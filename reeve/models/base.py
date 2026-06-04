from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    return str(uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseDoc(BaseModel):
    """Every Mongo document carries a string UUID `_id` and ISO8601 timestamps."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
    )

    id: str = Field(default_factory=new_id, alias="_id")
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
