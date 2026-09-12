from app.admin_access import is_bot_admin, parse_admin_ids
from app.config import Settings


def test_parse_admin_ids():
    assert parse_admin_ids("1, 2;3") == {1, 2, 3}
    assert parse_admin_ids("") == set()


def test_is_bot_admin():
    s = Settings(
        admin_platform_user_ids="100,200",
        max_bot_token="x",
    )
    assert is_bot_admin(100, s) is True
    assert is_bot_admin(999, s) is False


def test_is_bot_admin_from_user_flag():
    class U:
        is_admin = True

    s = Settings(admin_platform_user_ids="", max_bot_token="x")
    assert is_bot_admin(999, s, user=U()) is True
    assert is_bot_admin(999, s, user=None) is False
