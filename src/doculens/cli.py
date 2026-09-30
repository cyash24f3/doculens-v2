import argparse
import json
import signal
import threading
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from doculens.config import Settings
from doculens.evaluation.runner import ROOT, run_benchmark
from doculens.generation.service import Answerer
from doculens.ingestion.worker import Worker
from doculens.retrieval.models import Models
from doculens.retrieval.search import Retriever
from doculens.storage.database import Database
from doculens.storage.models import Document, Version
from doculens.storage.repository import Repository


def migrate(settings):
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["settings"] = settings
    command.upgrade(cfg, "head")


def seed(repo, models):
    manifest = json.loads((ROOT / "data/source_manifest.json").read_text())
    ordered = sorted(manifest, key=lambda item: item["active"])
    worker = Worker(repo, models)
    for item in ordered:
        with repo.db.transaction() as session:
            existing = session.scalar(
                select(Document).where(
                    Document.title == item["title"],
                    Document.workspace == "sample",
                    Document.deleted.is_(False),
                )
            )
            version = (
                session.scalar(
                    select(Version).where(
                        Version.document_id == existing.id,
                        Version.raw_sha256 == item["sha256"],
                        Version.pipeline_fingerprint == repo.pipeline,
                        Version.state == "ready",
                    )
                )
                if existing
                else None
            )
            if version:
                continue
            doc_id = existing.id if existing else None
        raw = (ROOT / item["path"]).read_bytes()
        from doculens.ingestion.parsing import sha

        if sha(raw) != item["sha256"]:
            raise ValueError("Sample source hash changed: " + item["key"])
        response = repo.upload(
            "sample",
            raw,
            Path(item["path"]).name,
            "application/octet-stream",
            item["title"],
            item["version"],
            doc_id,
            tags=[item["track"]],
            effective_date=item.get("effective_date"),
            source_locator=item.get("source_locator"),
        )
        while worker.run_once():
            pass
        status = repo.job("sample", response["job_id"])
        if status["state"] != "completed":
            raise RuntimeError(f"Seed failed: {item['key']} {status['error_code']}")
    snapshot = repo.snapshot("sample")
    print(
        json.dumps(
            {
                "active_versions": len(snapshot.versions),
                "chunks": len(snapshot.evidence),
                "revision": snapshot.revision,
                "models": models.memory,
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="DocuLens reproducible local commands")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("seed")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    demo = commands.add_parser("demo")
    demo.add_argument("--port", type=int, default=8000)
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--real-models", action="store_true")
    worker_parser = commands.add_parser("worker")
    worker_parser.add_argument("--once", action="store_true")
    worker_parser.add_argument("--demo", action="store_true")
    worker_parser.add_argument("--real-models", action="store_true")
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--split", choices=["dev", "test", "ci"], default="dev")
    benchmark.add_argument("--output", type=Path, default=Path("outputs"))
    benchmark.add_argument("--demo", action="store_true")
    benchmark.add_argument("--real-models", action="store_true")
    benchmark.add_argument("--answers", action="store_true")
    benchmark.add_argument("--max-questions", type=int)
    answers = commands.add_parser("evaluate-answers")
    answers.add_argument("--split", choices=["dev", "test"], default="test")
    answers.add_argument("--questions", type=int, default=12)
    answers.add_argument("--no-judge", action="store_true")
    answers.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    settings = Settings()
    if args.command == "demo" or getattr(args, "demo", False):
        backend = "sentence_transformer" if getattr(args, "real_models", False) else "fixture"
        settings = settings.model_copy(
            update={
                "database_url": "sqlite:///var/demo-real.db"
                if backend == "sentence_transformer"
                else "sqlite:///var/demo.db",
                "storage_dir": Path(
                    "var/demo-real-files" if backend == "sentence_transformer" else "var/demo-files"
                ),
                "model_backend": backend,
                "generation_mode": "fixture",
            }
        )
    if args.command == "migrate":
        migrate(settings)
        print("Schema migrated.")
        return
    if args.command in {"serve", "demo"}:
        if args.command == "demo":
            migrate(settings)
            db = Database(settings)
            models = Models(settings)
            models.initialize()
            seed(Repository(db, settings), models)
        import uvicorn

        from doculens.api.app import create_app

        print(
            f"DocuLens at http://127.0.0.1:{args.port}; generation={settings.generation_mode}; models={settings.model_backend}"
        )
        uvicorn.run(
            create_app(settings, database=db, models=models)
            if args.command == "demo"
            else create_app(settings),
            host=getattr(args, "host", "127.0.0.1"),
            port=args.port,
            access_log=False,
        )
        return
    db = Database(settings)
    repo = Repository(db, settings)
    models = Models(settings)
    models.initialize()
    if args.command == "seed":
        seed(repo, models)
    elif args.command == "worker":
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        worker = Worker(repo, models)
        if args.once:
            worker.run_once()
        else:
            while not stop.is_set():
                if not worker.run_once():
                    stop.wait(1)
    elif args.command == "evaluate-answers":
        from doculens.evaluation.answers import evaluate_answers

        path, summary = evaluate_answers(
            repo,
            Retriever(settings, models),
            Answerer(settings),
            args.split,
            args.questions,
            args.output,
            not args.no_judge,
        )
        print(json.dumps(summary, indent=2))
        print("Report:", path / "report.md")
    elif args.command == "benchmark":
        if args.answers and settings.generation_mode != "provider":
            parser.error(
                "--answers requires provider mode (local Ollama is free); fixtures are not semantic evaluation"
            )
        path, summary = run_benchmark(
            repo,
            Retriever(settings, models),
            args.split,
            args.output,
            Answerer(settings) if args.answers else None,
            args.max_questions,
        )
        print(json.dumps(summary["methods"], indent=2))
        print("Report:", path / "report.md")


if __name__ == "__main__":
    main()
