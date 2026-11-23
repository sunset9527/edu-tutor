"""v1.8 可解释周学习计划生成。"""

from datetime import date, datetime
from math import ceil

from sqlalchemy.orm import Session

from app.models.diagnostics import DiagnosticKnowledgeResult, DiagnosticSession
from app.models.knowledge import KnowledgePoint, KnowledgePointLink, WrongQuestion
from app.models.learning import LearningGoal, LearningPlanItem, LearningPlanVersion
from app.models.memory import Memory, ReviewPlan


_MASTERY_RANK = {"不懂": 0, "基本会": 1, "熟练": 2, "精通": 3}


def resolve_learning_evidence(*, diagnostic: dict | None, memory: dict | None) -> dict:
    """解析诊断与长期记忆；冲突时保留可审计的选择理由。"""
    diagnostic = diagnostic or {}
    memory = memory or {}
    diagnostic_mastery = diagnostic.get("mastery")
    memory_mastery = memory.get("mastery")
    if not diagnostic_mastery and not memory_mastery:
        return {"mastery": None, "source": "none", "conflict": False, "reason": "暂无掌握证据"}
    if not diagnostic_mastery:
        return {"mastery": memory_mastery, "source": "memory", "conflict": False, "reason": "采用既有掌握记忆"}
    if not memory_mastery:
        return {"mastery": diagnostic_mastery, "source": "diagnostic", "conflict": False, "reason": "采用已确认诊断"}
    if diagnostic_mastery == memory_mastery:
        return {"mastery": diagnostic_mastery, "source": "consistent", "conflict": False, "reason": "诊断与既有记忆一致"}

    diagnostic_at = diagnostic.get("confirmed_at")
    memory_at = memory.get("observed_at")
    if diagnostic_at and memory_at:
        if diagnostic_at >= memory_at:
            return {"mastery": diagnostic_mastery, "source": "diagnostic", "conflict": True, "reason": "诊断与既有记忆冲突，采用较新的诊断"}
        return {"mastery": memory_mastery, "source": "memory", "conflict": True, "reason": "诊断与既有记忆冲突，采用较新的掌握记忆"}

    conservative = min((diagnostic_mastery, memory_mastery), key=lambda value: _MASTERY_RANK.get(value, -1))
    return {"mastery": conservative, "source": "conservative", "conflict": True, "reason": "诊断与既有记忆冲突且时间不可比较，采用保守掌握度"}


