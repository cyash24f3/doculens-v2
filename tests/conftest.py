import pytest

from doculens.config import Settings
from doculens.ingestion.worker import Worker
from doculens.retrieval.models import Models
from doculens.retrieval.search import Retriever
from doculens.storage.database import Database
from doculens.storage.repository import Repository


@pytest.fixture
def system(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/test.db",
        storage_dir=tmp_path / "files",
        model_backend="fixture",
        generation_mode="fixture",
        admin_token="test-admin-token-at-least-24-characters",
    )
    db = Database(settings)
    db.initialize_test_schema()
    repo = Repository(db, settings)
    models = Models(settings)
    worker = Worker(repo, models)
    yield settings, repo, models, worker, Retriever(settings, models)
    db.engine.dispose()


@pytest.fixture
def ingest(system):
    _, repo, _, worker, _ = system

    def load(
        text,
        title="Policy",
        scope="sample",
        document_id=None,
        filename="policy.md",
        mime="text/markdown",
    ):
        response = repo.upload(
            scope,
            text.encode() if isinstance(text, str) else text,
            filename,
            mime,
            title,
            document_id=document_id,
        )
        while worker.run_once():
            pass
        return response

    return load
