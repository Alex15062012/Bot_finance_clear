from app.config import get_settings


def test_materials_deeplink():
    s = get_settings()
    # bot_username из env может быть пустым — проверяем формат
    assert "?start=" in s.materials_deeplink
    assert s.materials_start_payload in s.materials_deeplink
    if s.bot_username:
        assert s.question_deeplink.endswith("?start=question")
