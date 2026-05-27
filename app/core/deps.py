"""
FastAPI dependencies: текущий пользователь и проверка ролей.
"""
from collections.abc import Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import JWTError, decode_access_token
from app.database import get_db
from app.models import User, UserRole

# tokenUrl должен совпадать с реальным эндпоинтом логина.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise credentials_exception from None

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        # Мягко удалённого / заблокированного пользователя пускать нельзя.
        raise credentials_exception
    return user


def require_roles(*allowed: UserRole):
    """
    Фабрика dependency, разрешающего доступ только указанным ролям (F2).

    Использование:
        @router.get("/admin-only", dependencies=[Depends(require_roles(UserRole.ADMIN))])
    """
    allowed_set = set(allowed)

    async def _checker(current: User = Depends(get_current_user)) -> User:
        if current.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения операции",
            )
        return current

    return _checker
