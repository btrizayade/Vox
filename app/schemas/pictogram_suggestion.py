from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class PictogramSuggestionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    category_id: int | None = Field(default=None, gt=0)

    other_category: str | None = Field(
        default=None,
        max_length=100,
    )

    description: str = Field(min_length=1)

    usage_context: str | None = None

    @field_validator("name", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Este campo nao pode ficar vazio.")

        return value

    @field_validator("other_category", "usage_context")
    @classmethod
    def validate_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_category(self):
        if (
            self.category_id is None
            and self.other_category is None
        ) or (
            self.category_id is not None
            and self.other_category is not None
        ):
            raise ValueError(
                "Informe uma categoria existente ou uma nova categoria."
            )

        return self


class PictogramSuggestionResponse(BaseModel):
    id: int
    name: str
    category_id: int | None
    other_category: str | None
    description: str
    usage_context: str | None

    status: Literal[
        "pending",
        "in_review",
        "approved",
        "rejected",
        "implemented",
    ]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)