import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.core.security import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("clave-segura-123")
    assert hashed != "clave-segura-123"
    assert verify_password("clave-segura-123", hashed)
    assert not verify_password("otra-clave", hashed)
    assert not verify_password("x", "hash-invalido")


def test_token_type_is_enforced() -> None:
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    refresh = create_token(user_id, org_id, "admin", "refresh")
    assert decode_token(refresh, "refresh") is not None
    assert decode_token(refresh, "access") is None  # un refresh no sirve como access


def test_expired_and_tampered_tokens_are_rejected() -> None:
    expired = jwt.encode(
        {"sub": "x", "type": "access", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_token(expired, "access") is None
    forged = jwt.encode(
        {"sub": "x", "type": "access"}, "otro-secreto-de-32-bytes-o-mas-xxxx", algorithm="HS256"
    )
    assert decode_token(forged, "access") is None
