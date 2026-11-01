
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProfileCreate(BaseModel):
    name: str


class ProfileUpdate(BaseModel):
    name: str


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    created_at: datetime
    updated_at: datetime
