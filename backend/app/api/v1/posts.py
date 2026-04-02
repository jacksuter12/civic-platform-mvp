import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from typing import Annotated

from app.api.deps import DB, FacilitatorUser, ParticipantUser
from app.core.audit import log_event
from app.models.audit import AuditEventType
from app.models.post import Post
from app.models.thread import Thread, ThreadStatus
from app.schemas.common import CamelBase, TimestampSchema, UUIDSchema
from app.schemas.user import UserPublic

router = APIRouter()

# Posts can only be created in OPEN or DELIBERATING phases
_POSTING_ALLOWED_STATUSES = {ThreadStatus.OPEN, ThreadStatus.DELIBERATING}


class PostCreate(BaseModel):
    thread_id: uuid.UUID
    body: str = Field(min_length=10, max_length=3000)
    parent_id: uuid.UUID | None = None


class PostRemove(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class PostOut(UUIDSchema, TimestampSchema):
    model_config = {"from_attributes": True}
    thread_id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str
    is_removed: bool
    author: UserPublic


@router.get("/thread/{thread_id}", response_model=list[PostOut])
async def list_posts(
    thread_id: uuid.UUID,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Post]:
    result = await db.execute(
        select(Post)
        .where(Post.thread_id == thread_id, Post.parent_id == None)
        .order_by(Post.created_at)
        .limit(limit)
        .offset(offset)
    )
    posts = list(result.scalars())
    for p in posts:
        await db.refresh(p, ["author"])
    return posts


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: PostCreate, user: ParticipantUser, db: DB
) -> Post:
    thread_result = await db.execute(
        select(Thread).where(Thread.id == payload.thread_id)
    )
    thread = thread_result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    if thread.status not in _POSTING_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Posting is not allowed in '{thread.status.value}' phase.",
        )

    if payload.parent_id:
        parent_result = await db.execute(
            select(Post).where(
                Post.id == payload.parent_id, Post.thread_id == payload.thread_id
            )
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent post not found.")

    post = Post(
        thread_id=payload.thread_id,
        author_id=user.id,
        parent_id=payload.parent_id,
        body=payload.body,
    )
    db.add(post)
    await db.flush()

    await log_event(
        db,
        event_type=AuditEventType.POST_CREATED,
        target_type="post",
        target_id=post.id,
        payload={"thread_id": str(post.thread_id)},
        actor_id=user.id,
    )

    await db.refresh(post, ["author"])
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_post(
    post_id: uuid.UUID, payload: PostRemove, facilitator: FacilitatorUser, db: DB
) -> None:
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")

    post.is_removed = True
    post.removal_reason = payload.reason

    await log_event(
        db,
        event_type=AuditEventType.POST_REMOVED,
        target_type="post",
        target_id=post.id,
        payload={"reason": payload.reason, "thread_id": str(post.thread_id)},
        actor_id=facilitator.id,
    )
