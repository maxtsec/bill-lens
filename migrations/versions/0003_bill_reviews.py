"""Keep human review revisions separate from extraction evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bill_reviews",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("fields", postgresql.JSONB(none_as_null=True), nullable=False),
        sa.Column("fields_schema_version", sa.Integer(), nullable=False),
        sa.Column("review_flags", postgresql.JSONB(none_as_null=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], name="fk_reviews_bill"),
        sa.ForeignKeyConstraint(["source_run_id"], ["extraction_runs.id"], name="fk_reviews_run"),
        sa.UniqueConstraint("bill_id", "revision", name="uq_reviews_revision"),
        sa.CheckConstraint("revision > 0", name="ck_reviews_revision"),
        sa.CheckConstraint("action IN ('confirmed', 'corrected')", name="ck_reviews_action"),
        sa.CheckConstraint("length(btrim(reviewer)) BETWEEN 1 AND 80", name="ck_reviews_reviewer"),
        sa.CheckConstraint("length(note) <= 2000", name="ck_reviews_note"),
        sa.CheckConstraint("jsonb_typeof(fields) = 'object'", name="ck_reviews_fields"),
        sa.CheckConstraint("jsonb_typeof(review_flags) = 'array'", name="ck_reviews_flags"),
        sa.CheckConstraint("fields_schema_version = 1", name="ck_reviews_schema"),
    )


def downgrade():
    # Explicit downgrade removes human review history; extraction tables remain.
    op.drop_table("bill_reviews")
