from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_REORDER_ITEMS = 500


def _reject_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("name cannot be blank")
    return value


CategoryName = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[^\x00]+$"), AfterValidator(_reject_blank)
]

class CategoryCreate(BaseModel):
    name: CategoryName

    model_config = ConfigDict(extra="forbid")


class CategoryUpdate(BaseModel):
    name: CategoryName | None = None

    model_config = ConfigDict(extra="forbid")


class CategoryReorder(BaseModel):
    category_ids: list[UUID] = Field(..., min_length=1, max_length=MAX_REORDER_ITEMS)

    model_config = ConfigDict(extra="forbid")


class CategoryResponse(BaseModel):
    id: UUID
    server_id: UUID
    name: str
    position: int

    model_config = ConfigDict(from_attributes=True)
