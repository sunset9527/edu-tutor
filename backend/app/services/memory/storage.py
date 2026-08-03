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
from app.services.memory.chroma_client import get_memory_collection

logger = logging.getLogger(__name__)


class MemoryStorage:
    def __init__(self):
        self.collection = get_memory_collection()

    def write(
        self, student_id: int, session_id: int | None = None, items: list[dict] | None = None
    ) -> int:
        """写入多条记忆，返回写入条数（session_id 可空，如批量导入场景）"""
        items = items or []
        if not items:
            return 0
        db = SessionLocal()
        try:
            count = 0
            for item in items:
                mtype = item.get("type", "episodic")
                predicate = item.get("predicate", "信息")
                obj = item.get("object", "")
                confidence = min(1.0, max(0.0, float(item.get("confidence", 0.7))))
                conflict_flag = bool(item.get("conflict", False))

                # 冲突检测：同 predicate 已有不同内容的 active 记忆
                if conflict_flag or self._has_conflict(db, student_id, predicate, obj):
                    self._resolve_conflict(db, student_id, predicate, obj)

                content = f"{predicate}：{obj}"
                memory = Memory(
                    student_id=student_id,
                    memory_type=mtype,
                    content=content,
                    structured_data={"predicate": predicate, "object": obj},
                    source_session_id=session_id,
                    confidence=confidence,
                )
                db.add(memory)
                db.flush()  # 获取 memory.id

                # Chroma 双写（BGE-M3 向量）
                try:
                    emb = embed_texts([content])[0]
                    self.collection.add(
                        ids=[str(memory.id)],
                        embeddings=[emb],
                        metadatas=[
                            {
                                "student_id": student_id,
                                "memory_type": mtype,
                                "predicate": predicate,
                            }
                        ],
                        documents=[content],
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Chroma 写入失败（记忆 {memory.id} 仍保留在 MySQL）: {e}")

                # 复习计划（遗忘曲线调度，v0.3）
                from app.services.memory.forgetting import ReviewScheduler

                ReviewScheduler().create_plan(db, student_id, "memory", memory.id)

                # 知识点关联（双引擎桥，v0.3）
                self._link_knowledge_point(db, memory)

                count += 1

            db.commit()
            self._refresh_profile(db, student_id)
            logger.info(f"记忆写入完成: 学生{student_id} 新增{count}条")
            return count
        finally:
            db.close()

    def _has_conflict(self, db, student_id: int, predicate: str, obj: str) -> bool:
        """同 predicate 已有不同内容 -> 冲突"""
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
            sd = m.structured_data or {}
            if sd.get("predicate") == predicate and sd.get("object") != obj:
                return True
        return False

    def _resolve_conflict(self, db, student_id: int, predicate: str, obj: str) -> None:
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
        for m in rows:
            sd = m.structured_data or {}
            if sd.get("predicate") == predicate and sd.get("object") != obj:
                m.status = "contradicted"
                db.add(
                    MemoryConflict(
                        student_id=student_id,
                        old_memory_id=m.id,
                        new_content=f"{predicate}：{obj}",
                    )
                )

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
        db.commit()  # 画像快照落库（write 的 commit 在此之前）
