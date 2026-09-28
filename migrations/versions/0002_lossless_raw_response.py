"""Preserve every Python raw-response code point in BYTEA."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Existing PostgreSQL text is valid Unicode without NUL. UTF-8 bytes are
    # identical under strict and surrogatepass; NULL remains NULL.
    op.alter_column(
        "extraction_runs", "raw_response", existing_type=sa.Text(),
        type_=sa.LargeBinary(), existing_nullable=True,
        postgresql_using="convert_to(raw_response, 'UTF8')",
    )


def downgrade():
    # PostgreSQL rejects NUL / surrogate bytes. In that case the transactional
    # migration aborts, retaining revision 0002 and ALL original evidence.
    # Never silently sanitize or drop data to make a downgrade succeed.
    op.alter_column(
        "extraction_runs", "raw_response", existing_type=sa.LargeBinary(),
        type_=sa.Text(), existing_nullable=True,
        postgresql_using="convert_from(raw_response, 'UTF8')",
    )
