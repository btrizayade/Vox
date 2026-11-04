
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class BoardItem(Base):
    __tablename__ = "board_items"

    __table_args__ = (
        UniqueConstraint(
            "board_id",
            "pictogram_id",
            name="uq_board_items_board_pictogram",
        ),
        UniqueConstraint(
            "board_id",
            "position",
            name="uq_board_items_board_position",
        ),
        CheckConstraint(
            "position >= 1",
            name="ck_board_items_position_positive",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
    )

    pictogram_id: Mapped[int] = mapped_column(
        ForeignKey("pictograms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
