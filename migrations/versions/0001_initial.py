"""Frozen schema v1; independent of future runtime model edits."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.Float(), primary_key=False, nullable=False),
        sa.Column("manifest", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("summary", sa.JSON(), primary_key=False, nullable=False),
    )
    op.create_table(
        "traces",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("workspace", sa.String(length=32), primary_key=False, nullable=False),
        sa.Column("created_at", sa.Float(), primary_key=False, nullable=False),
        sa.Column("version_ids", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("payload", sa.JSON(), primary_key=False, nullable=False),
    )
    op.create_index("ix_traces_workspace", "traces", ["workspace"], unique=False)
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("revision", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "workspace",
            sa.String(length=32),
            sa.ForeignKey("workspaces.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), primary_key=False, nullable=False),
        sa.Column("document_type", sa.String(length=50), primary_key=False, nullable=False),
        sa.Column("tags", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("active_version_id", sa.String(length=36), primary_key=False, nullable=True),
        sa.Column("latest_sequence", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("deleted", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("created_at", sa.Float(), primary_key=False, nullable=False),
    )
    op.create_index("ix_documents_workspace", "documents", ["workspace"], unique=False)
    op.create_table(
        "versions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("label", sa.String(length=80), primary_key=False, nullable=False),
        sa.Column("state", sa.String(length=20), primary_key=False, nullable=False),
        sa.Column("source_kind", sa.String(length=12), primary_key=False, nullable=False),
        sa.Column("source_locator", sa.String(length=500), primary_key=False, nullable=True),
        sa.Column("effective_date", sa.String(length=10), primary_key=False, nullable=True),
        sa.Column("uploaded_at", sa.Float(), primary_key=False, nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("extracted_sha256", sa.String(length=64), primary_key=False, nullable=True),
        sa.Column("pipeline_fingerprint", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column(
            "embedding_fingerprint", sa.String(length=300), primary_key=False, nullable=False
        ),
        sa.Column("embedding_dimension", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("storage_key", sa.String(length=80), primary_key=False, nullable=False),
        sa.Column("extracted_text", sa.Text(), primary_key=False, nullable=True),
        sa.Column("chunk_count", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("warnings", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("error_code", sa.String(length=50), primary_key=False, nullable=True),
        sa.UniqueConstraint("document_id", "sequence"),
    )
    op.create_index("ix_versions_document_id", "versions", ["document_id"], unique=False)
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("versions.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("text", sa.Text(), primary_key=False, nullable=False),
        sa.Column("section", sa.String(length=500), primary_key=False, nullable=True),
        sa.Column("page_start", sa.Integer(), primary_key=False, nullable=True),
        sa.Column("page_end", sa.Integer(), primary_key=False, nullable=True),
        sa.Column("start", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("end", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("token_count", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("content_sha256", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column(
            "embedding_fingerprint", sa.String(length=300), primary_key=False, nullable=False
        ),
        sa.Column(
            "embedding",
            sa.JSON().with_variant(Vector(384), "postgresql"),
            primary_key=False,
            nullable=False,
        ),
        sa.UniqueConstraint("version_id", "ordinal"),
    )
    op.create_index("ix_chunks_version_id", "chunks", ["version_id"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("versions.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("state", sa.String(length=20), primary_key=False, nullable=False),
        sa.Column("stage", sa.String(length=30), primary_key=False, nullable=False),
        sa.Column("attempts", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("lease_token", sa.String(length=36), primary_key=False, nullable=True),
        sa.Column("lease_until", sa.Float(), primary_key=False, nullable=True),
        sa.Column("done", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("total", sa.Integer(), primary_key=False, nullable=True),
        sa.Column("error_code", sa.String(length=50), primary_key=False, nullable=True),
        sa.Column("error_message", sa.String(length=500), primary_key=False, nullable=True),
        sa.Column("created_at", sa.Float(), primary_key=False, nullable=False),
        sa.UniqueConstraint("version_id"),
    )
    op.create_index("ix_jobs_state", "jobs", ["state"], unique=False)
    op.create_index("jobs_claim", "jobs", ["state", "lease_until"], unique=False)
    bind.execute(
        sa.text("INSERT INTO workspaces (id, revision) VALUES ('sample', 0), ('private', 0)")
    )


def downgrade():
    op.drop_table("jobs")
    op.drop_table("chunks")
    op.drop_table("versions")
    op.drop_table("documents")
    op.drop_table("workspaces")
    op.drop_table("traces")
    op.drop_table("experiments")
