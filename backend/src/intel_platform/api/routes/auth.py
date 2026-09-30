from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from intel_platform.api.auth import (
    authenticate_user,
    check_login_rate_limit,
    clear_failed_logins,
    create_access_token,
    get_current_user,
    record_failed_login,
    register_user,
    require_admin,
    set_password,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "analyst"

    # Validators (not model_post_init): a ValueError raised here is caught by
    # FastAPI's request-validation layer and returned as a clean 422, whereas a
    # raise in model_post_init escapes as an unhandled 500.
    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be 3-50 characters")
        return v

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v not in ("analyst", "admin"):
            raise ValueError("Role must be 'analyst' or 'admin'")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if v == "admin":
            raise ValueError("Password must not be the built-in default")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request):
    from intel_platform.api.middleware import client_ip
    ip = client_ip(request)
    check_login_rate_limit(ip, req.username)

    user = authenticate_user(req.username, req.password)
    if not user:
        record_failed_login(ip, req.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    clear_failed_logins(ip, req.username)
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest, admin: dict = Depends(require_admin)):
    """Create a new user. Requires admin authentication."""
    user = register_user(req.username, req.password, req.role)
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.post("/auth/change-password")
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Change the signed-in user's password.

    There was no way to change a password at all, so a seeded admin/admin could
    only be fixed by editing the database. The current password is required and
    throttled like a login, because this endpoint is otherwise a password oracle.
    """
    username = user["username"]
    if username == "api_key_user":
        raise HTTPException(status_code=400, detail="The API key identity has no password")

    from intel_platform.api.middleware import client_ip
    ip = client_ip(request)
    check_login_rate_limit(ip, username)
    if not authenticate_user(username, req.current_password):
        record_failed_login(ip, username)
        # 403, not 401: the frontend treats 401 as an expired session and signs out.
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    if req.new_password == req.current_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current one")

    if not set_password(username, req.new_password):
        raise HTTPException(status_code=404, detail="User not found")
    clear_failed_logins(ip, username)
    return {"status": "ok", "username": username}
