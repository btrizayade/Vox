
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.pictogram import PictogramResponse


class BoardItemCreate(BaseModel):
    pictogram_id: int = Field(gt=0)


class BoardItemResponse(BaseModel):
    id: int
    board_id: int
    pictogram_id: int
    position: int
    pictogram: PictogramResponse

    model_config = ConfigDict(from_attributes=True)


class BoardItemsReorder(BaseModel):
    item_ids: list[int] = Field(min_length=1)

    @field_validator("item_ids")
    @classmethod
    def validate_item_ids(cls, value: list[int]) -> list[int]:
        if any(item_id <= 0 for item_id in value):
            raise ValueError("Todos os IDs devem ser positivos.")

        if len(value) != len(set(value)):
            raise ValueError("A lista nao pode conter IDs duplicados.")

        return value
