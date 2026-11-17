from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PictogramSuggestion(Base):
    __tablename__ = "pictogram_suggestions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_review', 'approved', "
            "'rejected', 'implemented')",
            name="ck_pictogram_suggestions_valid_status",
        ),
        CheckConstraint(
            "(category_id IS NOT NULL AND other_category IS NULL) OR "
            "(category_id IS NULL AND other_category IS NOT NULL "
            "AND length(trim(other_category)) > 0)",
            name="ck_pictogram_suggestions_category_source",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"),
        nullable=True,
    )

    other_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    usage_context: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )