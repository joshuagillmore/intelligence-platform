from __future__ import annotations
import hmac
import logging
import time
from collections import OrderedDict
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

# Failures are counted per username and per client address. Per username is what
# stops guessing one account's password, and does not lock out everyone who
# shares an address (every client behind an untrusted proxy does). Per address,
# at a higher ceiling, is what stops one client spraying many usernames.
MAX_LOGIN_ATTEMPTS = 5
MAX_LOGIN_ATTEMPTS_PER_IP = 20
LOGIN_LOCKOUT_SECONDS = 300
# Every distinct spoofed address or invented username is a new key, so the table
# has a hard size; the least recently failed keys are dropped first.
_MAX_TRACKED_KEYS = 10_000
_failed_logins: OrderedDict[str, list[float]] = OrderedDict()


def _recent_failures(key: str, now: float) -> list[float]:
    times = [t for t in _failed_logins.get(key, ()) if now - t < LOGIN_LOCKOUT_SECONDS]
    if times:
        _failed_logins[key] = times
    else:
        _failed_logins.pop(key, None)
    return times


def check_login_rate_limit(client_ip: str, username: str | None = None) -> None:
    """Refuse a login attempt for a username, or from an address, that has failed too often."""
    now = time.time()
    too_many = len(_recent_failures(f"ip:{client_ip}", now)) >= MAX_LOGIN_ATTEMPTS_PER_IP
    if username is not None:
        too_many = too_many or len(_recent_failures(f"user:{username}", now)) >= MAX_LOGIN_ATTEMPTS
    if too_many:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
        )


def record_failed_login(client_ip: str, username: str | None = None) -> None:
    now = time.time()
    keys = [f"ip:{client_ip}"] + ([f"user:{username}"] if username is not None else [])
    for key in keys:
        _failed_logins.setdefault(key, []).append(now)
        _failed_logins.move_to_end(key)
    while len(_failed_logins) > _MAX_TRACKED_KEYS:
        _failed_logins.popitem(last=False)


def clear_failed_logins(client_ip: str, username: str | None = None) -> None:
    """Forget a username's failures after it signs in successfully.

    The address count is deliberately kept: clearing it on any success would let
    a client holding one valid account reset its budget between sprays.
    """
    if username is not None:
        _failed_logins.pop(f"user:{username}", None)


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


_BUILTIN_ADMIN_PASSWORD = "admin"


def _ensure_default_admin():
    """Seed the first admin if no users exist, then judge the stored admin passwords."""
    from intel_platform.config import settings

    driver = _get_driver()
    with driver.session() as session:
        result = session.run("MATCH (u:User) RETURN count(u) as cnt")
        count = result.single()["cnt"]
        if count == 0:
            admin_password = settings.default_admin_password or _BUILTIN_ADMIN_PASSWORD
            require_secure = settings.require_secure_auth
            if require_secure and admin_password == _BUILTIN_ADMIN_PASSWORD:
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
            if admin_password == _BUILTIN_ADMIN_PASSWORD:
                _logger.warning("SECURITY: Created default admin/admin user. Change password in production!")
            else:
                _logger.info("Created initial admin user from DEFAULT_ADMIN_PASSWORD.")

    # Judged on every boot, against what is stored. Seeding was the only check
    # before, so a deploy that once booted admin/admin stayed admin/admin under
    # REQUIRE_SECURE_AUTH=true: the flag guarded the config, not the account.
    _enforce_stored_admin_password(_admins_with_default_password())


def _admins_with_default_password() -> list[str]:
    """Usernames of admin accounts whose stored hash still verifies 'admin'."""
    driver = _get_driver()
    with driver.session() as session:
        records = list(session.run(
            "MATCH (u:User {role: 'admin'}) RETURN u.username AS username, u.hashed_password AS h"
        ))
    weak = []
    for record in records:
        try:
            if record["h"] and verify_password(_BUILTIN_ADMIN_PASSWORD, record["h"]):
                weak.append(record["username"])
        except ValueError:
            # A malformed hash cannot verify anything, 'admin' included.
            continue
    return weak


def _enforce_stored_admin_password(weak_usernames: list[str]) -> None:
    """Act on admin accounts still using the built-in password.

    Without REQUIRE_SECURE_AUTH: warn. With it: replace the password with
    DEFAULT_ADMIN_PASSWORD when the operator has set one (that is what setting
    it alongside the flag asks for), and otherwise refuse to boot. Takes the
    usernames explicitly so only the accounts found weak are ever written.
    """
    if not weak_usernames:
        return
    from intel_platform.config import settings

    names = ", ".join(weak_usernames)
    if not settings.require_secure_auth:
        _logger.warning(
            "SECURITY: admin account(s) %s still use the default password 'admin'. "
            "Change it (POST /api/auth/change-password) before any real deployment.",
            names,
        )
        return

    replacement = settings.default_admin_password
    if not replacement or replacement == _BUILTIN_ADMIN_PASSWORD:
        raise RuntimeError(
            f"REQUIRE_SECURE_AUTH=true but admin account(s) {names} still use the default "
            "password 'admin'. Set DEFAULT_ADMIN_PASSWORD to replace it at boot, or change it "
            "(POST /api/auth/change-password) with REQUIRE_SECURE_AUTH=false first."
        )
    for username in weak_usernames:
        set_password(username, replacement)
    _logger.warning(
        "SECURITY: replaced the default 'admin' password on admin account(s) %s with "
        "DEFAULT_ADMIN_PASSWORD (REQUIRE_SECURE_AUTH=true).",
        names,
    )


def set_password(username: str, new_password: str) -> bool:
    """Store a new password hash for `username`. False when no such user exists."""
    driver = _get_driver()
    with driver.session() as session:
        record = session.run(
            "MATCH (u:User {username: $username}) SET u.hashed_password = $h, "
            "u.password_changed_at = datetime() RETURN count(u) AS n",
            username=username, h=_hash_password(new_password),
        ).single()
    return bool(record and record["n"])


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
    # Constant-time: `==` stops at the first differing byte, so response timing
    # would reveal the key one prefix at a time.
    if settings.api_key not in ("", _DEFAULT_API_KEY) and hmac.compare_digest(
        token.encode("utf-8"), settings.api_key.encode("utf-8"),
    ):
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
    except jwt.PyJWTError:
        # Covers InvalidTokenError and InvalidKeyError alike: PyJWT >= 2.15
        # raises the latter for an empty HMAC key, which is not a token
        # problem but must still be a 401, never a 500.
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
        # Spend the same bcrypt check an existing user costs. Returning at once
        # made an unknown username measurably faster to refuse than a wrong
        # password, which told an attacker which usernames exist.
        verify_password(password, _dummy_hash())
        return None
    user = record["props"]
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    """A real bcrypt hash of nothing anyone knows, made once, at the default cost."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = _hash_password("no user has this password")
    return _DUMMY_HASH
