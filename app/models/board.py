
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Board(Base):
    __tablename__ = "boards"

    __table_args__ = (
        CheckConstraint(
            "board_type IN ('system', 'custom')",
            name="ck_boards_board_type",
        ),
        CheckConstraint(
            "(board_type = 'system' AND profile_id IS NULL) "
            "OR "
            "(board_type = 'custom' AND profile_id IS NOT NULL)",
            name="ck_boards_profile_by_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    board_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="custom",
        server_default=text("'custom'"),
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
