"""v1.8 受控诊断会话与确定性客观题评分。"""

from datetime import datetime
import json

from sqlalchemy.orm import Session

from app.models.diagnostics import DiagnosticAnswer, DiagnosticKnowledgeResult, DiagnosticQuestion, DiagnosticSession
from app.models.learning import LearningGoal


def _suggest_subjective_score(question: DiagnosticQuestion, raw_answer: dict) -> tuple[int | None, dict]:
    """返回模型建议；不可用或失败时只返回状态，绝不构造分数。"""
    from app.core.config import settings
    if not settings.llm_configured:
        return None, {"status": "awaiting_model_suggestion", "reason": "llm_not_configured"}
    try:
        from app.core.llm import create_llm
        prompt = (
            "你是诊断测评评分助手。仅返回 JSON：{\"score\":整数,\"reason\":字符串}。"
            f"题目：{question.stem}\n满分：{question.max_score}\n评分规则：{question.rubric_json or {}}\n学生答案：{raw_answer}"
        )
        content = str(create_llm(temperature=0.0).invoke(prompt).content).strip()
        data = json.loads(content.removeprefix("```json").removesuffix("```").strip())
        score = int(data["score"])
        if not 0 <= score <= question.max_score:
            raise ValueError("suggested score out of range")
        return score, {"status": "suggested", "model": settings.deepseek_model, "reason": str(data.get("reason", ""))}
    except Exception as exc:
        return None, {"status": "awaiting_model_suggestion", "reason": "model_failed", "error_type": type(exc).__name__}


def start_or_resume_diagnostic(db: Session, *, student_id: int, goal_id: int) -> DiagnosticSession:
    goal = db.get(LearningGoal, goal_id)
    if goal is None or goal.student_id != student_id or goal.current_version is None:
        raise ValueError("学习目标不存在")
    version = goal.current_version
    if version.status != "active":
        raise ValueError("学习目标当前未启用")
    existing = db.query(DiagnosticSession).filter(
        DiagnosticSession.student_id == student_id,
        DiagnosticSession.goal_version_id == version.id,
        DiagnosticSession.status == "in_progress",
    ).order_by(DiagnosticSession.id.desc()).first()
    if existing:
        return existing
    target_ids = [item.knowledge_point_id for item in version.targets]
    questions = db.query(DiagnosticQuestion).filter(
        DiagnosticQuestion.knowledge_version_id == version.knowledge_version_id,
        DiagnosticQuestion.knowledge_point_id.in_(target_ids),
        DiagnosticQuestion.status == "published",
    ).order_by(DiagnosticQuestion.knowledge_point_id, DiagnosticQuestion.id).all()
    if not questions:
        raise ValueError("目标范围没有已发布诊断题")
    session = DiagnosticSession(student_id=student_id, goal_id=goal.id, goal_version_id=version.id, knowledge_version_id=version.knowledge_version_id)
    db.add(session)
    db.flush()
    db.add_all([DiagnosticAnswer(session_id=session.id, question_id=question.id) for question in questions])
    db.commit()
    db.refresh(session)
    return session


def save_answer(db: Session, *, session: DiagnosticSession, question_id: int, raw_answer: dict, elapsed_seconds: int | None, confidence: int | None) -> DiagnosticAnswer:
    answer = db.query(DiagnosticAnswer).filter(DiagnosticAnswer.session_id == session.id, DiagnosticAnswer.question_id == question_id).one_or_none()
    if answer is None:
        raise ValueError("题目不属于该诊断")
    question = db.get(DiagnosticQuestion, question_id)
    if question is None:
        raise ValueError("诊断题不存在")
    answer.raw_answer = raw_answer
    answer.elapsed_seconds = elapsed_seconds
    answer.confidence = confidence
    if question.question_type == "objective":
        expected = str((question.answer_key_json or {}).get("value", "")).strip().casefold()
        actual = str((raw_answer or {}).get("value", "")).strip().casefold()
        answer.deterministic_score = question.max_score if expected and actual == expected else 0
        answer.final_score = answer.deterministic_score
        answer.grading_basis = {"method": "deterministic", "expected": expected}
        answer.confirmed_at = datetime.now()
    else:
        answer.deterministic_score = None
        answer.final_score = None
        answer.suggested_score, answer.suggestion_basis = _suggest_subjective_score(question, raw_answer)
        answer.confirmed_at = None
    db.commit()
    db.refresh(answer)
    return answer


def submit_diagnostic(db: Session, *, session: DiagnosticSession) -> list[DiagnosticKnowledgeResult]:
    """提交已确认的诊断，按知识点持久化可追溯结论。"""
    answers = db.query(DiagnosticAnswer).filter(DiagnosticAnswer.session_id == session.id).all()
    if not answers or any(answer.raw_answer is None or answer.final_score is None for answer in answers):
        raise ValueError("仍有题目未作答或主观题未确认")
    questions = {question.id: question for question in db.query(DiagnosticQuestion).filter(DiagnosticQuestion.id.in_([answer.question_id for answer in answers])).all()}
    grouped: dict[int, list[DiagnosticAnswer]] = {}
    for answer in answers:
        grouped.setdefault(questions[answer.question_id].knowledge_point_id, []).append(answer)
    db.query(DiagnosticKnowledgeResult).filter(DiagnosticKnowledgeResult.session_id == session.id).delete(synchronize_session=False)
    results = []
    for knowledge_point_id, rows in grouped.items():
        total = sum(questions[row.question_id].max_score for row in rows)
        gained = sum(row.final_score or 0 for row in rows)
        rate = gained / total if total else None
        mastery = "不懂" if rate is not None and rate < .5 else "基本会" if rate is not None and rate < .8 else "熟练"
        result = DiagnosticKnowledgeResult(session_id=session.id, knowledge_point_id=knowledge_point_id, score_rate=rate, valid_answer_count=len(rows), mastery=mastery, evidence_status="confirmed", evidence_json={"answer_ids": [row.id for row in rows]})
        db.add(result); results.append(result)
    session.status = "submitted"; session.submitted_at = datetime.now()
    db.commit()
    return results
