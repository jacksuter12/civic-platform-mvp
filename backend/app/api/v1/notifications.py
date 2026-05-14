import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationType,
)
from app.schemas.notification import (
    NotificationListOut,
    NotificationOut,
    PreferencesOut,
    PreferenceUpdate,
    UnreadCountOut,
)

router = APIRouter()


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    unread_only: Annotated[bool, Query()] = False,
) -> NotificationListOut:
    q = select(Notification).where(Notification.recipient_id == user.id)
    if unread_only:
        q = q.where(Notification.is_read == False)  # noqa: E712

    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar_one()

    q = q.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    notifications = [NotificationOut.model_validate(n) for n in result.scalars()]

    return NotificationListOut(
        notifications=notifications,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(user: CurrentUser, db: DB) -> UnreadCountOut:
    result = await db.execute(
        select(func.count()).where(
            Notification.recipient_id == user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    return UnreadCountOut(count=result.scalar_one())


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: Annotated[uuid.UUID, Path()],
    user: CurrentUser,
    db: DB,
) -> Notification:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(UTC)
        db.add(notif)
        await db.flush()
    return notif


@router.post("/mark-all-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user: CurrentUser, db: DB) -> None:
    result = await db.execute(
        select(Notification).where(
            Notification.recipient_id == user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    now = datetime.now(UTC)
    for notif in result.scalars():
        notif.is_read = True
        notif.read_at = now
        db.add(notif)
    await db.flush()


@router.get("/preferences", response_model=PreferencesOut)
async def get_preferences(user: CurrentUser, db: DB) -> PreferencesOut:
    result = await db.execute(
        select(NotificationPreference.notification_type).where(
            NotificationPreference.user_id == user.id
        )
    )
    disabled = list(result.scalars())
    return PreferencesOut(disabled=disabled)


@router.put("/preferences/{notification_type}", response_model=PreferencesOut)
async def set_preference(
    notification_type: Annotated[str, Path()],
    payload: PreferenceUpdate,
    user: CurrentUser,
    db: DB,
) -> PreferencesOut:
    if notification_type not in {t.value for t in NotificationType}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown notification type: {notification_type!r}",
        )

    existing_result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.notification_type == notification_type,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if payload.enabled:
        # Re-enable: delete the opt-out row if present
        if existing is not None:
            await db.delete(existing)
            await db.flush()
    else:
        # Disable: upsert an opt-out row
        if existing is None:
            pref = NotificationPreference(
                user_id=user.id,
                notification_type=notification_type,
            )
            db.add(pref)
            await db.flush()

    # Return fresh disabled list
    result = await db.execute(
        select(NotificationPreference.notification_type).where(
            NotificationPreference.user_id == user.id
        )
    )
    return PreferencesOut(disabled=list(result.scalars()))
