"""学生相关路由（v1.1：账号关联 + 按用户过滤）"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.knowledge import WrongQuestion
from app.models.memory import Memory
from app.models.student import Student, StudentProfile
from app.api.access import get_owned_student
from app.api.auth import require_current_user_id
from app.schemas.student import StudentCreate, StudentOut

router = APIRouter(prefix="/api/students", tags=["students"])


def summarize_review_plans(plans, now: datetime | None = None) -> dict[str, int]:
    """汇总复习计划；到期只包含当前时间之前的 pending 计划。"""
    now = now or datetime.now()
    pending = [p for p in plans if p.status == "pending"]
    return {
        "total": len(plans),
        "due": sum(1 for p in pending if p.next_review_at <= now),
        "done": sum(1 for p in plans if p.status == "done"),
        "pending": len(pending),
    }


@router.post("", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    data = payload.model_dump()
    data["user_id"] = user_id
    student = Student(**data)
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("", response_model=list[StudentOut])
def list_students(
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """当前账号的学生列表。"""
    return (
        db.query(Student)
        .filter(Student.user_id == user_id)
        .order_by(Student.id)
        .all()
    )


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    return get_owned_student(db, student_id, user_id)


@router.get("/{student_id}/profile")
def student_profile(
    student_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """学生画像：薄弱点/优势/画像统计（前端雷达图数据）"""
    student = get_owned_student(db, student_id, user_id)
    profile = db.get(StudentProfile, student_id)
    return {
        "id": student.id,
        "name": student.name,
        "grade": student.grade,
        "level": student.level,
        "weaknesses": (profile.weaknesses if profile else []) or [],
        "strengths": (profile.strengths if profile else []) or [],
    }


@router.get("/{student_id}/memories")
def student_memories(
    student_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """记忆列表（前端记忆库页 + 对话侧边栏）"""
    get_owned_student(db, student_id, user_id)
    rows = (
        db.query(Memory)
        .filter(Memory.student_id == student_id, Memory.status == "active")
        .order_by(Memory.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": m.id,
            "memory_type": m.memory_type,
            "content": m.content,
            "confidence": m.confidence,
            "strength": m.strength,
            "mastery": m.mastery,
            "knowledge_point_id": m.knowledge_point_id,
            "created_at": str(m.created_at),
        }
        for m in rows
    ]


@router.get("/{student_id}/wrong-questions")
def student_wrong_questions(
    student_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """错题本"""
    get_owned_student(db, student_id, user_id)
    rows = (
        db.query(WrongQuestion)
        .filter(WrongQuestion.student_id == student_id)
        .order_by(WrongQuestion.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": w.id,
            "question_text": w.question_text,
            "answer": w.answer,
            "analysis": w.analysis,
            "error_type": w.error_type,
            "mastered": w.mastered,
            "created_at": str(w.created_at),
        }
        for w in rows
    ]


@router.get("/{student_id}/report")
def student_report(
    student_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """学习报告汇总（v1.2）：记忆/复习/错题/画像"""
    from app.models.knowledge import WrongQuestion
    from app.models.memory import Memory, ReviewPlan
    from app.models.student import StudentProfile

    student = get_owned_student(db, student_id, user_id)

    memories = db.query(Memory).filter(
        Memory.student_id == student_id, Memory.status == "active"
    ).all()
    type_counts: dict[str, int] = {}
    for m in memories:
        type_counts[m.memory_type] = type_counts.get(m.memory_type, 0) + 1

    plans = db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).all()
    review_summary = summarize_review_plans(plans)

    wqs = db.query(WrongQuestion).filter(WrongQuestion.student_id == student_id).all()

    profile = db.get(StudentProfile, student_id)

    return {
        "student": {"id": student.id, "name": student.name, "grade": student.grade, "subject": student.subject},
        "memory_counts": type_counts,
        "memory_total": len(memories),
        "review": review_summary,
        "wrong_questions": {
            "total": len(wqs),
            "mastered": sum(1 for w in wqs if w.mastered),
            "unmastered": sum(1 for w in wqs if not w.mastered),
        },
        "weaknesses": profile.weaknesses if profile else [],
        "strengths": profile.strengths if profile else [],
    }

