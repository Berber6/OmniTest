"""认证路由：/api/login 与 /api/me。"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import create_access_token, get_current_user, verify_password
from app.config import settings

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 password flow 登录，返回 JWT。"""
    if form.username != settings.admin_username or not verify_password(form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(form.username)
    return {"access_token": token, "token_type": "bearer", "username": form.username}


@router.get("/me")
async def me(current: str = Depends(get_current_user)):
    return {"username": current}
