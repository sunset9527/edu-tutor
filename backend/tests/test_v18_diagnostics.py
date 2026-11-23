"""v1.8 诊断题的受控知识来源契约。"""

import importlib


def test_diagnostic_question_model_requires_governed_knowledge_references():
    module = importlib.import_module("app.models.diagnostics")
    columns = set(module.DiagnosticQuestion.__table__.columns.keys())
    assert {"knowledge_version_id", "knowledge_point_id", "source_chunk_id", "status"} <= columns


def test_diagnostic_session_and_answers_preserve_fixed_evidence():
    module = importlib.import_module("app.models.diagnostics")
    assert {"student_id", "goal_version_id", "knowledge_version_id", "status"} <= set(
        module.DiagnosticSession.__table__.columns.keys()
    )
    assert {"session_id", "question_id", "raw_answer", "final_score", "final_score_reason", "confirmed_at"} <= set(
        module.DiagnosticAnswer.__table__.columns.keys()
    )


def test_diagnostic_results_and_plan_versions_record_explainable_evidence():
    diagnostics = importlib.import_module("app.models.diagnostics")
    learning = importlib.import_module("app.models.learning")
    assert {"session_id", "knowledge_point_id", "mastery", "evidence_status"} <= set(
        diagnostics.DiagnosticKnowledgeResult.__table__.columns.keys()
    )
    assert {"student_id", "goal_version_id", "knowledge_version_id", "evidence_snapshot"} <= set(
        learning.LearningPlanVersion.__table__.columns.keys()
    )
