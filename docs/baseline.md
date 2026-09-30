# Milestone 0: baseline (2026-09-30)

The supplied workspace contained only an empty Git repository: no README, source, dependencies, tests, schema, entry points, or existing instructions. There were no baseline tests to run. No resume or other repository was changed.

Observed tools: uv 0.12.1, Docker client 29.6.2, Apple ARM64. `docker version` failed because Docker Desktop's daemon socket was unavailable. Remote deployment credentials were not supplied.

Decisions: new Python 3.12/FastAPI modular monolith, SQLAlchemy/Alembic, PostgreSQL/pgvector canonical deployment. SQLite is an explicit small-corpus local/CI adapter using exact NumPy cosine search; it is not described as pgvector verification. Jinja2 plus vanilla JavaScript. Database-backed ingestion jobs; a separate worker process. Fixture embeddings and scripted demo generation are named fixtures and excluded from model-quality claims.

The model cards and official documentation were inspected. MiniLM's 256 word-piece input limit motivates 180-token chunks with 32-token overlap rather than the suggested 300–500 starting range. Actual loaded limits are checked at runtime. Model commit revisions are pinned. No approximate vector index is included.
