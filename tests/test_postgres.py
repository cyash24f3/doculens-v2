import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text

from doculens.cli import migrate
from doculens.config import Settings
from doculens.ingestion.worker import Worker
from doculens.retrieval.models import Models
from doculens.retrieval.search import Retriever
from doculens.storage.database import Database
from doculens.storage.models import Base, uid
from doculens.storage.repository import Repository


@pytest.mark.postgres
def test_postgres_vector_migration_claim_replacement_and_deletion(tmp_path):
    url = os.getenv("DOCULENS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set DOCULENS_TEST_POSTGRES_URL to a disposable PostgreSQL database")
    schema = "test_" + uid().replace("-", "")
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        # Generated schema identifier, never user input; isolated from application tables.
        scoped = url + ("&" if "?" in url else "?") + f"options=-csearch_path%3D{schema},public"
        settings = Settings(
            _env_file=None,
            database_url=scoped,
            storage_dir=tmp_path / "files",
            model_backend="fixture",
        )
        db = Database(settings)
        Base.metadata.create_all(db.engine, checkfirst=False)
        db.seed_workspaces()
        repo = Repository(db, settings)
        models = Models(settings)
        worker = Worker(repo, models)
        retriever = Retriever(settings, models)
        item = repo.upload(
            "sample", b"E17 reset the Beacon device.", "guide.txt", "text/plain", "Guide"
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: worker.claim(), range(2)))
        assert sum(c is not None for c in claims) == 1
        worker.process(*next(c for c in claims if c))
        snapshot = repo.snapshot("sample")
        hit = retriever.search(snapshot, "E17", "dense", 5).hits[0]
        with db.transaction() as session:
            result = session.execute(
                text(
                    "SELECT vector_dims(embedding), 1 - (embedding <=> CAST(:vector AS vector)) FROM chunks"
                ),
                {"vector": str(models.encode(["E17"])[0])},
            ).one()
        assert result[0] == 384 and result[1] == pytest.approx(hit.score, abs=1e-6)
        new = repo.upload(
            "sample",
            b"E99 reset the Beacon device.",
            "guide.txt",
            "text/plain",
            "Guide",
            document_id=item["document_id"],
        )
        worker.run_once()
        assert repo.snapshot("sample").versions == (new["version_id"],)
        assert not retriever.search(repo.snapshot("sample"), "E17", "bm25", 5).hits
        repo.remove("sample", item["document_id"])
        assert not repo.snapshot("sample").evidence
        db.engine.dispose()
        # Alembic is exercised on a second isolated schema, including the vector extension.
        schema2 = schema + "_migration"
        with admin.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema2}"))
        try:
            migrate(
                settings.model_copy(
                    update={"database_url": url + f"?options=-csearch_path%3D{schema2},public"}
                )
            )
            engine = create_engine(url + f"?options=-csearch_path%3D{schema2},public")
            with engine.connect() as connection:
                assert (
                    connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                    == "0002"
                )
            engine.dispose()
        finally:
            with admin.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema2} CASCADE"))
    finally:
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()
