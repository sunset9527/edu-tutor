"""登记一册真实教材并创建 v1.7 验收构建任务。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from starlette.datastructures import Headers, UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.knowledge.build_repository import create_build_task  # noqa: E402
from app.services.knowledge.textbook_service import store_textbook_upload  # noqa: E402


ADMIN_USERNAME = "v17-acceptance-admin"


async def run(pdf: Path) -> dict:
    if not pdf.is_file():
        raise FileNotFoundError(f"教材不存在: {pdf}")
    db = SessionLocal()
    handle = pdf.open("rb")
    try:
        admin = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if admin is None:
            admin = User(
                username=ADMIN_USERNAME,
                password_hash="acceptance-run-not-for-login",
                role="admin",
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
        upload = UploadFile(
            filename=pdf.name,
            file=handle,
            headers=Headers({"content-type": "application/pdf"}),
        )
        textbook, created = await store_textbook_upload(
            db,
            upload,
            metadata={
                "school_stage": "小学",
                "grade": "二年级",
                "subject": "数学",
                "publisher": "人民教育出版社",
                "edition": "2026",
                "volume": "下册",
                "source_note": "用户本地教材文件，仅用于 EduTutor 本地功能验收。",
                "license_note": "仅限本地学习与功能验证，不对外分发或发布教材内容。",
                "source_url": "",
            },
            uploaded_by=admin.id,
        )
        task, task_created = create_build_task(
            db,
            textbook_id=textbook.id,
            requested_by=admin.id,
            idempotency_key=f"v17-real-sample:{textbook.file_sha256}",
            build_config={"group_size": 12, "use_ocr": False},
        )
        return {
            "admin_id": admin.id,
            "textbook_id": textbook.id,
            "textbook_created": created,
            "task_id": task.id,
            "task_created": task_created,
            "page_count": textbook.page_count,
            "file_sha256": textbook.file_sha256,
        }
    finally:
        handle.close()
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.pdf)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
