"""Build the public sample with genuine pinned ONNX embeddings on Render Free.

The free filesystem is disposable. Administration is disabled on this public service.
The full persistent private-workspace deployment remains the separate Compose path.
"""

import json
import os
import sys
from pathlib import Path

from doculens.cli import migrate, seed
from doculens.config import Settings
from doculens.retrieval.models import Models
from doculens.storage.database import Database
from doculens.storage.repository import Repository


def cloud_settings() -> Settings:
    # Never read local .env or turn a public ephemeral instance into a private store.
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///.render-data/sample.db",
        storage_dir=Path(".render-data/files"),
        admin_token="",
        model_backend="onnx",
        cpu_threads=1,
        inference_concurrency=1,
        provider_concurrency=1,
        provider_retries=0,
        provider_repair_attempts=0,
    )
    if settings.generation_mode == "fixture":
        raise ValueError(
            "Render hosted build must use real provider answers or disabled generation"
        )
    return settings


def prepare():
    settings = cloud_settings()
    migrate(settings)
    models = Models(settings)
    models.initialize()
    database = Database(settings)
    seed(Repository(database, settings), models)
    # Warm and validate both artifacts before declaring the build successful.
    models.rerank("return policy", ["Products may be returned within 30 days."])
    print(json.dumps({"onnx_runtime": models.memory, "torch_imported": "torch" in sys.modules}))
    database.engine.dispose()


def serve():
    import uvicorn

    from doculens.api.app import create_app

    uvicorn.run(
        create_app(cloud_settings()),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        prepare()
