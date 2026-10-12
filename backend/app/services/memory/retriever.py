"""记忆检索：多路召回 + 组装注入文本

路 1：学生画像（student_profile + active semantic 记忆）—— 全局注入
路 2：向量语义检索（ChromaDB）—— 与当前问题相关，按遗忘曲线加权重排（v0.3）
路 3：最近情景事件（recent episodic）—— 对话连贯性
"""
import logging
import math
from datetime import datetime

from app.core.database import SessionLocal
from app.core.embeddings import embed_query
from app.models.memory import Memory
from app.models.student import StudentProfile
from app.services import settings_service
from app.services.memory.chroma_client import get_memory_collection
from app.services.memory.forgetting import retention_weight

logger = logging.getLogger(__name__)

DEFAULT_RETRIEVAL_WEIGHTS = {
    "similarity": 0.45,
    "recency": 0.15,
    "retention": 0.25,
    "confidence": 0.15,
}


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """把非负配置权重归一化；全为零时回退到等权。"""
    names = tuple(DEFAULT_RETRIEVAL_WEIGHTS)
    cleaned = {name: max(0.0, float(weights.get(name, 0.0))) for name in names}
    total = sum(cleaned.values())
    if total <= 0:
        return {name: 1.0 / len(names) for name in names}
    return {name: value / total for name, value in cleaned.items()}


def score_memory_candidate(
    *,
    similarity: float,
    recency: float,
    retention: float,
    confidence: float,
    weights: dict[str, float],
) -> float:
    """计算一条向量候选的统一分数。"""
    values = {
        "similarity": similarity,
        "recency": recency,
        "retention": retention,
        "confidence": confidence,
    }
    return sum(weights[name] * max(0.0, min(1.0, values[name])) for name in weights)


def recency_score(
    timestamp: datetime | None,
    *,
    now: datetime | None = None,
    decay_days: float = 14.0,
) -> float:
    """时间越近分数越高；decay_days 表示指数衰减时间尺度。"""
    now = now or datetime.now()
    if timestamp is None:
        return 0.0
    days = max(0.0, (now - timestamp).total_seconds() / 86400.0)
    return math.exp(-days / max(0.001, decay_days))


