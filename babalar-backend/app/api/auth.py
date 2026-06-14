from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models.models import InviteCode, User
from jose import JWTError, jwt
import uuid

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    identifier: str  # email or username
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Validate invite code
    result = await db.execute(
        select(InviteCode).where(InviteCode.code == req.invite_code, InviteCode.is_active == True)
    )
    invite = result.scalar_one_or_none()
    if not invite or invite.use_count >= invite.max_uses:
        raise HTTPException(status_code=400, detail="Invalid or already used invite code")

    # Check for duplicate email/username
    existing = await db.execute(
        select(User).where((User.email == req.email) | (User.username == req.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email or username already taken")

    user = User(
        email=req.email,
        username=req.username,
        password_hash=hash_password(req.password),
        invite_code=req.invite_code,
    )
    db.add(user)
    invite.use_count += 1
    await db.commit()
    return {"message": "Registration successful"}


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(
            ((User.email == req.identifier) | (User.username == req.identifier)),
            User.is_active == True,
        )
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username/email or password")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(req.refresh_token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "username": current_user.username,
        "role": current_user.role,
        "is_admin": current_user.is_admin,
    }
