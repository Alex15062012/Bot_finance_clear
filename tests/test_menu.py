from app.scenarios.menu import parse_command


def test_parse_command_simple():
    assert parse_command("/start") == ("start", "")
    assert parse_command("/materials") == ("materials", "")


def test_parse_command_with_bot_suffix():
    assert parse_command("/help@id773272640550_bot") == ("help", "")


def test_parse_command_with_args():
    assert parse_command("/question срочно") == ("question", "срочно")


def test_parse_not_command():
    assert parse_command("просто текст") is None
