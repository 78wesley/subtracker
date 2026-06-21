"""Password hashing + authentication."""

from app.auth import hash_password, verify_password, create_user, authenticate


def test_hash_is_salted_and_verifies():
    h1 = hash_password("hunter2")
    h2 = hash_password("hunter2")
    assert h1 != h2                      # random salt per hash
    assert verify_password("hunter2", h1)
    assert verify_password("hunter2", h2)


def test_verify_rejects_wrong_password():
    h = hash_password("correct horse")
    assert not verify_password("battery staple", h)


def test_authenticate_roundtrip(db):
    create_user("alice", "s3cret-pw", global_role="user")
    user = authenticate("alice", "s3cret-pw")
    assert user is not None
    assert user["username"] == "alice"
    assert user["global_role"] == "user"


def test_authenticate_rejects_bad_password(db):
    create_user("bob", "right-pw")
    assert authenticate("bob", "wrong-pw") is None


def test_authenticate_unknown_user_returns_none(db):
    assert authenticate("ghost", "whatever") is None


def test_password_hash_never_stored_in_plaintext(db):
    create_user("carol", "plaintext-check")
    row = next(db["users"].rows_where("username = ?", ["carol"]))
    assert "plaintext-check" not in row["password_hash"]
    assert row["password_hash"].startswith("$2")  # bcrypt prefix