def generate_learning_plan(db: Session, *, student_id: int, goal_id: int, adjustment_reason: str = "initial") -> LearningPlanVersion:
    goal = db.get(LearningGoal, goal_id)
    if goal is None or goal.student_id != student_id or goal.current_version is None:
        raise ValueError("学习目标不存在")
    goal_version = goal.current_version
    session = db.query(DiagnosticSession).filter(DiagnosticSession.student_id == student_id, DiagnosticSession.goal_version_id == goal_version.id, DiagnosticSession.status == "submitted").order_by(DiagnosticSession.submitted_at.desc(), DiagnosticSession.id.desc()).first()
    if session is None:
        raise ValueError("请先完成当前目标版本的诊断")
    result_rows = db.query(DiagnosticKnowledgeResult).filter(DiagnosticKnowledgeResult.session_id == session.id).all()
    results = {row.knowledge_point_id: row for row in result_rows}
    memories = db.query(Memory).filter(Memory.student_id == student_id, Memory.status == "active").all()
    memory_by_kp = {row.knowledge_point_id: row for row in memories if row.knowledge_point_id is not None and ((row.structured_data or {}).get("predicate") == "掌握状态" or row.mastery != "不懂")}
    wrongs = db.query(WrongQuestion).filter(WrongQuestion.student_id == student_id, WrongQuestion.mastered == 0).all()
    wrong_counts: dict[int, int] = {}
    for row in wrongs:
        if row.knowledge_point_id is not None: wrong_counts[row.knowledge_point_id] = wrong_counts.get(row.knowledge_point_id, 0) + 1
    due_ids = {row.target_id for row in db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id, ReviewPlan.target_type == "knowledge_point", ReviewPlan.status == "pending", ReviewPlan.next_review_at <= datetime.now()).all()}
    target_ids = [row.knowledge_point_id for row in goal_version.targets]
    links = db.query(KnowledgePointLink).filter(KnowledgePointLink.link_type == "prerequisite").all()
    prereqs: dict[int, list[int]] = {}
    for link in links: prereqs.setdefault(link.target_kp_id, []).append(link.source_kp_id)
    ordered: list[int] = []; visited: set[int] = set()
    def visit(kp_id: int):
        if kp_id in visited: return
        visited.add(kp_id)
        for pre in sorted(prereqs.get(kp_id, [])): visit(pre)
        ordered.append(kp_id)
    for target_id in target_ids: visit(target_id)
    points = {row.id: row for row in db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(ordered), KnowledgePoint.version_id == goal_version.knowledge_version_id).all()}
    weeks = max(1, ceil((goal_version.target_date - date.today()).days / 7))
    capacity = weeks * goal_version.weekly_minutes
    plan = LearningPlanVersion(student_id=student_id, goal_id=goal.id, goal_version_id=goal_version.id, diagnostic_session_id=session.id, knowledge_version_id=goal_version.knowledge_version_id, adjustment_reason=adjustment_reason, total_available_minutes=capacity, evidence_snapshot={"diagnostic_session_id": session.id, "result_ids": [row.id for row in result_rows]})
    db.query(LearningPlanVersion).filter(
        LearningPlanVersion.goal_id == goal.id,
        LearningPlanVersion.status.in_(["current", "needs_adjustment"]),
    ).update({"status": "superseded"}, synchronize_session=False)
    db.add(plan); db.flush()
    scheduled = 0
    for sequence, kp_id in enumerate(ordered, 1):
        point = points.get(kp_id)
        if not point: continue
        result = results.get(kp_id); memory = memory_by_kp.get(kp_id)
        evidence = resolve_learning_evidence(
            diagnostic={"mastery": result.mastery, "confirmed_at": session.submitted_at} if result and result.mastery else None,
            memory={"mastery": memory.mastery, "observed_at": memory.updated_at or memory.last_reviewed_at or memory.created_at} if memory else None,
        )
        mastery = evidence["mastery"]
        is_target = kp_id in target_ids
        if not is_target and mastery == "熟练": continue
        minutes = {"基础": 30, "进阶": 45, "拔高": 60}.get(point.difficulty, 30)
        is_scheduled = scheduled + minutes <= capacity
        reasons = ["当前学习目标" if is_target else "知识图谱中的前置知识"]
        reasons.append("暂无诊断证据，建议补测或基础学习" if result is None else f"诊断掌握度为{result.mastery}")
        reasons.append(evidence["reason"])
        if wrong_counts.get(kp_id): reasons.append(f"存在 {wrong_counts[kp_id]} 道未掌握错题")
        if kp_id in due_ids: reasons.append("知识点复习已到期")
        if memory and result is None: reasons.append(f"既有掌握记忆为{memory.mastery}")
        db.add(LearningPlanItem(plan_version_id=plan.id, week_no=(scheduled // goal_version.weekly_minutes) + 1 if is_scheduled else None, sequence_no=sequence, knowledge_point_id=kp_id, estimated_minutes=minutes, recommendation_reasons=reasons, completion_condition="完成对应学习并通过后续练习确认", evidence_json={"diagnostic_result_id": result.id if result else None, "memory_id": memory.id if memory else None, "wrong_count": wrong_counts.get(kp_id, 0), "review_due": kp_id in due_ids, "resolution": evidence}, scheduled=is_scheduled))
        if is_scheduled: scheduled += minutes
    plan.scheduled_minutes = scheduled; plan.missing_minutes = max(0, sum(item.estimated_minutes for item in db.query(LearningPlanItem).filter(LearningPlanItem.plan_version_id == plan.id, LearningPlanItem.scheduled == False).all()))
    plan.status = "needs_adjustment" if plan.missing_minutes else "current"
    db.commit(); db.refresh(plan)
    return plan
