from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from intel_platform.api.auth import (
    authenticate_user,
    check_login_rate_limit,
    clear_failed_logins,
    create_access_token,
    get_current_user,
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

    def model_post_init(self, __context) -> None:
        if len(self.username) < 3 or len(self.username) > 50:
            raise ValueError("Username must be 3-50 characters")
        if len(self.password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if self.role not in ("analyst", "admin"):
            raise ValueError("Role must be 'analyst' or 'admin'")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)

    user = authenticate_user(req.username, req.password)
    if not user:
        record_failed_login(client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    clear_failed_logins(client_ip)
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
