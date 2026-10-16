from dataclasses import dataclass


@dataclass
class User:
    username: str
    password_hash: str


USERS = {"ada": User("ada", "correct-hash")}


def verify_password(password: str, expected_hash: str) -> bool:
    return f"{password}-hash" == expected_hash


def authenticate_user(username: str, password: str) -> User | None:
    user = USERS.get(username)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        raise Exception("password verification failed")
    return user

