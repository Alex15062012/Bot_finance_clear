from app.scenarios.menu import action_from_menu_button, parse_command


def test_parse_command_simple():
    assert parse_command("/start") == ("start", "")
    assert parse_command("/materials") == ("materials", "")


def test_parse_command_with_bot_suffix():
    assert parse_command("/help@id773272640550_bot") == ("help", "")


def test_parse_command_with_args():
    assert parse_command("/question срочно") == ("question", "срочно")


def test_parse_not_command():
    assert parse_command("просто текст") is None


def test_menu_button_action_ignores_title():
    assert action_from_menu_button("menu:materials", "menu_materials") == "materials"
    assert action_from_menu_button("menu:question", "menu_question") == "question"
    assert action_from_menu_button("menu:help", "menu_help") == "help"
    assert action_from_menu_button("/start", "menu_home") == "start"
    assert action_from_menu_button("/question подробнее", "menu_question") == "question"
    assert action_from_menu_button("menu:chat", "menu_chat") == "chat"
