from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_admin_login_and_messages():
    get_settings.cache_clear()
    settings = get_settings()
    client = TestClient(app)
    login = client.get("/admin/login")
    assert login.status_code == 200

    bad = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong"},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/admin/login",
        data={
            "username": settings.admin_username,
            "password": settings.admin_password,
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303

    messages = client.get("/admin/messages")
    assert messages.status_code == 200
    assert "new_subscriber_welcome" in messages.text

    commands = client.get("/admin/commands")
    assert commands.status_code == 200
    assert "/start" in commands.text or "start" in commands.text

    buttons = client.get("/admin/buttons")
    assert buttons.status_code == 200
    assert "menu_materials" in buttons.text
