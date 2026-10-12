"""v0.1 冒烟测试：健康检查 + MySQL 连通"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"username": f"smoke-{uuid.uuid4().hex[:10]}", "password": "test123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["mysql"] == "ok"


def test_create_and_list_student():
    headers = _auth_headers()
    r = client.post(
        "/api/students",
        json={"name": "小明", "grade": "初一", "subject": "数学", "level": "基础"},
        headers=headers,
    )
    assert r.status_code == 201
    student_id = r.json()["id"]

    r = client.get("/api/students", headers=headers)
    assert r.status_code == 200
    assert any(s["id"] == student_id for s in r.json())


@pytest.mark.skipif(
    not settings.llm_configured, reason="DEEPSEEK_API_KEY 未配置，跳过真实对话测试"
)
def test_chat_flow():
    """真实对话链路：创建学生 → 发起对话 → 返回回复（需要 DEEPSEEK_API_KEY 已配置）"""
    headers = _auth_headers()
    r = client.post(
        "/api/students",
        json={"name": "链路测试", "grade": "初一", "subject": "数学"},
        headers=headers,
    )
    assert r.status_code == 201
    student_id = r.json()["id"]

    r = client.post(
        "/api/chat",
        json={"student_id": student_id, "message": "一元一次方程怎么解？"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] > 0
    assert len(data["response"]) > 0
