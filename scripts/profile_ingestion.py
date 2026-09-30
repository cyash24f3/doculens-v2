"""Measure real stages on safe fixtures in a fresh isolated database."""

import json
import tempfile
from pathlib import Path

import numpy as np
import psutil

from doculens.cli import migrate
from doculens.config import Settings
from doculens.ingestion.worker import Worker
from doculens.retrieval.models import Models
from doculens.storage.database import Database
from doculens.storage.repository import Repository

settings = Settings()
models = Models(settings)
models.initialize()
models.encode(["Warm-up text."])
records = []
with tempfile.TemporaryDirectory(prefix="doculens-profile-") as directory:
    temp = Path(directory)
    settings = settings.model_copy(
        update={"database_url": f"sqlite:///{temp}/profile.db", "storage_dir": temp / "files"}
    )
    migrate(settings)
    repo = Repository(Database(settings), settings)
    worker = Worker(repo, models)
    for i in range(3):
        for path in [
            Path("data/sample/returns.md"),
            Path("data/public/python-venv.txt"),
            Path("data/sample/beacon-quickstart.pdf"),
        ]:
            raw = path.read_bytes()
            item = repo.upload("private", raw, path.name, "application/octet-stream", path.stem)
            # Delete each completed source after measuring so repetitions are actual ingestion.
            worker.run_once()
            job = repo.job("private", item["job_id"])
            assert job["state"] == "completed", job
            records.append(
                {"source": str(path), "bytes": len(raw), "iteration": i, "timings": job["timings"]}
            )
            repo.remove("private", item["document_id"])
    repo.db.engine.dispose()
report = {
    "requests": len(records),
    "failures": 0,
    "conditions": "warm encoder, sequential isolated ingestion; not throughput",
    "embedding_fingerprint": models.fingerprint,
    "rss_bytes": psutil.Process().memory_info().rss,
    "model_load": models.memory,
    "per_ingestion": records,
    "stages": {},
}
for stage in records[0]["timings"]:
    values = [r["timings"][stage] for r in records]
    report["stages"][stage] = {
        "count": len(values),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
    }
Path("docs/evidence/ingestion-profile.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report["stages"], indent=2))
