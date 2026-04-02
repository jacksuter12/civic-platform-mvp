import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CamelBase(BaseModel):
    """Base schema that serializes to camelCase for mobile clients."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class UUIDSchema(CamelBase):
    id: uuid.UUID


class TimestampSchema(CamelBase):
    created_at: datetime


class Pagination(CamelBase):
    total: int
    limit: int
    offset: int
