
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Pictogram(Base):
    __tablename__ = "pictograms"

    __table_args__ = (
        CheckConstraint(
            "(profile_id IS NULL AND image_url IS NOT NULL "
            "AND storage_path IS NULL AND content_hash IS NULL) OR "
            "(profile_id IS NOT NULL AND image_url IS NULL "
            "AND storage_path IS NOT NULL)",
            name="ck_pictograms_image_source_by_owner",
        ),
        UniqueConstraint(
            "profile_id",
            "content_hash",
            name="uq_pictograms_profile_content_hash",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # URL externa dos pictogramas institucionais.
    # Sera nula para pictogramas personalizados.
    image_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Caminho do arquivo no Supabase Storage.
    # Sera preenchido somente para pictogramas personalizados.
    storage_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Hash SHA-256 do arquivo original para impedir duplicatas por perfil.
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # NULL indica um pictograma institucional.
    # Um ID indica o perfil proprietario.
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "profiles.id",
            name="fk_pictograms_profile_id_profiles",
        ),
        nullable=True,
        index=True,
    )

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
