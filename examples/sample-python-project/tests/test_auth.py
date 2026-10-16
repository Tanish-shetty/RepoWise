from store.auth import authenticate_user


def test_valid_login():
    assert authenticate_user("ada", "correct").username == "ada"


def test_unknown_user_is_rejected():
    assert authenticate_user("unknown", "anything") is None

