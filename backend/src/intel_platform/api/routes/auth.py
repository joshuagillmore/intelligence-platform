from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from intel_platform.api.auth import (
    authenticate_user,
    check_login_rate_limit,
    clear_failed_logins,
    create_access_token,
    record_failed_login,
    register_user,
    require_admin,
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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request):
    from intel_platform.api.middleware import client_ip
    ip = client_ip(request)
    check_login_rate_limit(ip)

    user = authenticate_user(req.username, req.password)
    if not user:
        record_failed_login(ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    clear_failed_logins(ip)
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
