from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BoardCreate(BaseModel):
    profile_id: int = Field(gt=0)
    name: str = Field(
        min_length=1,
        max_length=255,
    )


class BoardUpdate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )


class BoardResponse(BaseModel):
    id: int
    profile_id: int | None
    name: str
    board_type: Literal["system", "custom"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)