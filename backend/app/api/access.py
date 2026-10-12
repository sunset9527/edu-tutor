"""学生域资源的账号归属校验。"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.knowledge import WrongQuestion
from app.models.memory import Memory
from app.models.session import Session as TutorSession
from app.models.student import Student


def get_owned_student(db: Session, student_id: int, user_id: int) -> Student:
    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.user_id == user_id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    return student


def get_owned_memory(db: Session, memory_id: int, user_id: int) -> Memory:
    memory = (
        db.query(Memory)
        .join(Student, Student.id == Memory.student_id)
        .filter(Memory.id == memory_id, Student.user_id == user_id)
        .first()
    )
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory


def get_owned_wrong_question(
    db: Session, wrong_question_id: int, user_id: int
) -> WrongQuestion:
    wrong = (
        db.query(WrongQuestion)
        .join(Student, Student.id == WrongQuestion.student_id)
        .filter(WrongQuestion.id == wrong_question_id, Student.user_id == user_id)
        .first()
    )
    if not wrong:
        raise HTTPException(status_code=404, detail="错题不存在")
    return wrong


def get_owned_session(db: Session, session_id: int, user_id: int) -> TutorSession:
    tutor_session = (
        db.query(TutorSession)
        .join(Student, Student.id == TutorSession.student_id)
        .filter(TutorSession.id == session_id, Student.user_id == user_id)
        .first()
    )
    if not tutor_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return tutor_session
