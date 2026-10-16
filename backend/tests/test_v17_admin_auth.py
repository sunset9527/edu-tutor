"""v1.7 最小管理员角色与权限边界。"""

import uuid
import subprocess
import sys

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core.database import SessionLocal
from app.main import app
from app.models.user import User


client = TestClient(app)


def test_registered_user_is_returned_with_user_role():
    username = f"v17-role-{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "test123"},
    )
    assert response.status_code == 200, response.text
    user_id = response.json()["user"]["id"]
    try:
        assert response.json()["user"]["role"] == "user"
        me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {response.json()['token']}"},
        )
        assert me.status_code == 200, me.text
        assert me.json()["role"] == "user"
    finally:
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()


def test_admin_dependency_rejects_user_and_accepts_admin():
    dependency = getattr(auth_api, "require_admin_user_id", None)
    assert callable(dependency), "应提供统一管理员依赖"

    protected_app = FastAPI()

    @protected_app.get("/protected")
    def protected(user_id: int = Depends(dependency)):
        return {"user_id": user_id}

    protected_client = TestClient(protected_app)
    ordinary = client.post(
        "/api/auth/register",
        json={
            "username": f"v17-user-{uuid.uuid4().hex[:10]}",
            "password": "test123",
        },
    ).json()
    admin = client.post(
        "/api/auth/register",
        json={
            "username": f"v17-admin-{uuid.uuid4().hex[:10]}",
            "password": "test123",
        },
    ).json()
    db = SessionLocal()
    db.query(User).filter(User.id == admin["user"]["id"]).update({"role": "admin"})
    db.commit()
    db.close()
    try:
        denied = protected_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {ordinary['token']}"},
        )
        assert denied.status_code == 403
        allowed = protected_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {admin['token']}"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["user_id"] == admin["user"]["id"]
    finally:
        db = SessionLocal()
        db.query(User).filter(
            User.id.in_([ordinary["user"]["id"], admin["user"]["id"]])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_set_user_role_cli_changes_only_valid_role():
    registered = client.post(
        "/api/auth/register",
        json={
            "username": f"v17-cli-{uuid.uuid4().hex[:10]}",
            "password": "test123",
        },
    ).json()
    user_id = registered["user"]["id"]
    username = registered["user"]["username"]
    try:
        promoted = subprocess.run(
            [sys.executable, "scripts/set_user_role.py", username, "admin"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert promoted.returncode == 0, promoted.stderr or promoted.stdout
        db = SessionLocal()
        assert db.get(User, user_id).role == "admin"
        db.close()

        invalid = subprocess.run(
            [sys.executable, "scripts/set_user_role.py", username, "owner"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert invalid.returncode != 0
        db = SessionLocal()
        assert db.get(User, user_id).role == "admin"
        db.close()
    finally:
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
