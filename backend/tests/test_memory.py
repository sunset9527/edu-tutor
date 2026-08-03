"""v0.2 记忆引擎测试：提取 / 存储 / 检索 / 画像更新"""
import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.memory import Memory
from app.models.student import Student, StudentProfile
from app.services.memory.extractor import MemoryExtractor
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.storage import MemoryStorage

pytestmark = pytest.mark.skipif(
    not settings.llm_configured, reason="DEEPSEEK_API_KEY 未配置，跳过记忆引擎测试"
)


def _create_student(db) -> int:
    stu = Student(name="记忆测试", grade="初一", subject="数学")
    db.add(stu)
    db.commit()
    db.refresh(stu)
    return stu.id


def test_extractor_returns_json():
    """LLM 能从对话中提取结构化记忆"""
    extractor = MemoryExtractor()
    items = extractor.extract(
        user_message="我叫小明，我最怕解方程，移项总是搞错",
        ai_response="别担心，移项记住'变号'原则：移到等号另一边要变号。我们多练几道题。",
    )
    assert isinstance(items, list)
    assert len(items) >= 1, f"应提取到记忆，实际: {items}"
    assert all(
        item["type"] in {"semantic", "episodic", "procedural"} and item["object"]
        for item in items
    )


def test_storage_write_and_retrieve():
    """写入记忆后，向量检索能命中相关记忆"""
    db = SessionLocal()
    try:
        student_id = _create_student(db)
    finally:
        db.close()

    storage = MemoryStorage()
    count = storage.write(
        student_id,
        session_id=None,
        items=[
            {"type": "semantic", "predicate": "薄弱点", "object": "解方程移项", "confidence": 0.9},
            {"type": "semantic", "predicate": "学习偏好", "object": "喜欢生活例子", "confidence": 0.8},
        ],
    )
    assert count == 2

    retriever = MemoryRetriever()
    result = retriever.retrieve(student_id, "这个学生最怕什么数学内容？")
    assert any("解方程" in line for line in result["relevant_memories"]), result
    assert "薄弱点" in result["profile_summary"]


def test_profile_updated():
    """semantic 记忆写入后 student_profile 快照更新"""
    db = SessionLocal()
    try:
        student_id = _create_student(db)
    finally:
        db.close()

    MemoryStorage().write(
        student_id,
        session_id=None,
        items=[
            {"type": "semantic", "predicate": "薄弱点", "object": "函数图像", "confidence": 0.9},
            {"type": "semantic", "predicate": "已掌握", "object": "有理数运算", "confidence": 0.95},
        ],
    )

    db = SessionLocal()
    try:
        profile = db.get(StudentProfile, student_id)
        assert profile is not None
        assert "函数图像" in profile.weaknesses
        assert "有理数运算" in profile.strengths
    finally:
        db.close()


def test_conflict_resolution():
    """同一 predicate 新内容不同 → 旧记忆标 contradicted + 冲突记录"""
    db = SessionLocal()
    try:
        student_id = _create_student(db)
    finally:
        db.close()

    storage = MemoryStorage()
    storage.write(
        student_id, session_id=None,
        items=[{"type": "semantic", "predicate": "薄弱点", "object": "解方程移项", "confidence": 0.9}],
    )
    storage.write(
        student_id, session_id=None,
        items=[{"type": "semantic", "predicate": "薄弱点", "object": "二次函数", "confidence": 0.9}],
    )

    db = SessionLocal()
    try:
        active = (
            db.query(Memory)
            .filter(
                Memory.student_id == student_id,
                Memory.status == "active",
            )
            .all()
        )
        assert len(active) == 1, f"应只剩 1 条 active，实际 {len(active)}"
        assert "二次函数" in active[0].content
    finally:
        db.close()
