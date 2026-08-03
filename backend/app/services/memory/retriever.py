"""记忆检索：多路召回 + 组装注入文本

路 1：学生画像（student_profile + active semantic 记忆）—— 全局注入
路 2：向量语义检索（ChromaDB）—— 与当前问题相关，按遗忘曲线加权重排（v0.3）
路 3：最近情景事件（recent episodic）—— 对话连贯性
"""
import logging

from app.core.database import SessionLocal
from app.core.embeddings import embed_query
from app.models.memory import Memory
from app.models.student import StudentProfile
from app.services.memory.chroma_client import get_memory_collection
from app.services.memory.forgetting import retention_weight

logger = logging.getLogger(__name__)


class MemoryRetriever:
    def __init__(self):
        self.collection = get_memory_collection()

    def retrieve(self, student_id: int, query: str, top_k: int = 3) -> dict:
        """检索记忆，返回画像摘要 / 相关记忆 / 最近事件"""
        profile_lines = self._load_profile_lines(student_id)
        recent_events = self._load_recent_events(student_id)
        vector_lines = self._vector_search(student_id, query, top_k=top_k)

        return {
            "profile_summary": "\n".join(profile_lines),
            "relevant_memories": vector_lines,
            "recent_events": recent_events,
        }

    def _load_profile_lines(self, student_id: int) -> list[str]:
        """画像 + active semantic 记忆"""
        db = SessionLocal()
        try:
            profile = db.get(StudentProfile, student_id)
            lines: list[str] = []
            if profile:
                if profile.weaknesses:
                    lines.append("薄弱点：" + "、".join(profile.weaknesses))
                if profile.strengths:
                    lines.append("已掌握：" + "、".join(profile.strengths))
            rows = (
                db.query(Memory)
                .filter(
                    Memory.student_id == student_id,
                    Memory.memory_type == "semantic",
                    Memory.status == "active",
                )
                .order_by(Memory.id.desc())
                .limit(10)
                .all()
            )
            for m in rows:
                line = f"{m.content}（置信度{m.confidence:.0%}）"
                if line not in lines:
                    lines.append(line)
            return lines
        finally:
            db.close()

    def _load_recent_events(self, student_id: int) -> list[str]:
        """最近 3 条情景记忆"""
        db = SessionLocal()
        try:
            rows = (
                db.query(Memory)
                .filter(
                    Memory.student_id == student_id,
                    Memory.memory_type == "episodic",
                    Memory.status == "active",
                )
                .order_by(Memory.id.desc())
                .limit(3)
                .all()
            )
            return [m.content for m in rows]
        finally:
            db.close()

    def _vector_search(self, student_id: int, query: str, top_k: int = 3) -> list[str]:
        """向量语义检索（仅本学生）+ 遗忘曲线加权重排（v0.3）"""
        try:
            query_emb = embed_query(query)
            hits = self.collection.query(
                query_embeddings=[query_emb],
                n_results=max(top_k * 3, 5),
                where={"student_id": student_id},
            )
            docs = (hits.get("documents") or [[]])[0] or []
            ids = (hits.get("ids") or [[]])[0] or []

            # 遗忘加权：weight = retention(strength, last_reviewed_at)
            scored: list[tuple[float, str]] = []
            db = SessionLocal()
            try:
                for doc, mem_id in zip(docs, ids):
                    weight = 1.0
                    try:
                        memory = db.get(Memory, int(mem_id))
                        if memory:
                            weight = retention_weight(
                                memory.strength, memory.last_reviewed_at
                            )
                    except (TypeError, ValueError):
                        pass
                    scored.append((weight, doc))
            finally:
                db.close()

            scored.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in scored[:top_k]]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"向量检索失败: {e}")
            return []

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