class MemoryRetriever:
    def __init__(self, *, collection=None, session_factory=SessionLocal, now_factory=datetime.now):
        self.collection = collection or get_memory_collection()
        self.session_factory = session_factory
        self.now_factory = now_factory

    def retrieve(self, student_id: int, query: str, top_k: int = 3) -> dict:
        """检索记忆，返回画像摘要 / 相关记忆 / 最近事件"""
        profile_quota = max(0, settings_service.get_int("retrieval_profile_quota", 8))
        recent_quota = max(0, settings_service.get_int("retrieval_recent_quota", 3))
        relevant_quota = max(
            0,
            min(top_k, settings_service.get_int("retrieval_relevant_quota", top_k)),
        )
        profile_lines, profile_ids = self._load_profile(student_id, profile_quota)
        recent_events, recent_ids = self._load_recent_events(student_id, recent_quota)
        vector_lines, vector_trace = self._vector_search(
            student_id,
            query,
            top_k=relevant_quota,
            excluded_ids=profile_ids | recent_ids,
        )

        return {
            "profile_summary": "\n".join(profile_lines),
            "relevant_memories": vector_lines,
            "recent_events": recent_events,
            "trace": {
                "student_id": student_id,
                "query": query,
                "quotas": {
                    "profile": profile_quota,
                    "relevant": relevant_quota,
                    "recent": recent_quota,
                },
                **vector_trace,
            },
        }

    def _load_profile_lines(self, student_id: int) -> list[str]:
        """画像 + active semantic 记忆"""
        return self._load_profile(student_id, 8)[0]

    def _load_profile(self, student_id: int, quota: int) -> tuple[list[str], set[int]]:
        db = self.session_factory()
        try:
            profile = db.get(StudentProfile, student_id)
            rows = (
                db.query(Memory)
                .filter(
                    Memory.student_id == student_id,
                    Memory.memory_type == "semantic",
                    Memory.status == "active",
                )
                .order_by(Memory.id.desc())
                .all()
            )
            entries: list[tuple[str, set[int]]] = []
            represented_ids: set[int] = set()
            if profile:
                for predicate, values, label in (
                    ("薄弱点", profile.weaknesses or [], "薄弱点"),
                    ("已掌握", profile.strengths or [], "已掌握"),
                ):
                    if not values:
                        continue
                    value_set = set(values)
                    ids = {
                        memory.id
                        for memory in rows
                        if (memory.structured_data or {}).get("predicate") == predicate
                        and (memory.structured_data or {}).get("object") in value_set
                    }
                    represented_ids.update(ids)
                    entries.append((f"{label}：" + "、".join(values), ids))
            for m in rows:
                if m.id in represented_ids:
                    continue
                line = f"{m.content}（置信度{m.confidence:.0%}）"
                if line not in {entry[0] for entry in entries}:
                    entries.append((line, {m.id}))
            selected = entries[: max(0, quota)]
            return [entry[0] for entry in selected], {
                memory_id for _, memory_ids in selected for memory_id in memory_ids
            }
        finally:
            db.close()

    def _load_recent_events(self, student_id: int, quota: int = 3) -> tuple[list[str], set[int]]:
        """最近情景记忆。"""
        db = self.session_factory()
        try:
            rows = (
                db.query(Memory)
                .filter(
                    Memory.student_id == student_id,
                    Memory.memory_type == "episodic",
                    Memory.status == "active",
                )
                .order_by(Memory.id.desc())
                .limit(max(0, quota))
                .all()
            )
            return [m.content for m in rows], {m.id for m in rows}
        finally:
            db.close()

    def _vector_search(
        self,
        student_id: int,
        query: str,
        top_k: int = 3,
        excluded_ids: set[int] | None = None,
    ) -> tuple[list[str], dict]:
        """向量召回后统一评分，返回命中内容和完整追踪。"""
        raw_weights = {
            name: settings_service.get_float(f"retrieval_weight_{name}", default)
            for name, default in DEFAULT_RETRIEVAL_WEIGHTS.items()
        }
        weights = normalize_weights(raw_weights)
        decay_days = settings_service.get_float("retrieval_recency_days", 14.0)
        excluded_ids = excluded_ids or set()
        trace = {
            "configured_weights": raw_weights,
            "applied_weights": weights,
            "recency_decay_days": decay_days,
            "candidates": [],
            "error": None,
        }
        try:
            query_emb = embed_query(query)
            hits = self.collection.query(
                query_embeddings=[query_emb],
                n_results=max(top_k * 3, 5),
                where={"student_id": student_id},
            )
            docs = (hits.get("documents") or [[]])[0] or []
            ids = (hits.get("ids") or [[]])[0] or []
            distances = (hits.get("distances") or [[]])[0] or []

            scored: list[dict] = []
            db = self.session_factory()
            try:
                now = self.now_factory()
                for index, (doc, mem_id) in enumerate(zip(docs, ids)):
                    try:
                        parsed_id = int(mem_id)
                    except (TypeError, ValueError):
                        trace["candidates"].append(
                            {"memory_id": mem_id, "content": doc, "selected": False, "reason": "invalid_id"}
                        )
                        continue
                    memory = db.get(Memory, parsed_id)
                    if not memory or memory.student_id != student_id or memory.status != "active":
                        trace["candidates"].append(
                            {"memory_id": parsed_id, "content": doc, "selected": False, "reason": "inactive_or_missing"}
                        )
                        continue
                    distance = float(distances[index]) if index < len(distances) else 1.0
                    similarity = max(0.0, min(1.0, 1.0 - distance))
                    base_time = memory.last_accessed_at or memory.last_reviewed_at or memory.created_at
                    components = {
                        "similarity": similarity,
                        "recency": recency_score(base_time, now=now, decay_days=decay_days),
                        "retention": retention_weight(
                            memory.strength,
                            memory.last_reviewed_at,
                            now=now,
                            created_at=memory.created_at,
                        ),
                        "confidence": max(0.0, min(1.0, memory.confidence)),
                    }
                    scored.append(
                        {
                            "memory": memory,
                            "memory_id": parsed_id,
                            "content": doc,
                            "components": components,
                            "final_score": score_memory_candidate(weights=weights, **components),
                        }
                    )

                scored.sort(key=lambda item: (-item["final_score"], item["memory_id"]))
                selected: list[dict] = []
                for rank, candidate in enumerate(scored, start=1):
                    candidate["rank"] = rank
                    if candidate["memory_id"] in excluded_ids:
                        candidate["selected"] = False
                        candidate["reason"] = "duplicate_in_other_channel"
                    elif len(selected) >= top_k:
                        candidate["selected"] = False
                        candidate["reason"] = "quota_exceeded"
                    else:
                        candidate["selected"] = True
                        candidate["reason"] = "selected"
                        candidate["memory"].last_accessed_at = now
                        selected.append(candidate)
                db.commit()
            finally:
                db.close()

            trace["candidates"].extend(
                [
                    {key: value for key, value in item.items() if key != "memory"}
                    for item in scored
                ]
            )
            return [item["content"] for item in selected], trace
        except Exception as e:  # noqa: BLE001
            logger.warning(f"向量检索失败: {e}")
            trace["error"] = str(e)
            return [], trace

    def build_injection_text(self, result: dict) -> str:
        """组装注入 System Prompt 的记忆上下文文本"""
        parts = []
        if result["profile_summary"]:
            parts.append("【学生画像】\n" + result["profile_summary"])
        if result["relevant_memories"]:
            parts.append("【相关历史记忆】\n" + "\n".join(result["relevant_memories"]))
        if result["recent_events"]:
            parts.append("【最近学习事件】\n" + "\n".join(result["recent_events"]))
        return "\n\n".join(parts)
