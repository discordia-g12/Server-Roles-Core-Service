from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_POSITION = 2_147_483_647


def _reject_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("name cannot be blank")
    return value


CategoryName = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$"), AfterValidator(_reject_blank)
]
Position = Annotated[int, Field(ge=0, le=MAX_POSITION)]


class CategoryCreate(BaseModel):
    name: CategoryName
    position: Position | None = None


class CategoryUpdate(BaseModel):
    name: CategoryName | None = None
    position: Position | None = None


class CategoryResponse(BaseModel):
    id: UUID
    server_id: UUID
    name: str
    position: int

    model_config = ConfigDict(from_attributes=True)
