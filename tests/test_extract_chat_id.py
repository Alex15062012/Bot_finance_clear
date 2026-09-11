from app.max_api.types import extract_chat_id


def test_extract_chat_id_top_level():
    assert extract_chat_id({"chat_id": 42}) == 42


def test_extract_chat_id_from_recipient():
    update = {"message": {"recipient": {"chat_id": -100}}}
    assert extract_chat_id(update) == -100


def test_extract_chat_id_missing():
    assert extract_chat_id({}) is None
