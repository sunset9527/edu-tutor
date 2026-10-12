"""智能出题 + 错题本（v1.2 学习闭环）"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.access import get_owned_student, get_owned_wrong_question
from app.api.auth import require_current_user_id
from app.core.database import get_db
from app.core.llm import create_llm
from app.models.knowledge import KnowledgePoint, WrongQuestion
from app.models.memory import Memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["quiz"])

QUIZ_PROMPT = """你是中小学数学出题老师。基于以下知识点内容出练习题：

知识点：{title}
内容：{content_md}

请生成 {count} 道练习题，难度：{difficulty}。
要求：
1. 题型多样（选择/填空/解答）
2. 结合该知识点的核心概念与易错点
3. 每道题包含题干、答案、解析

只输出 JSON 数组，格式：
[{{"type": "选择|填空|解答", "question": "题干", "options": ["A. xx", "B. xx", "C. xx", "D. xx"], "answer": "答案", "analysis": "解析", "knowledge_point_id": {kp_id}}}]
选择填空题 options 可为空数组。"""


class QuizRequest(BaseModel):
    student_id: int
    subject: str = "数学"
    count: int = Field(default=5, ge=1, le=10)
    difficulty: str = "中等"


class WrongQuestionCreate(BaseModel):
    student_id: int
    question_text: str
    answer: str = ""
    analysis: str = ""
    error_type: str = "概念不清"
    knowledge_point_id: int | None = None


def _pick_knowledge_points(db: Session, student_id: int, subject: str, n: int = 3) -> list[KnowledgePoint]:
    """个性化选知识点：薄弱点记忆关联的优先，否则科目下随机"""
    # 1. 学生薄弱点关联的知识点
    weak_kps = (
        db.query(KnowledgePoint)
        .join(Memory, Memory.knowledge_point_id == KnowledgePoint.id)
        .filter(
            Memory.student_id == student_id,
            Memory.status == "active",
            Memory.memory_type == "semantic",
            KnowledgePoint.subject == subject,
        )
        .all()
    )
    # 2. 补足：科目下随机
    all_kps = db.query(KnowledgePoint).filter(KnowledgePoint.subject == subject).all()
    pool = weak_kps if weak_kps else all_kps
    return pool[:n] if pool else []


def _parse_questions(raw: str) -> list[dict]:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"出题 JSON 解析失败: {e}")
        return []


@router.post("/quiz/generate")
def generate_quiz(
    payload: QuizRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """智能出题：薄弱点知识点优先，LLM 生成题目"""
    get_owned_student(db, payload.student_id, user_id)
    kps = _pick_knowledge_points(db, payload.student_id, payload.subject, n=3)
    if not kps:
        raise HTTPException(status_code=404, detail="该科目暂无知识点")

    llm = create_llm(temperature=0.7, request_timeout=180)
    questions: list[dict] = []
    per_kp = max(1, payload.count // len(kps))
    for kp in kps:
        prompt = QUIZ_PROMPT.format(
            title=kp.title,
            content_md=kp.content_md[:800],
            count=per_kp,
            difficulty=payload.difficulty,
            kp_id=kp.id,
        )
        try:
            resp = llm.invoke(prompt)
            qs = _parse_questions(resp.content)
            for q in qs:
                q["knowledge_point_id"] = q.get("knowledge_point_id") or kp.id
                q["knowledge_point_title"] = kp.title
            questions.extend(qs)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"出题失败({kp.title}): {e}")
    return {"count": len(questions), "questions": questions[: payload.count]}


@router.post("/wrong-questions", status_code=201)
def record_wrong_question(
    payload: WrongQuestionCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """记录错题（智能出题做错 → 入错题本）"""
    get_owned_student(db, payload.student_id, user_id)
    wq = WrongQuestion(
        student_id=payload.student_id,
        knowledge_point_id=payload.knowledge_point_id,
        question_text=payload.question_text,
        answer=payload.answer,
        analysis=payload.analysis,
        error_type=payload.error_type,
        mastered=0,
    )
    db.add(wq)
    db.commit()
    db.refresh(wq)
    return {"ok": True, "id": wq.id}


@router.put("/wrong-questions/{wq_id}/mastered")
def mark_wrong_mastered(
    wq_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """标记错题已掌握"""
    wq = get_owned_wrong_question(db, wq_id, user_id)
    wq.mastered = 1
    db.commit()
    return {"ok": True, "id": wq_id, "mastered": 1}
