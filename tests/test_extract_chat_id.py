from app.max_api.types import extract_chat_id, extract_user


def test_extract_chat_id_top_level():
    assert extract_chat_id({"chat_id": 42}) == 42


def test_extract_chat_id_from_recipient():
    update = {"message": {"recipient": {"chat_id": -100}}}
    assert extract_chat_id(update) == -100


def test_extract_chat_id_missing():
    assert extract_chat_id({}) is None


def test_callback_user_is_the_clicker_not_the_bot_message_author():
    update = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb",
            "payload": "menu:question",
            "user": {"user_id": 5600001, "name": "Евгений", "is_bot": False},
        },
        "message": {
            "sender": {"user_id": 378258738, "name": "Помощник", "is_bot": True},
            "recipient": {"chat_id": 383694387, "chat_type": "dialog"},
        },
    }
    user = extract_user(update)
    assert user is not None
    assert user["user_id"] == 5600001
