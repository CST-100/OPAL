"""User management endpoints."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from opal.api.deps import DbSession, PaginationParams
from opal.db.models import User

router = APIRouter()


class UserCreate(BaseModel):
    """Schema for creating a user."""

    name: str
    email: EmailStr | None = None


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    name: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int
    name: str
    email: str | None
    is_active: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Schema for user list response."""

    items: list[UserResponse]
    total: int


@router.get("", response_model=UserListResponse)
async def list_users(
    db: DbSession,
    pagination: PaginationParams,
) -> UserListResponse:
    """List all users."""
    query = db.query(User).filter(User.is_active == True)  # noqa: E712
    total = query.count()
    users = query.offset(pagination.skip).limit(pagination.limit).all()

    return UserListResponse(
        items=[
            UserResponse(
                id=u.id,
                name=u.name,
                email=u.email,
                is_active=u.is_active,
                created_at=u.created_at.isoformat(),
                updated_at=u.updated_at.isoformat(),
            )
            for u in users
        ],
        total=total,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    db: DbSession,
    user_in: UserCreate,
) -> UserResponse:
    """Create a new user."""
    user = User(name=user_in.name, email=user_in.email)
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    db: DbSession,
    user_id: int,
) -> UserResponse:
    """Get a specific user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    db: DbSession,
    user_id: int,
    user_in: UserUpdate,
) -> UserResponse:
    """Update a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )
