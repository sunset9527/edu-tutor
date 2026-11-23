"""v1.8 学习目标的不可变版本契约。"""

from datetime import date, timedelta
import uuid

from fastapi.testclient import TestClient

from app.core.security import create_token
from app.core.database import SessionLocal
from app.main import app
from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import KnowledgeSourceChunk, KnowledgeVersion, Textbook
from app.models.diagnostics import DiagnosticAnswer, DiagnosticKnowledgeResult, DiagnosticQuestion, DiagnosticSession
from app.models.learning import LearningPlanItem, LearningPlanVersion
from app.models.learning import LearningGoal, LearningGoalTarget, LearningGoalVersion
from app.models.student import Student
from app.models.user import User
from app.services.learning_goals import append_learning_goal_version


client = TestClient(app)


def test_creating_goal_pins_active_knowledge_version_and_first_version():
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    user = User(username=f"v18-goal-{token}", password_hash="fixture")
    other_user = User(username=f"v18-other-{token}", password_hash="fixture")
    textbook = Textbook(
        identity_key=f"v18-goal:{token}",
        grade="二年级",
        subject="数学",
        source_kind="fixture",
    )
    student = Student(name=f"v18-goal-{token}", grade="二年级", subject="数学")
    student_id = user_id = other_user_id = textbook_id = version_id = chunk_id = target_id = uncovered_target_id = question_id = None
    try:
        db.add_all([user, other_user, textbook, student])
        db.flush()
        student.user_id = user.id
        version = KnowledgeVersion(
            textbook_id=textbook.id,
            version_no=1,
            status="active",
            created_by=user.id,
        )
        db.add(version)
        db.flush()
        textbook.active_version_id = version.id
        chunk = KnowledgeSourceChunk(
            version_id=version.id,
            sequence=1,
            start_page=1,
            end_page=1,
            raw_text="测试教材正文",
            content_hash="a" * 64,
            parse_method="fixture",
            parser_version="test",
        )
        db.add(chunk)
        db.flush()
        target = KnowledgePoint(
            subject="数学",
            grade="二年级",
            title="认识长度单位",
            slug=f"v18-goal-kp-{token}",
            difficulty="基础",
            version_id=version.id,
            source_chunk_id=chunk.id,
            provenance_gap=False,
        )
        db.add(target)
        db.flush()
        uncovered_target = KnowledgePoint(
            subject="数学",
            grade="二年级",
            title="没有诊断题的目标",
            slug=f"v18-no-evidence-kp-{token}",
            difficulty="基础",
            version_id=version.id,
            source_chunk_id=chunk.id,
            provenance_gap=False,
        )
        db.add(uncovered_target)
        db.flush()
        question = DiagnosticQuestion(
            knowledge_version_id=version.id,
            knowledge_point_id=target.id,
            source_chunk_id=chunk.id,
            question_type="objective",
            difficulty="基础",
            stem="1 + 1 = ?",
            options_json=["1", "2"],
            answer_key_json={"value": "2"},
            max_score=1,
            status="published",
        )
        db.add(question)
        db.commit()
        student_id = student.id
        user_id = user.id
        other_user_id = other_user.id
        textbook_id = textbook.id
        version_id = version.id
        chunk_id = chunk.id
        target_id = target.id
        uncovered_target_id = uncovered_target.id
        question_id = question.id
        db.close()

        created = client.post(
            "/api/learning/goals",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
            json={
                "student_id": student_id,
                "target_date": str(date.today() + timedelta(days=28)),
                "weekly_minutes": 120,
                "subject": "数学",
                "target_level": "熟练",
                "target_knowledge_point_ids": [target_id, uncovered_target_id],
            },
        )
        assert created.status_code == 201
        db = SessionLocal()
        goal = db.get(LearningGoal, created.json()["id"])
        assert goal is not None

        assert goal.current_version_no == 1
        assert goal.current_version.knowledge_version_id == version_id
        assert [item.knowledge_point_id for item in goal.current_version.targets] == [target_id, uncovered_target_id]
        assert goal.current_version.status == "active"

        diagnostic = client.post(
            "/api/learning/diagnostics",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
            json={"student_id": student_id, "goal_id": goal.id},
        )
        assert diagnostic.status_code == 201
        assert diagnostic.json()["missing_question_knowledge_point_ids"] == [uncovered_target_id]
        session_id = diagnostic.json()["id"]
        resumed = client.get(
            f"/api/learning/diagnostics/goals/{goal.id}",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
        )
        assert resumed.status_code == 200
        assert resumed.json()["id"] == session_id
        saved = client.put(
            f"/api/learning/diagnostics/{session_id}/answers/{question_id}",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
            json={"raw_answer": {"value": "2"}, "elapsed_seconds": 8, "confidence": 4},
        )
        assert saved.status_code == 200
        assert saved.json()["final_score"] == 1
        submitted = client.post(
            f"/api/learning/diagnostics/{session_id}/submit",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
        )
        assert submitted.status_code == 200
        assert submitted.json()["results"][0]["mastery"] == "熟练"
        report = client.get(
            f"/api/learning/diagnostics/{session_id}/report",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
        )
        assert report.status_code == 200
        report_results = {row["knowledge_point_id"]: row for row in report.json()["results"]}
        assert report_results[target_id]["evidence_status"] == "confirmed"
        assert report_results[target_id]["source_page_range"] == [1, 1]
        assert report_results[target_id]["elapsed_seconds"] == 8
        assert report_results[target_id]["confidence"] == 4.0
        assert report_results[uncovered_target_id]["score_rate"] is None
        assert report_results[uncovered_target_id]["valid_answer_count"] == 0
        assert report_results[uncovered_target_id]["mastery"] is None
        assert report_results[uncovered_target_id]["evidence_status"] == "no_evidence"
        assert report_results[uncovered_target_id]["evidence"] == {"reason": "no_published_diagnostic_question"}
        assert report_results[uncovered_target_id]["source_page_range"] == [1, 1]
        planned = client.post(
            "/api/learning/plans",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
            json={"student_id": student_id, "goal_id": goal.id},
        )
        assert planned.status_code == 201
        assert planned.json()["items"][0]["knowledge_point_id"] == target_id

        current_history = client.get(
            f"/api/learning/plans/{goal.id}",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
        )
        assert current_history.status_code == 200
        assert current_history.json()["plans"][0]["status"] == "current"

        updated = append_learning_goal_version(
            db,
            goal_id=goal.id,
            target_date=date.today() + timedelta(days=42),
            weekly_minutes=180,
            target_level="基本会",
            target_knowledge_point_ids=[target_id],
            status="paused",
            change_reason="paused",
        )

        assert updated.current_version_no == 2
        assert updated.current_version.status == "paused"
        assert updated.current_version.weekly_minutes == 180
        assert updated.current_version.target_level == "基本会"
        assert [item.knowledge_point_id for item in updated.current_version.targets] == [target_id]
        assert [(row.version_no, row.weekly_minutes, row.status) for row in updated.versions] == [
            (1, 120, "active"),
            (2, 180, "paused"),
        ]

        own = client.get(
            f"/api/learning/goals/{student_id}",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
        )
        assert own.status_code == 200
        assert own.json()["current_version"]["version_no"] == 2
        stale_history = client.get(
            f"/api/learning/plans/{goal.id}",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
        )
        assert stale_history.json()["plans"][0]["status"] == "stale"
        resumed = client.patch(
            f"/api/learning/goals/{goal.id}",
            headers={"Authorization": f"Bearer {create_token(user_id)}"},
            json={"status": "active", "change_reason": "resumed"},
        )
        assert resumed.status_code == 200
        assert resumed.json()["current_version"]["version_no"] == 3
        assert resumed.json()["current_version"]["status"] == "active"
        foreign = client.get(
            f"/api/learning/goals/{student_id}",
            headers={"Authorization": f"Bearer {create_token(other_user_id)}"},
        )
        assert foreign.status_code == 404
    finally:
        db.rollback()
        db.query(LearningGoal).filter(LearningGoal.student_id == student_id).update(
            {"current_version_id": None}, synchronize_session=False
        )
        db.flush()
        session_ids = db.query(DiagnosticSession.id).filter(
            DiagnosticSession.student_id == student_id
        )
        plan_ids = db.query(LearningPlanVersion.id).filter(
            LearningPlanVersion.student_id == student_id
        )
        db.query(LearningPlanItem).filter(
            LearningPlanItem.plan_version_id.in_(plan_ids)
        ).delete(synchronize_session=False)
        db.query(LearningPlanVersion).filter(
            LearningPlanVersion.student_id == student_id
        ).delete(synchronize_session=False)
        db.query(DiagnosticKnowledgeResult).filter(
            DiagnosticKnowledgeResult.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(DiagnosticAnswer).filter(
            DiagnosticAnswer.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(DiagnosticSession).filter(
            DiagnosticSession.student_id == student_id
        ).delete(synchronize_session=False)
        db.query(LearningGoalTarget).filter(
            LearningGoalTarget.goal_version_id.in_(
                db.query(LearningGoalVersion.id).filter(LearningGoalVersion.goal_id.in_(
                    db.query(LearningGoal.id).filter(LearningGoal.student_id == student_id)
                ))
            )
        ).delete(synchronize_session=False)
        db.query(LearningGoalVersion).filter(
            LearningGoalVersion.goal_id.in_(
                db.query(LearningGoal.id).filter(LearningGoal.student_id == student_id)
            )
        ).delete(synchronize_session=False)
        db.query(LearningGoal).filter(LearningGoal.student_id == student_id).delete(
            synchronize_session=False
        )
        db.query(DiagnosticQuestion).filter(DiagnosticQuestion.id == question_id).delete(
            synchronize_session=False
        )
        db.query(KnowledgePoint).filter(KnowledgePoint.id.in_([target_id, uncovered_target_id])).delete(
            synchronize_session=False
        )
        db.query(KnowledgeSourceChunk).filter(KnowledgeSourceChunk.id == chunk_id).delete(
            synchronize_session=False
        )
        db.query(Textbook).filter(Textbook.id == textbook_id).update(
            {"active_version_id": None}, synchronize_session=False
        )
        db.flush()
        db.query(KnowledgeVersion).filter(KnowledgeVersion.id == version_id).delete(
            synchronize_session=False
        )
        db.query(Textbook).filter(Textbook.id == textbook_id).delete(synchronize_session=False)
        db.query(Student).filter(Student.id == student_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == other_user_id).delete(synchronize_session=False)
        db.commit()
        db.close()
