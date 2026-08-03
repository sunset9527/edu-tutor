"""v1.1 账号体系测试：注册/登录/me/学生关联"""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _uname() -> str:
    return f"u{uuid.uuid4().hex[:8]}"


def _register(name: str) -> dict:
    r = client.post("/api/auth/register", json={"username": name, "password": "test123"})
    assert r.status_code == 200, r.text
    return r.json()


def test_register_login_me():
    name = _uname()
    data = _register(name)
    token = data["token"]
    assert data["user"]["username"] == name

    r = client.post("/api/auth/login", json={"username": name, "password": "test123"})
    assert r.status_code == 200
    token = r.json()["token"]

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == name


def test_login_wrong_password():
    name = _uname()
    _register(name)
    r = client.post("/api/auth/login", json={"username": name, "password": "wrong"})
    assert r.status_code == 401


def test_register_duplicate():
    name = _uname()
    _register(name)
    r = client.post("/api/auth/register", json={"username": name, "password": "test123"})
    assert r.status_code == 400


def test_student_bound_to_user():
    """带 token 创建的学生挂到用户，列表可按 user_id 过滤"""
    name = _uname()
    data = _register(name)
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}
    uid = data["user"]["id"]

    r = client.post(
        "/api/students",
        json={"name": "账号关联测试", "grade": "初一", "subject": "数学"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == uid

    r2 = client.post(
        "/api/students", json={"name": "匿名测试", "grade": "初一", "subject": "数学"}
    )
    assert r2.status_code == 201
    assert r2.json()["user_id"] is None

    mine = client.get("/api/students", params={"user_id": uid}).json()
    assert all(s["user_id"] == uid for s in mine)
    assert any(s["name"] == "账号关联测试" for s in mine)
    assert not any(s["name"] == "匿名测试" for s in mine)
