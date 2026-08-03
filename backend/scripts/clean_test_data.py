"""清理测试数据：仅保留 v03验证 学生及其记忆/复习计划，删除其他所有学生数据"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.database import engine, SessionLocal  # noqa: E402
from app.models.memory import Memory, MemoryConflict, ReviewPlan  # noqa: E402
from app.models.session import Message, Session as TutorSession  # noqa: E402
from app.models.knowledge import WrongQuestion  # noqa: E402
from app.models.student import Student, StudentProfile  # noqa: E402

db = SessionLocal()
try:
    keep = db.query(Student).filter(Student.name == "v03验证").first()
    if not keep:
        print("未找到 v03验证 学生，跳过清理")
        sys.exit(0)
    keep_id = keep.id
    keep_session_ids = [
        s.id for s in db.query(TutorSession).filter(TutorSession.student_id == keep_id).all()
    ]
    print(f"保留学生: v03验证 (id={keep_id}), 会话 {len(keep_session_ids)} 个")

    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        # 消息表无 student_id，通过 session_id 过滤
        if keep_session_ids:
            conn.execute(
                text(
                    "DELETE FROM messages WHERE session_id NOT IN "
                    f"({','.join(str(x) for x in keep_session_ids)})"
                )
            )
        else:
            conn.execute(text("DELETE FROM messages"))
        print("已清理 messages")
        # 各子表按 student_id 过滤
        for t in [
            MemoryConflict.__tablename__,
            ReviewPlan.__tablename__,
            Memory.__tablename__,
            TutorSession.__tablename__,
            WrongQuestion.__tablename__,
            StudentProfile.__tablename__,
        ]:
            conn.execute(text(f"DELETE FROM `{t}` WHERE student_id != {keep_id}"))
            print(f"已清理 {t}")
        conn.execute(text(f"DELETE FROM students WHERE id != {keep_id}"))
        print("已清理 students")
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        conn.commit()

    # 清空记忆向量库中其他学生的向量
    from app.services.memory.chroma_client import get_memory_collection
    coll = get_memory_collection()
    all_items = coll.get()
    drop_ids = []
    for i, meta in enumerate(all_items.get("metadatas", []) or []):
        if meta and meta.get("student_id") != keep_id:
            drop_ids.append(all_items["ids"][i])
    if drop_ids:
        coll.delete(ids=drop_ids)
        print(f"已清理记忆向量: {len(drop_ids)} 条")
    else:
        print("记忆向量无需清理")
    print("清理完成")
finally:
    db.close()