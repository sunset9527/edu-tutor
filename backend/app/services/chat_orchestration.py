"""流式与非流式聊天共享的检索准备和证据账本。"""

from app.core.database import SessionLocal
from app.models.knowledge_governance import AnswerEvidenceLedger
from app.models.session import Message, Session as TutorSession
from app.services.knowledge.evidence import evaluate_knowledge_evidence
from app.services.knowledge.retriever import KnowledgeRetriever
from app.services.memory.retriever import MemoryRetriever


def _knowledge_context(knowledge_result: dict, evidence_gap: dict) -> str:
    lines = []
    source_index = 0
    for candidate in knowledge_result.get("candidates") or []:
        if not candidate.get("adopted"):
            continue
        source_index += 1
        page_range = candidate.get("page_range")
        page_label = (
            f"第 {page_range[0]}-{page_range[1]} 页" if page_range else "页码未知"
        )
        lines.append(
            f"[来源{source_index}] {candidate.get('title', '未命名知识点')}"
            f"（版本 v{candidate.get('version_no')}，{page_label}）\n"
            f"{candidate.get('content', '')}"
        )
    if evidence_gap.get("evidence_gap"):
        messages = "；".join(evidence_gap.get("messages") or [])
        lines.append(
            "【教材证据约束】"
            + messages
            + "回答时必须明确说明当前知识库缺口，可以给出通用建议，但不能声称建议来自指定教材。"
        )
    return "\n\n".join(lines)


def prepare_turn(
    *,
    student_id: int,
    user_message: str,
    memory_retriever=None,
    knowledge_retriever=None,
) -> dict:
    """运行一次共享检索，知识库故障降级为可解释 gap。"""
    memory_retriever = memory_retriever or MemoryRetriever()
    memory_result = memory_retriever.retrieve(student_id, user_message)
    memory_context = memory_retriever.build_injection_text(memory_result)
    knowledge_retriever = knowledge_retriever or KnowledgeRetriever()
    try:
        knowledge_result = knowledge_retriever.retrieve(student_id, user_message)
        evidence_gap = evaluate_knowledge_evidence(knowledge_result)
    except Exception as exc:  # noqa: BLE001
        knowledge_result = {
            "active_version_ids": [],
            "candidates": [],
            "retrieval_config": {},
            "error": str(exc),
        }
        evidence_gap = {
            "evidence_gap": True,
            "reasons": ["knowledge_retrieval_failed"],
            "messages": ["教材知识检索暂时不可用。"],
            "adopted_count": 0,
        }
    knowledge_context = _knowledge_context(knowledge_result, evidence_gap)
    context_parts = []
    if memory_context:
        context_parts.append(
            "以下是这个学生的长期记忆，请充分利用它提供个性化辅导：\n"
            + memory_context
        )
    if knowledge_context:
        context_parts.append("以下是本轮教材知识证据与使用约束：\n" + knowledge_context)
    return {
        "memory_result": memory_result,
        "knowledge_result": knowledge_result,
        "evidence_gap": evidence_gap,
        "system_context": "\n\n".join(context_parts),
    }


def _serialize_ledger(ledger: AnswerEvidenceLedger) -> dict:
    return {
        "id": ledger.id,
        "student_id": ledger.student_id,
        "session_id": ledger.session_id,
        "assistant_message_id": ledger.assistant_message_id,
        "knowledge_evidence": ledger.knowledge_evidence or [],
        "memory_evidence": ledger.memory_evidence or [],
        "retrieval_config": ledger.retrieval_config or {},
        "evidence_gap": ledger.evidence_gap or {},
        "created_at": ledger.created_at.isoformat() if ledger.created_at else None,
    }


def record_answer_evidence(
    *,
    student_id: int,
    session_id: int,
    assistant_message_id: int,
    prepared: dict,
    session_factory=SessionLocal,
) -> dict:
    """幂等写入与助手消息一对一的不可变证据快照。"""
    db = session_factory()
    try:
        existing = (
            db.query(AnswerEvidenceLedger)
            .filter(
                AnswerEvidenceLedger.assistant_message_id == assistant_message_id
            )
            .first()
        )
        if existing:
            return _serialize_ledger(existing)
        message = db.get(Message, assistant_message_id)
        tutor_session = db.get(TutorSession, session_id)
        if (
            not message
            or message.role != "assistant"
            or message.session_id != session_id
            or not tutor_session
            or tutor_session.student_id != student_id
        ):
            raise ValueError("助手消息、会话与学生不匹配")
        memory_result = prepared.get("memory_result") or {}
        memory_trace = memory_result.get("trace") or {}
        memory_evidence = [
            row
            for row in memory_trace.get("candidates", [])
            if row.get("selected")
        ]
        knowledge_result = prepared.get("knowledge_result") or {}
        ledger = AnswerEvidenceLedger(
            student_id=student_id,
            session_id=session_id,
            assistant_message_id=assistant_message_id,
            knowledge_evidence=knowledge_result.get("candidates") or [],
            memory_evidence=memory_evidence,
            retrieval_config={
                "knowledge": knowledge_result.get("retrieval_config") or {},
                "memory": {
                    key: value
                    for key, value in memory_trace.items()
                    if key != "candidates"
                },
            },
            evidence_gap=prepared.get("evidence_gap") or {},
        )
        db.add(ledger)
        db.commit()
        db.refresh(ledger)
        return _serialize_ledger(ledger)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_answer_evidence(db, assistant_message_id: int) -> dict | None:
    ledger = (
        db.query(AnswerEvidenceLedger)
        .filter(AnswerEvidenceLedger.assistant_message_id == assistant_message_id)
        .first()
    )
    return _serialize_ledger(ledger) if ledger else None
