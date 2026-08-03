"""评测3：消融实验（有记忆 vs 无记忆）—— LLM-as-judge 打分"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.core.llm import create_llm  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.services.memory.storage import MemoryStorage  # noqa: E402

from data.ablation_scenarios import SCENARIOS  # noqa: E402

JUDGE_PROMPT = """你是教育产品评测专家。请比较两个 AI 辅导老师的回答，从三个维度打分（1-5 分）：
1. 个性化程度：回答是否贴合该学生的具体情况（历史、薄弱点、偏好）
2. 连贯性：回答是否自然、上下文一致
3. 正确性：教学内容是否正确、有帮助

学生情况：{profile}
学生提问：{question}

回答A（系统A）：{answer_a}
回答B（系统B）：{answer_b}

只输出 JSON：{{"personalization_a": 1-5, "personalization_b": 1-5, "coherence_a": 1-5, "coherence_b": 1-5, "correctness_a": 1-5, "correctness_b": 1-5, "brief_reason": "一句话说明哪个更好"}}"""


def profile_to_items(profile_text: str) -> list[dict]:
    """把画像文本拆成记忆项（按分号/句号切分）"""
    parts = [p.strip() for p in profile_text.replace("。", "；").split("；") if p.strip()]
    items = []
    for p in parts[:4]:
        items.append({"type": "semantic", "predicate": "画像信息", "object": p[:60], "confidence": 0.8})
    return items


def create_student(name: str, items: list[dict]) -> int:
    db = SessionLocal()
    try:
        stu = Student(name=name, grade="初一", subject="数学")
        db.add(stu)
        db.commit()
        db.refresh(stu)
        sid = stu.id
    finally:
        db.close()
    if items:
        MemoryStorage().write(sid, session_id=None, items=items)
    return sid


def ask(sid: int, question: str) -> str:
    """无历史对话，直接提问（新会话）"""
    from app.agents.chat_graph import run_chat
    from app.models.session import Session as TutorSession

    db = SessionLocal()
    try:
        s = TutorSession(student_id=sid, subject="数学")
        db.add(s)
        db.commit()
        db.refresh(s)
        session_id = s.id
    finally:
        db.close()
    return run_chat(sid, session_id, question)


def main() -> None:
    llm = create_llm(temperature=0.0)
    rows = []

    for sc in SCENARIOS:
        sid_a = create_student(f"消融A{sc['id']}", profile_to_items(sc["profile"]))
        sid_b = create_student(f"消融B{sc['id']}", [])

        try:
            answer_a = ask(sid_a, sc["question"])
        except Exception as e:
            answer_a = f"[错误] {e}"
        try:
            answer_b = ask(sid_b, sc["question"])
        except Exception as e:
            answer_b = f"[错误] {e}"

        judge = JUDGE_PROMPT.format(
            profile=sc["profile"], question=sc["question"], answer_a=answer_a, answer_b=answer_b
        )
        try:
            resp = llm.invoke(judge).content
            start, end = resp.find("{"), resp.rfind("}")
            scores = json.loads(resp[start : end + 1])
        except Exception:
            scores = {"personalization_a": 0, "personalization_b": 0, "coherence_a": 0, "coherence_b": 0, "correctness_a": 0, "correctness_b": 0, "brief_reason": "judge 解析失败"}

        rows.append({
            "id": sc["id"], "name": sc["name"],
            "answer_a": answer_a[:200], "answer_b": answer_b[:200],
            "scores": scores,
        })
        print(f"[场景{sc['id']} {sc['name']}] A(有记忆) vs B(无记忆) -> {scores.get('brief_reason', '')}")

    # 汇总
    def avg(key):
        vals = [r["scores"].get(key, 0) for r in rows]
        return round(sum(vals) / len(vals), 4)

    summary = {
        "avg_personalization_with_memory": avg("personalization_a"),
        "avg_personalization_no_memory": avg("personalization_b"),
        "avg_coherence_with_memory": avg("coherence_a"),
        "avg_coherence_no_memory": avg("coherence_b"),
        "avg_correctness_with_memory": avg("correctness_a"),
        "avg_correctness_no_memory": avg("correctness_b"),
    }
    result = {"summary": summary, "scenarios": rows}
    out = Path(__file__).parent / "results" / "eval_ablation.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[评测3 消融实验汇总] 有记忆 vs 无记忆")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  结果已存: {out}")


if __name__ == "__main__":
    main()