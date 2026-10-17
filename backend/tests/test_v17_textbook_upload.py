"""v1.7 教材上传、去重与文件安全。"""

import uuid
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.knowledge_governance import Textbook
from app.models.user import User


client = TestClient(app)


def _pdf_bytes(text: str = "EduTutor v1.7 textbook") -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def _admin() -> tuple[int, dict[str, str]]:
    username = f"v17-upload-{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "test123"},
    ).json()
    db = SessionLocal()
    db.query(User).filter(User.id == response["user"]["id"]).update({"role": "admin"})
    db.commit()
    db.close()
    return response["user"]["id"], {
        "Authorization": f"Bearer {response['token']}"
    }


def _metadata(token: str) -> dict[str, str]:
    return {
        "school_stage": "初中",
        "grade": "初一",
        "subject": f"上传测试-{token}",
        "publisher": "测试出版社",
        "edition": "2026",
        "volume": "上册",
        "source_note": "自动化测试生成",
        "license_note": "仅用于自动化测试",
    }


def test_admin_uploads_pdf_and_duplicate_is_idempotent():
    user_id, headers = _admin()
    token = uuid.uuid4().hex[:8]
    storage_dir = Path(__file__).resolve().parents[1] / "data" / "test_textbooks" / token
    storage_dir.mkdir(parents=True, exist_ok=False)
    previous_storage = getattr(settings, "textbook_storage_dir", None)
    object.__setattr__(settings, "textbook_storage_dir", str(storage_dir))
    textbook_id = None
    try:
        payload = _pdf_bytes(token)
        first = client.post(
            "/api/admin/textbooks",
            data=_metadata(token),
            files={"file": ("教材.pdf", payload, "application/pdf")},
            headers=headers,
        )
        assert first.status_code == 201, first.text
        textbook_id = first.json()["id"]
        assert first.json()["created"] is True
        assert first.json()["page_count"] == 1
        assert Path(first.json()["file_path"]).is_absolute() is False

        duplicate = client.post(
            "/api/admin/textbooks",
            data=_metadata(token),
            files={"file": ("再次上传.pdf", payload, "application/pdf")},
            headers=headers,
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["id"] == textbook_id
        assert duplicate.json()["created"] is False
        db = SessionLocal()
        assert db.query(Textbook).filter(Textbook.id == textbook_id).count() == 1
        db.close()
    finally:
        if previous_storage is None:
            object.__delattr__(settings, "textbook_storage_dir")
        else:
            object.__setattr__(settings, "textbook_storage_dir", previous_storage)
        db = SessionLocal()
        if textbook_id:
            db.query(Textbook).filter(Textbook.id == textbook_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
        for child in storage_dir.iterdir():
            child.unlink()
        storage_dir.rmdir()
        if storage_dir.parent.exists() and not any(storage_dir.parent.iterdir()):
            storage_dir.parent.rmdir()


def test_upload_rejects_whitespace_only_source_metadata():
    user_id, headers = _admin()
    token = uuid.uuid4().hex[:8]
    storage_dir = Path(__file__).resolve().parents[1] / "data" / "test_textbooks" / token
    storage_dir.mkdir(parents=True, exist_ok=False)
    previous_storage = settings.textbook_storage_dir
    object.__setattr__(settings, "textbook_storage_dir", str(storage_dir))
    created_ids: list[int] = []
    try:
        metadata = _metadata(token)
        metadata["source_note"] = "   "
        response = client.post(
            "/api/admin/textbooks",
            data=metadata,
            files={"file": ("教材.pdf", _pdf_bytes(token), "application/pdf")},
            headers=headers,
        )
        if response.status_code in {200, 201}:
            created_ids.append(response.json()["id"])
        assert response.status_code == 422
        assert "来源" in response.json()["detail"]
    finally:
        object.__setattr__(settings, "textbook_storage_dir", previous_storage)
        db = SessionLocal()
        if created_ids:
            db.query(Textbook).filter(Textbook.id.in_(created_ids)).delete(
                synchronize_session=False
            )
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
        for child in storage_dir.iterdir():
            child.unlink()
        storage_dir.rmdir()
        if storage_dir.parent.exists() and not any(storage_dir.parent.iterdir()):
            storage_dir.parent.rmdir()
