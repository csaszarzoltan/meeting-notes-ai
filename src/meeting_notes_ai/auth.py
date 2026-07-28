"""JWT authentication and authorization for MeetingNotesAI v0.2.0.

Endpoints:
    POST /api/v1/auth/signup  — Register a new user
    POST /api/v1/auth/login   — Login, receive JWT token
    GET  /api/v1/auth/me      — Get current user profile
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meeting_notes_ai.db.models import TeamMember, TeamRole, User
from meeting_notes_ai.db.session import get_db_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ── Configuration ───────────────────────────────────────────────────────────────

SECRET_KEY = "meeting-notes-ai-secret-key-change-in-production"  # TODO: move to env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Request/Response Schemas ────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    is_active: bool = True


# ── Service Layer ───────────────────────────────────────────────────────────────


async def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: Plaintext password.

    Returns:
        Bcrypt-hashed password string.
    """
    return pwd_context.hash(password)


async def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain: Plaintext password to verify.
        hashed: Bcrypt hash to check against.

    Returns:
        True if password matches, False otherwise.
    """
    return pwd_context.verify(plain, hashed)


async def create_access_token(user_id: str, expires_delta_hours: int = 24) -> str:
    """Create a signed JWT access token.

    Args:
        user_id: The user's unique ID to embed in the token.
        expires_delta_hours: Token expiry in hours (default 24).

    Returns:
        Encoded JWT string.
    """
    expires = datetime.now(timezone.utc) + timedelta(hours=expires_delta_hours)
    payload = {"sub": user_id, "exp": expires, "iat": datetime.now(timezone.utc)}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


async def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT string to decode.

    Returns:
        Dict with token payload (user_id, exp, etc.)

    Raises:
        HTTPException(401) if token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    authorization: str = Header(..., description="Bearer token"),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """FastAPI dependency: extract and validate current user from Bearer token.

    Usage:
        @router.get("/me")
        async def get_me(user: dict = Depends(get_current_user)):
            ...

    Returns:
        Dict with user_id, email, and other user fields.

    Raises:
        HTTPException(401) if token is missing or invalid.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[len("Bearer "):]
    payload = await decode_access_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_active": user.is_active,
    }


async def require_team_role(
    team_id: str,
    required_role: str,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> bool:
    """Check that the current user has the required role in a team.

    Args:
        team_id: Team identifier.
        required_role: One of 'admin', 'member', 'viewer'.

    Returns:
        True if user has required or higher role.

    Raises:
        HTTPException(403) if insufficient permissions.
    """
    role_hierarchy = {"viewer": 0, "member": 1, "admin": 2}
    required_level = role_hierarchy.get(required_role, 0)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user["user_id"],
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this team")

    user_level = role_hierarchy.get(membership.role.value, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient role. Required: {required_role}, have: {membership.role.value}",
        )

    return True


# ── Route Handlers ──────────────────────────────────────────────────────────────


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(
    request: SignupRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Register a new user and return JWT token."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == request.email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = await hash_password(request.password)
    user = User(
        email=request.email,
        hashed_password=hashed,
        display_name=request.display_name,
    )
    db.add(user)
    await db.flush()

    token = await create_access_token(user.id)
    expires = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return TokenResponse(access_token=token, expires_at=expires)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authenticate user and return JWT token."""
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    valid = await verify_password(request.password, user.hashed_password)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    token = await create_access_token(user.id)
    expires = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return TokenResponse(access_token=token, expires_at=expires)


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)) -> UserResponse:
    """Get current user profile."""
    return UserResponse(
        id=user["user_id"],
        email=user["email"],
        display_name=user.get("display_name"),
        is_active=user.get("is_active", True),
    )
