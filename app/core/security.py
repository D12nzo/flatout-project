"""
Криптография: bcrypt-хэширование паролей и JWT.
Соответствует требованию X3 (хранение паролей в виде хэшей с индивидуальной солью —
bcrypt генерирует соль автоматически на каждый пароль).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt с дефолтными rounds (12) — индивидуальная соль на каждый пароль внутри hash-строки.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Возвращает bcrypt-хэш с солью."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Сравнивает пароль с хэшем в безопасном для тайминга режиме."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Хэш повреждён / неподдерживаемый формат — трактуем как несовпадение.
        return False


def create_access_token(subject: str, role: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    Выпуск JWT. В payload кладём id пользователя (sub) и его роль —
    этого достаточно для разграничения прав по требованию F2.
    """
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(tz=timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Возвращает payload или бросает JWTError."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "JWTError",
]
