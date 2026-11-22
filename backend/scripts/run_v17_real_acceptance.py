"""在真实教材构建版本上运行 v1.7 的证据、纠错、回滚验收。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.knowledge import KnowledgePoint  # noqa: E402
from app.models.knowledge_governance import CorrectionTicket, KnowledgeReview, KnowledgeVersion, Textbook  # noqa: E402
from app.models.session import Message, Session as TutorSession  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.services.chat_orchestration import prepare_turn, record_answer_evidence  # noqa: E402
from app.services.knowledge.correction_service import accept_ticket, create_ticket  # noqa: E402
from app.services.knowledge.release_service import (  # noqa: E402
    activate_version,
    audit_version_consistency,
    rollback_textbook,
    submit_review,
)


ADMIN_ID = 594
TEXTBOOK_ID = 155
PARENT_VERSION_ID = 141
CORRECTION_REASON = "v1.7 真实教材验收：验证教材证据纠错、版本修订与回滚链路。"
REVIEW_TYPES = ["content", "formula", "knowledge_point", "difficulty", "prerequisite"]


def ensure_passed_review(db, version_id: int) -> int:
    review = (
        db.query(KnowledgeReview)
        .filter(
            KnowledgeReview.version_id == version_id,
            KnowledgeReview.conclusion == "passed",
        )
        .order_by(KnowledgeReview.id.desc())
        .first()
    )
    if review:
        return review.id
    review = submit_review(
        db,
        version_id=version_id,
        reviewer_id=ADMIN_ID,
        conclusion="passed",
        note="v1.7 real textbook acceptance review",
        items=[
            {"item_type": item_type, "target_type": "version", "conclusion": "pass"}
            for item_type in REVIEW_TYPES
        ],
    )
    return review.id


def ensure_student_and_message(db) -> tuple[Student, TutorSession, Message]:
    student = (
        db.query(Student)
        .filter(Student.user_id == ADMIN_ID, Student.name == "v1.7验收学生")
        .first()
    )
    if not student:
        student = Student(
            user_id=ADMIN_ID,
            name="v1.7验收学生",
            grade="二年级",
            subject="数学",
            level="基础",
        )
        db.add(student)
        db.commit()
        db.refresh(student)
    session = TutorSession(student_id=student.id, subject="数学", summary="v1.7 acceptance")
    db.add(session)
    db.flush()
    message = Message(
        session_id=session.id,
        role="assistant",
        content="这是用于 v1.7 真实教材证据与纠错验收的辅助回答。",
    )
    db.add(message)
    db.commit()
    db.refresh(session)
    db.refresh(message)
    return student, session, message


def run() -> dict:
    db = SessionLocal()
    try:
        textbook = db.get(Textbook, TEXTBOOK_ID)
        parent = db.get(KnowledgeVersion, PARENT_VERSION_ID)
        if not textbook or not parent:
            raise RuntimeError("验收前置条件不满足：真实教材或 v141 不存在")
        existing_ticket = (
            db.query(CorrectionTicket)
            .filter(CorrectionTicket.reason == CORRECTION_REASON)
            .order_by(CorrectionTicket.id.desc())
            .first()
        )
        if not existing_ticket and textbook.active_version_id != parent.id:
            raise RuntimeError("首次验收必须从真实教材 v141 的 active 状态开始")
        parent_audit = audit_version_consistency(db, parent.id)
        if parent_audit["issues"]:
            raise RuntimeError(f"父版本门禁不通过: {parent_audit['issues']}")

        sample_point = (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.version_id == parent.id)
            .order_by(KnowledgePoint.id)
            .first()
        )
        if not sample_point:
            raise RuntimeError("真实教材版本没有知识点")
        student, session, message = ensure_student_and_message(db)

        prepared = prepare_turn(student_id=student.id, user_message=sample_point.title)
        evidence = record_answer_evidence(
            student_id=student.id,
            session_id=session.id,
            assistant_message_id=message.id,
            prepared=prepared,
        )
        # record_answer_evidence 使用独立会话提交；当前会话此前已读过数据，
        # MySQL 的可重复读快照不会自动看到该提交。结束当前只读事务后，
        # 后续 create_ticket 才能读取这份已提交的证据账本。
        db.rollback()
        adopted = [row for row in evidence["knowledge_evidence"] if row.get("adopted")]
        if not adopted:
            raise RuntimeError("真实教材检索没有产生可采用的证据，不能继续纠错验收")

        ticket = existing_ticket
        if not ticket:
            point = db.get(KnowledgePoint, adopted[0]["knowledge_point_id"])
            ticket = create_ticket(
                db,
                submitted_by=ADMIN_ID,
                category="knowledge",
                assistant_message_id=message.id,
                proposed_value={
                    "content_md": (point.content_md or "")
                    + "\n\n<!-- v1.7 acceptance: source traceability verified. -->"
                },
                reason=CORRECTION_REASON,
                target_id=point.id,
            )
        if ticket.status != "applied":
            ticket = accept_ticket(
                db,
                ticket_id=ticket.id,
                admin_id=ADMIN_ID,
                note="v1.7 real textbook acceptance correction approved",
            )
        child = db.get(KnowledgeVersion, ticket.applied_version_id)
        if not child:
            raise RuntimeError("纠错未产出子版本")
        review_id = ensure_passed_review(db, child.id)
        child_audit = audit_version_consistency(db, child.id)
        if child_audit["issues"]:
            raise RuntimeError(f"纠错子版本门禁不通过: {child_audit['issues']}")

        if textbook.active_version_id != child.id:
            activate_version(
                db,
                version_id=child.id,
                admin_id=ADMIN_ID,
                expected_active_version_id=textbook.active_version_id,
            )
        # 已发布子版本回滚至历史父版本，再以受审核的归档版本重新激活。
        rollback_textbook(
            db,
            textbook_id=textbook.id,
            target_version_id=parent.id,
            admin_id=ADMIN_ID,
            expected_active_version_id=child.id,
        )
        activate_version(
            db,
            version_id=child.id,
            admin_id=ADMIN_ID,
            expected_active_version_id=parent.id,
        )
        db.refresh(textbook)
        return {
            "textbook_id": textbook.id,
            "parent_version_id": parent.id,
            "child_version_id": child.id,
            "active_version_id": textbook.active_version_id,
            "evidence_ledger_id": evidence["id"],
            "adopted_evidence_count": len(adopted),
            "correction_ticket_id": ticket.id,
            "correction_status": ticket.status,
            "review_id": review_id,
            "child_gate_ok": not child_audit["issues"],
            "rollback_and_reactivate": textbook.active_version_id == child.id,
        }
    finally:
        db.close()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
