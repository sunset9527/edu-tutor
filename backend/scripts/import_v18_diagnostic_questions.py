"""导入经人工审校的 v1.8 诊断题 JSON；不在运行时生成题目。"""
import argparse, json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.database import SessionLocal
from app.models.diagnostics import DiagnosticQuestion
from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import KnowledgeVersion, Textbook

def run(path: Path, version_id: int = 142) -> dict:
    rows=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows,list) or not rows: raise ValueError("题目文件必须是非空 JSON 数组")
    db=SessionLocal()
    try:
        version=db.get(KnowledgeVersion,version_id)
        textbook=db.query(Textbook).filter(Textbook.active_version_id==version_id).one_or_none()
        if not version or not textbook: raise ValueError("指定知识版本不是当前 active 版本")
        created=0
        for row in rows:
            review_mode=row.get("review_mode", "human_review")
            if review_mode == "human_review":
                if row.get("reviewed_by") is None or not row.get("review_note"):
                    raise ValueError("人工审校题目必须带 reviewed_by 和 review_note")
            elif review_mode == "ai_pre_review":
                ai_review=row.get("ai_review") or {}
                if not row.get("ai_model") or ai_review.get("decision") != "pass":
                    raise ValueError("AI 初审题目必须记录 ai_model 且 ai_review.decision 为 pass")
            else:
                raise ValueError("review_mode 只能是 human_review 或 ai_pre_review")
            point=db.get(KnowledgePoint,row.get("knowledge_point_id"))
            if not point or point.version_id!=version_id or point.provenance_gap or not point.source_chunk_id:
                raise ValueError("题目知识点必须属于目标版本且有来源块")
            existing=db.query(DiagnosticQuestion).filter(DiagnosticQuestion.knowledge_version_id==version_id,DiagnosticQuestion.knowledge_point_id==point.id,DiagnosticQuestion.stem==row.get("stem")).first()
            if existing: continue
            db.add(DiagnosticQuestion(knowledge_version_id=version_id,knowledge_point_id=point.id,source_chunk_id=point.source_chunk_id,question_type=row["question_type"],difficulty=row.get("difficulty",point.difficulty),stem=row["stem"],options_json=row.get("options"),answer_key_json=row.get("answer_key"),rubric_json=row.get("rubric"),max_score=row.get("max_score",1),status="published",reviewed_by=row.get("reviewed_by"),review_note=row.get("review_note"),review_mode=review_mode,ai_model=row.get("ai_model"),ai_review_json=row.get("ai_review"),ai_reviewed_at=datetime.now() if review_mode == "ai_pre_review" else None)); created+=1
        db.commit(); return {"version_id":version_id,"created":created,"skipped":len(rows)-created}
    finally: db.close()
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("file",type=Path);p.add_argument("--version-id",type=int,default=142);a=p.parse_args();print(json.dumps(run(a.file,a.version_id),ensure_ascii=False))
