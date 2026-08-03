"""评测2：记忆检索效果（Hit@K / MRR）"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.services.memory.retriever import MemoryRetriever  # noqa: E402
from app.services.memory.storage import MemoryStorage  # noqa: E402

from data.retrieval_dataset import GROUND_TRUTH_MEMORIES, QUERIES  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        stu = Student(name="评测检索学生", grade="初一", subject="数学")
        db.add(stu)
        db.commit()
        db.refresh(stu)
        student_id = stu.id
    finally:
        db.close()

    # 写入 ground truth 记忆
    MemoryStorage().write(student_id, session_id=None, items=GROUND_TRUTH_MEMORIES)

    retriever = MemoryRetriever()
    hits_at_k = 0
    reciprocal_ranks = []
    detail = []

    for q in QUERIES:
        result = retriever.retrieve(student_id, q["q"], top_k=3)
        # 拼接检索文本（相关记忆 + 画像 + 最近事件）
        texts = result["relevant_memories"] + result["profile_summary"].split("\n") + result["recent_events"]
        rank = None
        for i, t in enumerate(texts):
            if any(kw in t for kw in q["keywords"]):
                rank = i + 1
                break
        if rank:
            hits_at_k += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
        detail.append({"q": q["q"], "keywords": q["keywords"], "rank": rank})

    hit_rate = hits_at_k / len(QUERIES)
    mrr = sum(reciprocal_ranks) / len(QUERIES)

    # 清理评测学生（SQL 直删，避免外键顺序问题）
    from sqlalchemy import text  # noqa: E402
    from app.core.database import engine  # noqa: E402
    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        conn.execute(text(f"DELETE FROM memory_conflicts WHERE student_id={student_id}"))
        conn.execute(text(f"DELETE FROM review_plans WHERE student_id={student_id}"))
        conn.execute(text(f"DELETE FROM memories WHERE student_id={student_id}"))
        conn.execute(text(f"DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE student_id={student_id})"))
        conn.execute(text(f"DELETE FROM sessions WHERE student_id={student_id}"))
        conn.execute(text(f"DELETE FROM students WHERE id={student_id}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        conn.commit()

    result = {
        "total_queries": len(QUERIES),
        "hit_rate_top3": round(hit_rate, 4),
        "mrr": round(mrr, 4),
        "detail": detail,
    }
    out = Path(__file__).parent / "results" / "eval_retrieval.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[评测2 检索效果] 查询数={len(QUERIES)}")
    print(f"  Hit@3 = {hit_rate:.4f}   MRR = {mrr:.4f}")
    print(f"  结果已存: {out}")


if __name__ == "__main__":
    main()