"""教材知识证据的确定性充分性判断。"""


GAP_MESSAGES = {
    "no_active_version": "当前学科和年级没有已激活的教材知识版本。",
    "below_similarity_threshold": "当前教材知识库没有达到相似度门槛的内容。",
    "missing_content": "命中的知识点缺少可用于回答的正文。",
    "legacy_provenance_gap": "命中内容来自历史导入知识，缺少可核验的教材页来源。",
    "knowledge_retrieval_failed": "教材知识检索暂时不可用。",
}


def evaluate_knowledge_evidence(retrieval: dict) -> dict:
    active_version_ids = retrieval.get("active_version_ids") or []
    candidates = retrieval.get("candidates") or []
    reasons: list[str] = []
    if not active_version_ids:
        reasons.append("no_active_version")
    elif not any(candidate.get("adopted") for candidate in candidates):
        if any(not str(candidate.get("content") or "").strip() for candidate in candidates):
            reasons.append("missing_content")
        else:
            reasons.append("below_similarity_threshold")
    elif any(
        candidate.get("adopted") and candidate.get("legacy")
        for candidate in candidates
    ):
        reasons.append("legacy_provenance_gap")
    return {
        "evidence_gap": bool(reasons),
        "reasons": reasons,
        "messages": [GAP_MESSAGES[reason] for reason in reasons],
        "adopted_count": sum(bool(row.get("adopted")) for row in candidates),
    }
