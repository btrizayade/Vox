"""allow legacy custom pictograms without content hashes

Revision ID: 49c7a4d210ef
Revises: 3c85661c8030
Create Date: 2026-11-24

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "49c7a4d210ef"
down_revision: Union[str, Sequence[str], None] = "3c85661c8030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Align databases already at the former head with the relaxed check."""
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
        "AND storage_path IS NOT NULL)",
    )


def downgrade() -> None:
    """Keep the schema at the definition now represented by revision 3c."""
    # Revision 3c85661c8030 now has the same permissive check. Recreate it
    # here as well so both upgrade paths converge on the same parent schema.
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
        "AND storage_path IS NOT NULL)",
    )
