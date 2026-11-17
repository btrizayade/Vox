"""add content hash to pictograms

Revision ID: 3c85661c8030
Revises: e45c6f16bab5
Create Date: 2026-11-15 18:40:30.247223
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3c85661c8030"
down_revision: Union[str, Sequence[str], None] = "e45c6f16bab5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Adiciona o hash dos arquivos.
    op.add_column(
        "pictograms",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )

    # Atualiza a regra que diferencia pictogramas institucionais
    # dos personalizados.
    op.drop_constraint(
        "ck_pictograms_image_source_by_owner",
        "pictograms",
        type_="check",
    )

    op.create_check_constraint(
        "ck_pictograms_image_source_by_owner",
        "pictograms",
        "(profile_id IS NULL AND image_url IS NOT NULL "
        "AND storage_path IS NULL AND content_hash IS NULL) OR "
        "(profile_id IS NOT NULL AND image_url IS NULL "
        "AND storage_path IS NOT NULL AND content_hash IS NOT NULL)",
    )

    # Impede que o mesmo arquivo seja cadastrado duas vezes
    # no mesmo perfil.
    op.create_unique_constraint(
        "uq_pictograms_profile_content_hash",
        "pictograms",
        ["profile_id", "content_hash"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Remove as restricoes adicionadas.
    op.drop_constraint(
        "uq_pictograms_profile_content_hash",
        "pictograms",
        type_="unique",
    )

    op.drop_constraint(
        "ck_pictograms_image_source_by_owner",
        "pictograms",
        type_="check",
    )

    # Remove a coluna de hash.
    op.drop_column("pictograms", "content_hash")

    # Restaura a regra anterior.
    op.create_check_constraint(
        "ck_pictograms_image_source_by_owner",
        "pictograms",
        "(profile_id IS NULL AND image_url IS NOT NULL "
        "AND storage_path IS NULL) OR "
        "(profile_id IS NOT NULL AND image_url IS NULL "
        "AND storage_path IS NOT NULL)",
    )