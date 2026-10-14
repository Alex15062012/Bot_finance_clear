from app.config import get_settings, link_opens_bot


def test_materials_deeplink():
    s = get_settings()
    # bot_username из env может быть пустым — проверяем формат
    assert "?start=" in s.materials_deeplink
    assert s.materials_start_payload in s.materials_deeplink
    if s.bot_username:
        assert s.question_deeplink.endswith("?start=question")
        assert link_opens_bot(s.materials_deeplink)


def test_link_without_bot_name_does_not_open_bot():
    assert link_opens_bot("https://max.ru/?start=materials") is False
    assert link_opens_bot("https://max.ru/id773272640550_bot?start=materials") is True
