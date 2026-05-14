import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationType,
)

log = structlog.get_logger()


async def create_notification(
    db: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    notification_type: NotificationType,
    actor_id: uuid.UUID | None,
    target_type: str,
    target_id: uuid.UUID,
    community_id: uuid.UUID | None,
    headline: str,
    link: str | None = None,
) -> None:
    """
    Create a single in-app notification.

    Self-notifications are suppressed (recipient == actor → no-op).
    If the recipient has disabled this notification type, no-op.
    Does not catch exceptions — callers must wrap in try/except so that
    notification failures never break the triggering action.
    """
    if actor_id is not None and recipient_id == actor_id:
        return

    pref_result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == recipient_id,
            NotificationPreference.notification_type == notification_type.value,
        )
    )
    if pref_result.scalar_one_or_none() is not None:
        return

    notif = Notification(
        recipient_id=recipient_id,
        notification_type=notification_type.value,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        community_id=community_id,
        headline=headline,
        link=link,
        is_read=False,
    )
    db.add(notif)
    await db.flush()


async def get_community_slug(db: AsyncSession, community_id: uuid.UUID | None) -> str | None:
    """One indexed lookup. Returns None if community_id is None or not found."""
    if community_id is None:
        return None
    from app.models.community import Community  # local import avoids circular
    result = await db.execute(select(Community.slug).where(Community.id == community_id))
    return result.scalar_one_or_none()
