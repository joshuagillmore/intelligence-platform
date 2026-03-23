from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from intel_platform.api.auth import authenticate_user, create_access_token, register_user

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    # SECURITY: constrain registration inputs to prevent abuse
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
def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    user = register_user(req.username, req.password, req.role)
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )
