"""生成可复现的 v1.8 工程验收报告与计划 JSON（非真实学生数据）。"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.diagnostics import DiagnosticQuestion, DiagnosticKnowledgeResult
from app.models.knowledge_governance import Textbook
from app.models.learning import LearningPlanItem
from app.models.student import Student
from app.models.user import User
from app.services.diagnostics import save_answer, start_or_resume_diagnostic, submit_diagnostic
from app.services.learning_goals import create_learning_goal
from app.services.learning_plans import generate_learning_plan


def run(output: Path, version_id: int = 142) -> dict:
    """使用已发布题目走完目标→诊断→报告→计划，落盘可检查的工程样例。"""
    db = SessionLocal()
    try:
        textbook = db.query(Textbook).filter(Textbook.active_version_id == version_id).one_or_none()
        question = db.query(DiagnosticQuestion).filter(
            DiagnosticQuestion.knowledge_version_id == version_id,
            DiagnosticQuestion.status == "published",
        ).order_by(DiagnosticQuestion.id).first()
        if textbook is None or question is None:
            raise ValueError("需要 active v142 及至少一条已发布诊断题；请先导入工程样例或人工审校题目")
        token = uuid4().hex[:12]
        user = User(username=f"v18-engineering-{token}", password_hash="engineering-fixture")
        student = Student(name=f"v1.8 工程验收-{token}", grade=textbook.grade, subject=textbook.subject)
        db.add_all([user, student])
        db.flush()
        student.user_id = user.id
        db.commit()

        goal = create_learning_goal(
            db,
            student_id=student.id,
            target_date=date.today() + timedelta(days=28),
            weekly_minutes=120,
            subject=textbook.subject,
            target_level="熟练",
            target_knowledge_point_ids=[question.knowledge_point_id],
        )
        session = start_or_resume_diagnostic(db, student_id=student.id, goal_id=goal.id)
        answer_value = (question.answer_key_json or {}).get("value")
        if question.question_type != "objective" or answer_value is None:
            raise ValueError("工程验收样例需要一条带 value 答案键的客观题")
        save_answer(db, session=session, question_id=question.id, raw_answer={"value": answer_value}, elapsed_seconds=1, confidence=5)
        results = submit_diagnostic(db, session=session)
        plan = generate_learning_plan(db, student_id=student.id, goal_id=goal.id, adjustment_reason="engineering_acceptance")
        items = db.query(LearningPlanItem).filter(LearningPlanItem.plan_version_id == plan.id).order_by(LearningPlanItem.sequence_no).all()
        payload = {
            "kind": "engineering_acceptance_fixture",
            "warning": "此文件只证明工程流程可复现，不代表真实学生效果或学科人工审校。",
            "knowledge_version_id": version_id,
            "goal": {"id": goal.id, "version_id": goal.current_version_id},
            "diagnostic_report": [{"knowledge_point_id": row.knowledge_point_id, "mastery": row.mastery, "evidence_status": row.evidence_status, "score_rate": row.score_rate} for row in results],
            "learning_plan": {"id": plan.id, "status": plan.status, "scheduled_minutes": plan.scheduled_minutes, "missing_minutes": plan.missing_minutes, "items": [{"knowledge_point_id": item.knowledge_point_id, "week_no": item.week_no, "estimated_minutes": item.estimated_minutes, "scheduled": item.scheduled, "reasons": item.recommendation_reasons} for item in items]},
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-id", type=int, default=142)
    parser.add_argument("--output", type=Path, default=Path("../docs/releases/v1.8/engineering-sample-output.json"))
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.version_id), ensure_ascii=False, indent=2))
