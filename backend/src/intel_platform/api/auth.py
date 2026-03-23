from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt

_logger = logging.getLogger(__name__)

# SECURITY: JWT secret must be set via environment in production.
# The default is only for local development convenience.
SECRET_KEY = os.environ.get("JWT_SECRET", "intel-platform-dev-secret-change-in-production")
_IS_DEFAULT_SECRET = SECRET_KEY == "intel-platform-dev-secret-change-in-production"
if _IS_DEFAULT_SECRET:
    _logger.warning("SECURITY: Using default JWT secret. Set JWT_SECRET env var in production.")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# Default admin user — in production, use a database
_users: dict[str, dict] = {
    "admin": {
        "username": "admin",
        "hashed_password": _hash_password("admin"),  # Change in production!
        "role": "admin",
    }
}


def create_access_token(username: str, role: str = "analyst") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    """Verify JWT token OR legacy API key."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials

    # Support legacy API key for backwards compatibility
    from intel_platform.config import settings
    if token == settings.api_key:
        return {"username": "api_key_user", "role": "admin"}

    # JWT token
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": payload.get("role", "analyst")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def register_user(username: str, password: str, role: str = "analyst") -> dict:
    if username in _users:
        raise HTTPException(status_code=400, detail="Username already exists")
    _users[username] = {
        "username": username,
        "hashed_password": _hash_password(password),
        "role": role,
    }
    return {"username": username, "role": role}


def authenticate_user(username: str, password: str) -> dict | None:
    user = _users.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user
