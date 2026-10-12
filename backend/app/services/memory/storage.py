"""记忆存储：MySQL memories 表 + ChromaDB 向量库双写

职责：
- 写入记忆（memories 表 + memory_vectors collection）
- 冲突检测与消解（memory_conflicts）
- 画像快照刷新（student_profile）
"""
import logging

from app.core.database import SessionLocal
from app.core.embeddings import embed_texts
from app.models.memory import Memory, MemoryConflict
from app.models.student import StudentProfile
from app.services import settings_service
from app.services.memory.chroma_client import get_memory_collection
from app.services.memory.lifecycle import build_provenance

logger = logging.getLogger(__name__)

SINGLE_VALUE_PREDICATES = {"年级", "学习偏好"}
OPPOSITE_PREDICATE_PAIRS = {frozenset({"薄弱点", "已掌握"})}


def is_memory_candidate_accepted(confidence: float, minimum: float) -> bool:
    """置信度达到配置阈值才允许写入。"""
    return confidence >= minimum


def facts_conflict(
    existing: dict,
    incoming: dict,
    *,
    explicit_conflict: bool = False,
) -> bool:
    """判断两个结构化事实是否占用同一且互斥的事实槽位。"""
    old_predicate = str(existing.get("predicate") or "")
    new_predicate = str(incoming.get("predicate") or "")
    old_object = str(existing.get("object") or "")
    new_object = str(incoming.get("object") or "")
    if old_predicate == new_predicate:
        if old_object == new_object:
            return False
        return old_predicate in SINGLE_VALUE_PREDICATES or explicit_conflict

    old_kp = existing.get("knowledge_point_id")
    new_kp = incoming.get("knowledge_point_id")
    predicates = frozenset({old_predicate, new_predicate})
    return bool(old_kp and new_kp and old_kp == new_kp and predicates in OPPOSITE_PREDICATE_PAIRS)


def upsert_memory_vector(
    memory: Memory,
    *,
    collection=None,
    embedder=embed_texts,
) -> None:
    """按记忆当前内容幂等写入 Chroma。"""
    collection = collection or get_memory_collection()
    structured = memory.structured_data or {}
    collection.upsert(
        ids=[str(memory.id)],
        embeddings=[embedder([memory.content])[0]],
        metadatas=[
            {
                "student_id": memory.student_id,
                "memory_type": memory.memory_type,
                "predicate": str(structured.get("predicate") or "信息"),
            }
        ],
        documents=[memory.content],
    )


def delete_memory_vector(memory_id: int, *, collection=None) -> None:
    """从 Chroma 删除指定记忆向量。"""
    collection = collection or get_memory_collection()
    collection.delete(ids=[str(memory_id)])


