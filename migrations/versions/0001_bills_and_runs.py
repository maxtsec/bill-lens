"""Bill identity and historical extraction attempts (hand-written migration)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bills",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_sha256", sa.CHAR(64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("processing_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("file_sha256", name="uq_bills_file_sha256"),
        sa.UniqueConstraint("storage_key", name="uq_bills_storage_key"),
        sa.CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="ck_bills_hash"),
        sa.CheckConstraint("storage_key ~ '^bills/[0-9a-f]{32}[.]pdf$'", name="ck_bills_storage_key"),
        sa.CheckConstraint("size_bytes > 0", name="ck_bills_size"),
        sa.CheckConstraint("processing_status IN ('processed', 'needs_review', 'failed')", name="ck_bills_status"),
    )
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("fields", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("fields_schema_version", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("review_flags", postgresql.JSONB(none_as_null=True), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("latency_ms", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], name="fk_runs_bill"),
        sa.CheckConstraint("provider ~ '[^[:space:]]'", name="ck_runs_provider"),
        sa.CheckConstraint("model ~ '[^[:space:]]'", name="ck_runs_model"),
        sa.CheckConstraint("prompt_version ~ '[^[:space:]]'", name="ck_runs_prompt_version"),
        sa.CheckConstraint("error_code IN ('rate_limited', 'timeout', 'refused', 'truncated', 'invalid_output', 'provider_error')", name="ck_runs_error_code"),
        sa.CheckConstraint("(fields IS NOT NULL) <> (error_code IS NOT NULL)", name="ck_runs_outcome"),
        sa.CheckConstraint("(fields IS NULL AND error_code <> 'invalid_output') OR raw_response IS NOT NULL", name="ck_runs_raw_response"),
        sa.CheckConstraint("jsonb_typeof(fields) = 'object'", name="ck_runs_fields_object"),
        sa.CheckConstraint("(fields IS NULL AND fields_schema_version IS NULL) OR (fields IS NOT NULL AND fields_schema_version IS NOT NULL AND fields_schema_version > 0)", name="ck_runs_schema_version"),
        sa.CheckConstraint("jsonb_typeof(review_flags) = 'array'", name="ck_runs_flags_array"),
        sa.CheckConstraint("status IN ('processed', 'needs_review', 'failed')", name="ck_runs_status"),
        sa.CheckConstraint("(status = 'failed') = (error_code IS NOT NULL)", name="ck_runs_failed"),
        sa.CheckConstraint("(status = 'needs_review' AND review_flags <> '[]'::jsonb) OR (status IN ('processed', 'failed') AND review_flags = '[]'::jsonb)", name="ck_runs_status_flags"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_runs_input_tokens"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_runs_output_tokens"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_runs_latency"),
    )
    op.create_index("ix_extraction_runs_bill_id", "extraction_runs", ["bill_id"])
    # Raw SQL updates must refresh timestamps too; ORM onupdate alone cannot.
    op.execute("""
        CREATE FUNCTION touch_bill_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER bills_updated_at BEFORE UPDATE ON bills
        FOR EACH ROW EXECUTE FUNCTION touch_bill_updated_at()
    """)


def downgrade():
    op.drop_table("extraction_runs")
    op.drop_table("bills")
    op.execute("DROP FUNCTION touch_bill_updated_at()")
