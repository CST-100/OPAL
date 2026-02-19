"""User management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from opal.api.deps import CurrentUserId, DbSession, PaginationParams, RequiredAdmin, RequiredUser
from opal.core.audit import get_model_dict, log_create, log_delete, log_update
from opal.core.events import emit_user_activity
from opal.db.models import User

router = APIRouter()

# Timeout for considering a user "online" (30 seconds)
PRESENCE_TIMEOUT_SECONDS = 30


class UserCreate(BaseModel):
    """Schema for creating a user."""

    name: str
    email: EmailStr | None = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    name: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int
    name: str
    email: str | None
    is_active: bool
    is_admin: bool
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
    admin: RequiredAdmin,
) -> UserListResponse:
    """List all users. Requires admin."""
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
                is_admin=u.is_admin,
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
    admin: RequiredAdmin,
) -> UserResponse:
    """Create a new user. Requires admin."""
    user = User(name=user_in.name, email=user_in.email, is_admin=user_in.is_admin)
    db.add(user)
    db.flush()

    log_create(db, user, admin.id)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
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
        is_admin=user.is_admin,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    db: DbSession,
    user_id: int,
    user_in: UserUpdate,
    acting_user: RequiredUser,
) -> UserResponse:
    """Update a user.

    Non-admins can only edit their own name/email.
    Admins can edit any user, including is_admin and is_active.
    Cannot remove admin from the last admin user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    update_data = user_in.model_dump(exclude_unset=True)

    # Non-admin restrictions
    if not acting_user.is_admin:
        # Can only edit self
        if user_id != acting_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot edit other users",
            )
        # Can only change name and email
        allowed_fields = {"name", "email"}
        disallowed = set(update_data.keys()) - allowed_fields
        if disallowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot change fields: {', '.join(disallowed)}",
            )

    # Prevent removing last admin
    if "is_admin" in update_data and not update_data["is_admin"] and user.is_admin:
        admin_count = db.query(User).filter(
            User.is_admin == True, User.is_active == True  # noqa: E712
        ).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last admin",
            )

    old_data = get_model_dict(user)

    for field, value in update_data.items():
        setattr(user, field, value)

    db.flush()
    log_update(db, user, old_data, acting_user.id)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    db: DbSession,
    user_id: int,
    acting_user: RequiredUser,
) -> None:
    """Deactivate a user account.

    Non-admins can only deactivate themselves.
    Cannot deactivate the last admin.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Non-admins can only deactivate self
    if not acting_user.is_admin and user_id != acting_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot deactivate other users",
        )

    # Prevent deactivating last admin
    if user.is_admin:
        admin_count = db.query(User).filter(
            User.is_admin == True, User.is_active == True  # noqa: E712
        ).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last admin",
            )

    old_data = get_model_dict(user)
    user.is_active = False
    db.flush()
    log_update(db, user, old_data, acting_user.id)
    db.commit()


# ============ Presence Tracking ============


class HeartbeatRequest(BaseModel):
    """Heartbeat request to update presence."""

    activity: str | None = None  # e.g., "executing:123", "viewing:parts:45"


class HeartbeatResponse(BaseModel):
    """Heartbeat response."""

    user_id: int
    last_seen_at: str
    current_activity: str | None


class OnlineUserResponse(BaseModel):
    """Online user info."""

    id: int
    name: str
    last_seen_at: str
    current_activity: str | None
    is_online: bool


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    data: HeartbeatRequest,
    db: DbSession,
    user_id: CurrentUserId,
) -> HeartbeatResponse:
    """Update user presence (heartbeat).

    Call this periodically (every 10-15 seconds) to maintain online status.
    Include current activity to show what the user is doing.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)
    user.last_seen_at = now

    # Track activity change for event emission
    old_activity = user.current_activity
    if data.activity is not None:
        user.current_activity = data.activity

    db.commit()
    db.refresh(user)

    # Emit activity event if activity changed
    if data.activity is not None and data.activity != old_activity:
        await emit_user_activity(user.id, user.name, data.activity)

    return HeartbeatResponse(
        user_id=user.id,
        last_seen_at=user.last_seen_at.isoformat(),
        current_activity=user.current_activity,
    )


@router.get("/online", response_model=list[OnlineUserResponse])
async def get_online_users(
    db: DbSession,
) -> list[OnlineUserResponse]:
    """Get list of currently online users.

    Users are considered online if they've sent a heartbeat within the timeout window.
    """
    cutoff = datetime.now(timezone.utc).timestamp() - PRESENCE_TIMEOUT_SECONDS

    users = db.query(User).filter(User.is_active == True, User.last_seen_at.isnot(None)).all()  # noqa: E712

    result = []
    for user in users:
        if user.last_seen_at:
            is_online = user.last_seen_at.timestamp() > cutoff
            result.append(
                OnlineUserResponse(
                    id=user.id,
                    name=user.name,
                    last_seen_at=user.last_seen_at.isoformat(),
                    current_activity=user.current_activity,
                    is_online=is_online,
                )
            )

    # Sort by online status (online first) then by name
    result.sort(key=lambda x: (not x.is_online, x.name))
    return result


@router.get("/{user_id}/presence", response_model=OnlineUserResponse)
async def get_user_presence(
    user_id: int,
    db: DbSession,
) -> OnlineUserResponse:
    """Get presence status for a specific user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_online = False
    if user.last_seen_at:
        cutoff = datetime.now(timezone.utc).timestamp() - PRESENCE_TIMEOUT_SECONDS
        is_online = user.last_seen_at.timestamp() > cutoff

    return OnlineUserResponse(
        id=user.id,
        name=user.name,
        last_seen_at=user.last_seen_at.isoformat() if user.last_seen_at else "",
        current_activity=user.current_activity,
        is_online=is_online,
    )
