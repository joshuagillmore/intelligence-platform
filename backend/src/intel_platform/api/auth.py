from __future__ import annotations
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt

_logger = logging.getLogger(__name__)

# SECURITY: the JWT secret comes from Settings (JWT_SECRET). The built-in value
# is only for local development; see jwt_secret_problem for what production needs.
_DEFAULT_JWT_SECRET = "intel-platform-dev-secret-change-in-production"

# The built-in placeholder API key ships in .env.example, so anyone can read it.
# It must NEVER authenticate (as admin or otherwise) — see get_current_user.
_DEFAULT_API_KEY = "dev-api-key-change-in-production"

# HS256 is only as strong as its key, and PyJWT signs and verifies with an empty
# one. 32 bytes is the HMAC-SHA256 block-size guidance (RFC 7518 §3.2). An API
# key authenticates as admin, so it gets a floor too.
MIN_JWT_SECRET_BYTES = 32
MIN_API_KEY_BYTES = 16
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


def jwt_secret_problem(secret: str) -> str | None:
    """Why this JWT secret is unfit for a deployment, or None when it is fine.

    Judges the value itself. The old check compared against the literal default
    only, so a blank `JWT_SECRET=` passed REQUIRE_SECURE_AUTH while letting
    anyone mint admin tokens with an empty key. Length is counted in bytes: that
    is the key material HMAC sees.
    """
    if not secret:
        return "JWT_SECRET is blank"
    if secret == _DEFAULT_JWT_SECRET:
        return "JWT_SECRET is the built-in default"
    if len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        return f"JWT_SECRET is shorter than {MIN_JWT_SECRET_BYTES} bytes"
    return None


def api_key_problem(api_key: str) -> str | None:
    """Why this API key is unfit for a deployment, or None when it is fine.

    Blank is fine: it switches the API-key path off entirely. Any other value
    authenticates as admin, so it must be neither the published default nor short.
    """
    if not api_key:
        return None
    if api_key == _DEFAULT_API_KEY:
        return "API_KEY is the built-in default"
    if len(api_key.encode("utf-8")) < MIN_API_KEY_BYTES:
        return f"API_KEY is shorter than {MIN_API_KEY_BYTES} bytes"
    return None


def _jwt_secret() -> str:
    """The signing key in effect, read per call so boot checks and the signer agree."""
    from intel_platform.config import settings
    return settings.jwt_secret


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
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    """Verify JWT token OR legacy API key."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials

    # Support a legacy API key for programmatic / service-to-service callers.
    # SECURITY: the built-in default key must never authenticate — otherwise
    # anyone who reads .env.example gets admin on a naive deploy — so only a
    # non-default key works. The browser frontend does NOT use this path; it
    # authenticates with a JWT obtained from login.
    from intel_platform.config import settings
    if settings.api_key not in ("", _DEFAULT_API_KEY) and token == settings.api_key:
        return {"username": "api_key_user", "role": "admin"}

    # JWT token
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
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
