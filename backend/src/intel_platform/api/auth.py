from __future__ import annotations
import logging
import os
import time
from collections import defaultdict
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

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300
_failed_logins: dict[str, list[float]] = defaultdict(list)


def check_login_rate_limit(client_ip: str) -> None:
    """Block login attempts after too many failures from the same IP."""
    now = time.time()
    # Prune old entries
    _failed_logins[client_ip] = [
        t for t in _failed_logins[client_ip]
        if now - t < LOGIN_LOCKOUT_SECONDS
    ]
    if len(_failed_logins[client_ip]) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
        )


def record_failed_login(client_ip: str) -> None:
    _failed_logins[client_ip].append(time.time())


def clear_failed_logins(client_ip: str) -> None:
    _failed_logins.pop(client_ip, None)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def _get_driver():
    from intel_platform.api.deps import get_neo4j_driver
    return get_neo4j_driver()


def _ensure_default_admin():
    """Create default admin user in Neo4j if no users exist."""
    driver = _get_driver()
    with driver.session() as session:
        result = session.run("MATCH (u:User) RETURN count(u) as cnt")
        count = result.single()["cnt"]
        if count == 0:
            from intel_platform.config import settings
            admin_password = settings.default_admin_password or "admin"
            require_secure = settings.require_secure_auth
            if require_secure and admin_password == "admin":
                raise RuntimeError(
                    "REQUIRE_SECURE_AUTH=true: set DEFAULT_ADMIN_PASSWORD (not the default 'admin') "
                    "before first boot so no default admin is seeded."
                )
            session.run(
                """
                CREATE (u:User {
                    username: $username,
                    hashed_password: $hashed_password,
                    role: $role,
                    created_at: datetime()
                })
                """,
                username="admin",
                hashed_password=_hash_password(admin_password),
                role="admin",
            )
            if admin_password == "admin":
                _logger.warning("SECURITY: Created default admin/admin user. Change password in production!")
            else:
                _logger.info("Created initial admin user from DEFAULT_ADMIN_PASSWORD.")


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


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires the authenticated user to have admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def register_user(username: str, password: str, role: str = "analyst") -> dict:
    driver = _get_driver()
    with driver.session() as session:
        # Check if user exists
        result = session.run("MATCH (u:User {username: $username}) RETURN u", username=username)
        if result.single():
            raise HTTPException(status_code=400, detail="Username already exists")

        session.run(
            """
            CREATE (u:User {
                username: $username,
                hashed_password: $hashed_password,
                role: $role,
                created_at: datetime()
            })
            """,
            username=username,
            hashed_password=_hash_password(password),
            role=role,
        )
    return {"username": username, "role": role}


def authenticate_user(username: str, password: str) -> dict | None:
    driver = _get_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH (u:User {username: $username}) RETURN properties(u) as props",
            username=username,
        )
        record = result.single()
        if not record:
            return None
        user = record["props"]
        if not verify_password(password, user["hashed_password"]):
            return None
        return user
