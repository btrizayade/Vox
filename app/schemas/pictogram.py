from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PictogramResponse(BaseModel):
    id: int
    name: str
    image_url: str
    category_id: int
    category_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)