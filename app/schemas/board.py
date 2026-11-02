from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BoardCreate(BaseModel):
    profile_id: int
    name: str


class BoardUpdate(BaseModel):
    name: str


class BoardResponse(BaseModel):
    id: int
    profile_id: int
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)