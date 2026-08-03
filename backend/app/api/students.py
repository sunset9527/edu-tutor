"""学生相关路由（v1.1：账号关联 + 按用户过滤）"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.knowledge import WrongQuestion
from app.models.memory import Memory
from app.models.student import Student, StudentProfile
from app.api.auth import get_current_user_id
from app.schemas.student import StudentCreate, StudentOut

router = APIRouter(prefix="/api/students", tags=["students"])


@router.post("", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    user_id: int | None = Depends(get_current_user_id),
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
    user_id: int | None = None,
    db: Session = Depends(get_db),
):
    """学生列表（?user_id=N 按用户过滤；不带则返回全部，兼容演示）"""
    query = db.query(Student)
    if user_id is not None:
        query = query.filter(Student.user_id == user_id)
    return query.order_by(Student.id).all()


@router.get("/{student_id}", response_model=StudentOut)
def get_student(student_id: int, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    return student


@router.get("/{student_id}/profile")
def student_profile(student_id: int, db: Session = Depends(get_db)):
    """学生画像：薄弱点/优势/画像统计（前端雷达图数据）"""
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
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
def student_memories(student_id: int, db: Session = Depends(get_db)):
    """记忆列表（前端记忆库页 + 对话侧边栏）"""
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
def student_wrong_questions(student_id: int, db: Session = Depends(get_db)):
    """错题本"""
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