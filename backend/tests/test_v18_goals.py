"""v1.8 学习目标的不可变版本契约。"""

from datetime import date, timedelta
import uuid

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import KnowledgeSourceChunk, KnowledgeVersion, Textbook
from app.models.learning import LearningGoal, LearningGoalTarget, LearningGoalVersion
from app.models.student import Student
from app.models.user import User
from app.services.learning_goals import create_learning_goal


def test_creating_goal_pins_active_knowledge_version_and_first_version():
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    user = User(username=f"v18-goal-{token}", password_hash="fixture")
    textbook = Textbook(
        identity_key=f"v18-goal:{token}",
        grade="二年级",
        subject="数学",
        source_kind="fixture",
    )
    student = Student(name=f"v18-goal-{token}", grade="二年级", subject="数学")
    try:
        db.add_all([user, textbook, student])
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
        db.commit()

        goal = create_learning_goal(
            db,
            student_id=student.id,
            target_date=date.today() + timedelta(days=28),
            weekly_minutes=120,
            subject="数学",
            target_level="熟练",
            target_knowledge_point_ids=[target.id],
        )

        assert goal.current_version_no == 1
        assert goal.current_version.knowledge_version_id == version.id
        assert [item.knowledge_point_id for item in goal.current_version.targets] == [target.id]
        assert goal.current_version.status == "active"
    finally:
        db.rollback()
        db.query(LearningGoal).filter(LearningGoal.student_id == student.id).update(
            {"current_version_id": None}, synchronize_session=False
        )
        db.flush()
        db.query(LearningGoalTarget).filter(
            LearningGoalTarget.goal_version_id.in_(
                db.query(LearningGoalVersion.id).filter(LearningGoalVersion.goal_id.in_(
                    db.query(LearningGoal.id).filter(LearningGoal.student_id == student.id)
                ))
            )
        ).delete(synchronize_session=False)
        db.query(LearningGoalVersion).filter(
            LearningGoalVersion.goal_id.in_(
                db.query(LearningGoal.id).filter(LearningGoal.student_id == student.id)
            )
        ).delete(synchronize_session=False)
        db.query(LearningGoal).filter(LearningGoal.student_id == student.id).delete(
            synchronize_session=False
        )
        db.query(KnowledgePoint).filter(KnowledgePoint.id == target.id).delete(
            synchronize_session=False
        )
        db.query(KnowledgeSourceChunk).filter(KnowledgeSourceChunk.id == chunk.id).delete(
            synchronize_session=False
        )
        textbook.active_version_id = None
        db.flush()
        db.query(KnowledgeVersion).filter(KnowledgeVersion.id == version.id).delete(
            synchronize_session=False
        )
        db.query(Textbook).filter(Textbook.id == textbook.id).delete(synchronize_session=False)
        db.query(Student).filter(Student.id == student.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