class MemoryStorage:
    def __init__(self):
        self.collection = get_memory_collection()

    def write(
        self,
        student_id: int,
        session_id: int | None = None,
        items: list[dict] | None = None,
        *,
        source_message_id: int | None = None,
        extraction_version: str = "v1.5",
        model_name: str = "unknown",
    ) -> int:
        """写入多条记忆，返回写入条数（session_id 可空，如批量导入场景）"""
        items = items or []
        if not items:
            return 0
        db = SessionLocal()
        written_vector_ids: list[int] = []
        removed_conflict_memories: list[Memory] = []
        try:
            count = 0
            for item in items:
                mtype = item.get("type", "episodic")
                predicate = item.get("predicate", "信息")
                obj = item.get("object", "")
                confidence = min(1.0, max(0.0, float(item.get("confidence", 0.7))))
                conflict_flag = bool(item.get("conflict", False))

                minimum_confidence = settings_service.get_float(
                    "extract_min_confidence", 0.5
                )
                if not is_memory_candidate_accepted(confidence, minimum_confidence):
                    logger.info(
                        "跳过低置信度记忆: confidence=%.3f threshold=%.3f",
                        confidence,
                        minimum_confidence,
                    )
                    continue

                incoming_fact = {
                    "predicate": predicate,
                    "object": obj,
                    "knowledge_point_id": item.get("knowledge_point_id"),
                    "provenance": item.get("provenance")
                    or build_provenance(
                        session_id=session_id,
                        message_id=source_message_id,
                        extraction_version=extraction_version,
                        model_name=model_name,
                    ),
                }

                if mtype == "procedural" and predicate == "有效策略":
                    changed, activated_id = self._record_procedural_evidence(
                        db,
                        student_id,
                        incoming_fact,
                        confidence,
                        session_id=session_id,
                    )
                    if activated_id is not None:
                        written_vector_ids.append(activated_id)
                    if changed:
                        count += 1
                    continue

                if self._has_conflict(
                    db,
                    student_id,
                    incoming_fact,
                    explicit_conflict=conflict_flag,
                ):
                    conflicts = self._resolve_conflict(
                        db,
                        student_id,
                        incoming_fact,
                        explicit_conflict=conflict_flag,
                    )
                    for old_memory in conflicts:
                        delete_memory_vector(old_memory.id, collection=self.collection)
                        removed_conflict_memories.append(old_memory)

                content = f"{predicate}：{obj}"
                memory = Memory(
                    student_id=student_id,
                    memory_type=mtype,
                    content=content,
                    structured_data=incoming_fact,
                    source_session_id=session_id,
                    confidence=confidence,
                )
                db.add(memory)
                db.flush()  # 获取 memory.id

                upsert_memory_vector(memory, collection=self.collection)
                written_vector_ids.append(memory.id)

                # 复习计划（遗忘曲线调度，v0.3）
                from app.services.memory.forgetting import ReviewScheduler

                ReviewScheduler().create_plan(db, student_id, "memory", memory.id)

                # 知识点关联（双引擎桥，v0.3）
                self._link_knowledge_point(db, memory)

                count += 1

            self._refresh_profile(db, student_id)
            db.commit()
            logger.info(f"记忆写入完成: 学生{student_id} 新增{count}条")
            return count
        except Exception:
            db.rollback()
            for memory_id in written_vector_ids:
                try:
                    delete_memory_vector(memory_id, collection=self.collection)
                except Exception as cleanup_error:  # noqa: BLE001
                    logger.error("回滚记忆向量失败 id=%s: %s", memory_id, cleanup_error)
            for old_memory in removed_conflict_memories:
                try:
                    upsert_memory_vector(old_memory, collection=self.collection)
                except Exception as cleanup_error:  # noqa: BLE001
                    logger.error("恢复冲突记忆向量失败 id=%s: %s", old_memory.id, cleanup_error)
            raise
        finally:
            db.close()

    def _record_procedural_evidence(
        self,
        db,
        student_id: int,
        incoming_fact: dict,
        confidence: float,
        *,
        session_id: int | None,
    ) -> tuple[bool, int | None]:
        """累计相同教学策略证据，达到阈值时才激活长期记忆。"""
        threshold = max(
            1,
            settings_service.get_int("consolidation_threshold", 3),
        )
        rows = (
            db.query(Memory)
            .filter(
                Memory.student_id == student_id,
                Memory.memory_type == "procedural",
                Memory.status.in_(["candidate", "active"]),
            )
            .all()
        )
        strategy = incoming_fact.get("object")
        existing = next(
            (row for row in rows if (row.structured_data or {}).get("object") == strategy),
            None,
        )
        if existing:
            structured = dict(existing.structured_data or {})
            history = list(structured.get("provenance_history") or [])
            provenance = incoming_fact["provenance"]
            source_key = (
                provenance.get("source_session_id"),
                provenance.get("source_message_id"),
            )
            if source_key != (None, None) and any(
                (
                    item.get("source_session_id"),
                    item.get("source_message_id"),
                )
                == source_key
                for item in history
            ):
                return False, None
            evidence_count = int(structured.get("evidence_count", 1)) + 1
            history.append(incoming_fact["provenance"])
            structured.update(
                {
                    "predicate": "有效策略",
                    "object": strategy,
                    "evidence_count": evidence_count,
                    "provenance": incoming_fact["provenance"],
                    "provenance_history": history,
                }
            )
            existing.structured_data = structured
            existing.confidence = max(existing.confidence, confidence)
            existing.source_session_id = session_id or existing.source_session_id
            if existing.status == "candidate" and evidence_count >= threshold:
                existing.status = "active"
                upsert_memory_vector(existing, collection=self.collection)
                from app.services.memory.forgetting import ReviewScheduler

                ReviewScheduler().create_plan(db, student_id, "memory", existing.id)
                return True, existing.id
            return True, None

        structured = dict(incoming_fact)
        structured["evidence_count"] = 1
        structured["provenance_history"] = [incoming_fact["provenance"]]
        memory = Memory(
            student_id=student_id,
            memory_type="procedural",
            content=f"有效策略：{strategy}",
            structured_data=structured,
            source_session_id=session_id,
            confidence=confidence,
            status="active" if threshold == 1 else "candidate",
        )
        db.add(memory)
        db.flush()
        if memory.status == "active":
            upsert_memory_vector(memory, collection=self.collection)
            from app.services.memory.forgetting import ReviewScheduler

            ReviewScheduler().create_plan(db, student_id, "memory", memory.id)
            return True, memory.id
        return True, None

    def _has_conflict(
        self,
        db,
        student_id: int,
        incoming: dict,
        *,
        explicit_conflict: bool = False,
    ) -> bool:
        """存在占用同一互斥事实槽位的 active 记忆。"""
        rows = (
            db.query(Memory)
            .filter(
                Memory.student_id == student_id,
                Memory.memory_type == "semantic",
                Memory.status == "active",
            )
            .all()
        )
        for m in rows:
            existing = dict(m.structured_data or {})
            existing["knowledge_point_id"] = m.knowledge_point_id
            if facts_conflict(
                existing,
                incoming,
                explicit_conflict=explicit_conflict,
            ):
                return True
        return False

    def _resolve_conflict(
        self,
        db,
        student_id: int,
        incoming: dict,
        *,
        explicit_conflict: bool = False,
    ) -> list[Memory]:
        """旧记忆标 contradicted + 记录冲突"""
        rows = (
            db.query(Memory)
            .filter(
                Memory.student_id == student_id,
                Memory.memory_type == "semantic",
                Memory.status == "active",
            )
            .all()
        )
        conflicts: list[Memory] = []
        for m in rows:
            existing = dict(m.structured_data or {})
            existing["knowledge_point_id"] = m.knowledge_point_id
            if facts_conflict(
                existing,
                incoming,
                explicit_conflict=explicit_conflict,
            ):
                m.status = "contradicted"
                conflicts.append(m)
                db.add(
                    MemoryConflict(
                        student_id=student_id,
                        old_memory_id=m.id,
                        new_content=f"{incoming.get('predicate')}：{incoming.get('object')}",
                    )
                )
        return conflicts

    def _link_knowledge_point(self, db, memory: Memory) -> None:
        """双引擎桥：向量检索最相似知识点，填 knowledge_point_id（相似度阈值）"""
        try:
            from app.core.embeddings import embed_query
            from app.services.knowledge.chroma_client import get_knowledge_collection

            coll = get_knowledge_collection()
            if coll.count() == 0:
                return  # 知识库尚未编译
            query_emb = embed_query(memory.content)
            hits = coll.query(query_embeddings=[query_emb], n_results=1)
            ids = (hits.get("ids") or [[]])[0]
            distances = (hits.get("distances") or [[]])[0]
            if ids and distances and distances[0] < 0.45:  # 余弦距离 → 相似度 > 0.55
                memory.knowledge_point_id = int(ids[0])
        except Exception as e:  # noqa: BLE001
            logger.debug(f"知识点关联跳过: {e}")

    def _refresh_profile(self, db, student_id: int) -> None:
        """从 active semantic 记忆聚合画像快照"""
        rows = (
            db.query(Memory)
            .filter(
                Memory.student_id == student_id,
                Memory.memory_type == "semantic",
                Memory.status == "active",
            )
            .all()
        )
        weaknesses: list[str] = []
        strengths: list[str] = []
        for m in rows:
            sd = m.structured_data or {}
            pred = sd.get("predicate")
            obj = sd.get("object")
            if pred == "薄弱点" and obj and obj not in weaknesses:
                weaknesses.append(obj)
            elif pred == "已掌握" and obj and obj not in strengths:
                strengths.append(obj)

        profile = db.get(StudentProfile, student_id)
        if not profile:
            profile = StudentProfile(student_id=student_id)
            db.add(profile)
        profile.weaknesses = weaknesses
        profile.strengths = strengths
