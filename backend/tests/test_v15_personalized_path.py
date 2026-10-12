"""v1.5 三学生个性化路径集成测试。"""

import uuid
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint, KnowledgePointLink, WrongQuestion
from app.models.memory import Memory, ReviewPlan
from app.models.student import Student
from app.services.knowledge.path_service import build_personalized_learning_path


def test_same_target_produces_evidence_based_different_paths():
    db = SessionLocal()
    token = uuid.uuid4().hex[:10]
    student_ids: list[int] = []
    kp_ids: list[int] = []
    try:
        prerequisites = [
            KnowledgePoint(
                subject="数学",
                grade="初一",
                title="整数运算",
                slug=f"v15-integer-{token}",
                difficulty="基础",
            ),
            KnowledgePoint(
                subject="数学",
                grade="初一",
                title="等式性质",
                slug=f"v15-equality-{token}",
                difficulty="基础",
            ),
        ]
        target = KnowledgePoint(
            subject="数学",
            grade="初一",
            title="一元一次方程",
            slug=f"v15-equation-{token}",
            difficulty="进阶",
        )
        db.add_all([*prerequisites, target])
        db.flush()
        kp_ids = [kp.id for kp in prerequisites] + [target.id]
        db.add_all(
            [
                KnowledgePointLink(
                    source_kp_id=prerequisites[0].id,
                    target_kp_id=target.id,
                    link_type="prerequisite",
                ),
                KnowledgePointLink(
                    source_kp_id=prerequisites[1].id,
                    target_kp_id=target.id,
                    link_type="prerequisite",
                ),
            ]
        )
        students = [
            Student(name=f"路径甲-{token}", grade="初一", subject="数学"),
            Student(name=f"路径乙-{token}", grade="初一", subject="数学"),
            Student(name=f"路径丙-{token}", grade="初一", subject="数学"),
        ]
        db.add_all(students)
        db.flush()
        student_ids = [student.id for student in students]

        # 甲已熟练整数运算，只需补等式性质。
        db.add(
            Memory(
                student_id=students[0].id,
                memory_type="semantic",
                content="掌握状态：整数运算（熟练）",
                structured_data={"predicate": "掌握状态", "object": "整数运算"},
                knowledge_point_id=prerequisites[0].id,
                mastery="熟练",
                status="active",
            )
        )
        # 乙已熟练等式性质，但整数运算仍有错题且复习到期。
        db.add(
            Memory(
                student_id=students[1].id,
                memory_type="semantic",
                content="掌握状态：等式性质（熟练）",
                structured_data={"predicate": "掌握状态", "object": "等式性质"},
                knowledge_point_id=prerequisites[1].id,
                mastery="熟练",
                status="active",
            )
        )
        db.add(
            WrongQuestion(
                student_id=students[1].id,
                knowledge_point_id=prerequisites[0].id,
                question_text="-2+5=?",
                mastered=0,
            )
        )
        db.add(
            ReviewPlan(
                student_id=students[1].id,
                target_type="knowledge_point",
                target_id=prerequisites[0].id,
                interval_days=1,
                next_review_at=datetime.now() - timedelta(hours=1),
                status="pending",
            )
        )
        db.commit()

        paths = [
            build_personalized_learning_path(db, student.id, target.id)
            for student in students
        ]

        path_ids = [[step["id"] for step in result["path"]] for result in paths]
        assert path_ids[0] == [prerequisites[1].id, target.id]
        assert path_ids[1] == [prerequisites[0].id, target.id]
        assert set(path_ids[2][:-1]) == {kp.id for kp in prerequisites}
        assert len({tuple(ids) for ids in path_ids}) == 3

        second_first = paths[1]["path"][0]
        assert second_first["wrong_count"] == 1
        assert second_first["review_due"] is True
        assert "存在 1 道未掌握错题" in second_first["reasons"]
        assert paths[0]["evidence_gap"] is None
    finally:
        if kp_ids:
            db.query(ReviewPlan).filter(
                ReviewPlan.target_type == "knowledge_point",
                ReviewPlan.target_id.in_(kp_ids),
            ).delete(synchronize_session=False)
            db.query(WrongQuestion).filter(
                WrongQuestion.knowledge_point_id.in_(kp_ids)
            ).delete(synchronize_session=False)
            db.query(Memory).filter(Memory.student_id.in_(student_ids)).delete(
                synchronize_session=False
            )
            db.query(KnowledgePointLink).filter(
                KnowledgePointLink.target_kp_id.in_(kp_ids)
            ).delete(synchronize_session=False)
            db.query(Student).filter(Student.id.in_(student_ids)).delete(
                synchronize_session=False
            )
            db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(kp_ids)).delete(
                synchronize_session=False
            )
            db.commit()
        db.close()
