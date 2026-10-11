from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    position: int | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    position: int | None = None


class CategoryResponse(BaseModel):
    id: UUID
    server_id: UUID
    name: str
    position: int

    model_config = ConfigDict(from_attributes=True)
