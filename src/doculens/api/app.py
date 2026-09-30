import logging
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text

from doculens.api.auth import authenticate, bearer, permitted, require_admin
from doculens.api.contracts import AnswerResponse, SearchRequest, SearchResponse, UploadResponse
from doculens.config import Settings
from doculens.errors import DomainError
from doculens.generation.service import Answerer
from doculens.observability.telemetry import Metrics, configure
from doculens.retrieval.models import Models
from doculens.retrieval.search import Retriever
from doculens.storage.database import Database
from doculens.storage.models import Experiment, Job, Trace, uid
from doculens.storage.repository import Repository

log = logging.getLogger(__name__)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
WEB = Path(__file__).parents[1] / "web"


def create_app(
    settings: Settings | None = None, database=None, models=None, answerer=None
) -> FastAPI:
    settings = settings or Settings()
    db = database or Database(settings)
    model_manager = models or Models(settings)
    repo = Repository(db, settings)
    retriever = Retriever(settings, model_manager)
    generator = answerer or Answerer(settings)
    metrics = Metrics()
    configure(settings.log_level)

    @asynccontextmanager
    async def lifespan(app):
        # Heavy initialization runs in a worker thread, never on the event loop.
        from starlette.concurrency import run_in_threadpool

        await run_in_threadpool(model_manager.initialize)
        with db.transaction() as session:
            session.execute(text("SELECT revision FROM workspaces LIMIT 1"))
        yield
        if generator.provider is not None and hasattr(generator.provider, "close"):
            generator.provider.close()
        db.engine.dispose()

    app = FastAPI(
        title="DocuLens",
        version="0.1.0",
        lifespan=lifespan,
        description="Evidence-grounded retrieval and generation. Fixture responses are scripted demo behavior.",
    )
    app.state.settings, app.state.repo, app.state.models = settings, repo, model_manager
    app.state.retriever, app.state.answerer = retriever, generator
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
    templates = Jinja2Templates(directory=WEB / "templates")

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "request_id": request.state.request_id,
            },
        )

    @app.middleware("http")
    async def bounded_requests(request: Request, call_next):
        request.state.request_id = uid()
        started = time.perf_counter()
        if request.method in {"POST", "PUT", "PATCH"}:
            limit = (
                settings.upload_bytes + 65536 if request.url.path == "/api/v1/documents" else 16384
            )
            parts, size = [], 0
            async for part in request.stream():
                size += len(part)
                if size > limit:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "request_too_large",
                                "message": "Request body exceeds limit",
                            }
                        },
                    )
                parts.append(part)
            request._body = b"".join(parts)
        response = await call_next(request)
        elapsed = (time.perf_counter() - started) * 1000
        metrics.observe(response.status_code, elapsed)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        log.info(
            "request_completed",
            extra={
                "request_id": request.state.request_id,
                "status": response.status_code,
                "total_ms": elapsed,
            },
        )
        return response

    def identity(request: Request, credentials: Credentials) -> bool:
        return authenticate(request, credentials)

    Admin = Annotated[bool, Depends(identity)]

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "service": "doculens"}

    @app.get("/api/v1/readiness")
    def ready():
        try:
            with db.transaction() as session:
                session.execute(text("SELECT revision FROM workspaces LIMIT 1"))
        except Exception:
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "database": "unavailable"}
            )
        payload = {
            "status": "ready" if model_manager.loaded else "not_ready",
            "database": "available",
            "models": "initialized" if model_manager.loaded else "not_initialized",
            "generation_mode": settings.generation_mode,
            "provider_connectivity": "unverified"
            if settings.generation_mode == "provider"
            else "not_applicable",
        }

        return JSONResponse(status_code=200 if model_manager.loaded else 503, content=payload)

    @app.get("/api/v1/config")
    def public_configuration():
        return {
            "model_backend": settings.model_backend,
            "embedding_model": model_manager.fingerprint,
            "generation_mode": settings.generation_mode,
            "default_method": "hybrid",
            "upload_limit_bytes": settings.upload_bytes,
            "fixture_questions": [
                "Can I return an opened product after 20 days?",
                "Is delivery to Antarctica guaranteed?",
                "How long is the Harbor warranty?",
            ],
        }

    @app.post("/api/v1/documents", response_model=UploadResponse, status_code=202)
    async def upload(
        request: Request,
        admin: Admin,
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form(min_length=1, max_length=200)],
        corpus: Annotated[Literal["sample", "private"], Form()] = "private",
        label: Annotated[str, Form(max_length=80)] = "v1",
        document_id: Annotated[str | None, Form()] = None,
        effective_date: Annotated[date | None, Form()] = None,
        source_locator: Annotated[str | None, Form(max_length=500)] = None,
        document_type: Annotated[str, Form(max_length=50)] = "documentation",
        tags: Annotated[str, Form(max_length=500)] = "",
    ):
        require_admin(admin)
        raw = await file.read(settings.upload_bytes + 1)
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            repo.upload,
            permitted(corpus, admin),
            raw,
            file.filename or "",
            file.content_type or "",
            title.strip(),
            label,
            document_id,
            document_type,
            [t.strip() for t in tags.split(",") if t.strip()],
            effective_date.isoformat() if effective_date else None,
            source_locator,
        )

    @app.get("/api/v1/documents")
    def documents(
        admin: Admin,
        corpus: Literal["sample", "private"] = "sample",
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ):
        return {
            "documents": repo.documents(permitted(corpus, admin), offset, limit),
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/v1/documents/{document_id}")
    def document(document_id: str, admin: Admin, corpus: Literal["sample", "private"] = "sample"):
        versions = repo.versions(permitted(corpus, admin), document_id)
        return {"document_id": document_id, "versions": versions}

    @app.get("/api/v1/documents/{document_id}/versions")
    def versions(document_id: str, admin: Admin, corpus: Literal["sample", "private"] = "sample"):
        return {"versions": repo.versions(permitted(corpus, admin), document_id)}

    @app.delete("/api/v1/documents/{document_id}", status_code=204)
    def remove(document_id: str, admin: Admin, corpus: Literal["sample", "private"] = "private"):
        require_admin(admin)
        repo.remove(permitted(corpus, admin), document_id)
        retriever.clear()

    @app.get("/api/v1/jobs/{job_id}")
    def job_status(job_id: str, admin: Admin, corpus: Literal["sample", "private"] = "private"):
        require_admin(admin)
        return repo.job(permitted(corpus, admin), job_id)

    @app.post("/api/v1/jobs/{job_id}/retry", status_code=202)
    def retry(job_id: str, admin: Admin, corpus: Literal["sample", "private"] = "private"):
        require_admin(admin)
        repo.retry(permitted(corpus, admin), job_id)
        return {"status": "queued"}

    def run_search(body: SearchRequest, admin: bool):
        if len(model_manager.offsets(body.question)) > model_manager.max_tokens - 2:
            raise DomainError(
                "question_model_limit", "Question exceeds embedding model input limit"
            )
        snapshot = repo.snapshot(permitted(body.corpus, admin), body.document_ids)
        return retriever.search(snapshot, body.question, body.method, body.top_k)

    @app.post("/api/v1/search", response_model=SearchResponse)
    def search(body: SearchRequest, request: Request, admin: Admin):
        result = run_search(body, admin)
        response = {
            "request_id": request.state.request_id,
            "corpus_revision": result.snapshot.revision,
            "corpus_manifest": result.snapshot.manifest,
            "method": body.method,
            "embedding_model": model_manager.fingerprint,
            "results": [h.public() for h in result.hits],
            "timings": result.timings,
        }
        repo.save_trace(
            result.snapshot, request.state.request_id, {"search": response, "stages": result.stages}
        )
        return response

    @app.post("/api/v1/developer/compare")
    def compare(body: SearchRequest, request: Request, admin: Admin):
        require_admin(admin)
        snapshot = repo.snapshot(permitted(body.corpus, admin), body.document_ids)
        comparisons = []
        for method in ("bm25", "dense", "hybrid", "reranked"):
            result = retriever.search(snapshot, body.question, method, body.top_k)
            comparisons.append(
                {
                    "method": method,
                    "corpus_revision": snapshot.revision,
                    "results": [h.public() for h in result.hits],
                    "timings": result.timings,
                    "stages": result.stages,
                }
            )
        response = {
            "request_id": request.state.request_id,
            "corpus_revision": snapshot.revision,
            "corpus_manifest": snapshot.manifest,
            "comparisons": comparisons,
        }
        repo.save_trace(snapshot, request.state.request_id, {"comparison": response})
        return response

    @app.post("/api/v1/answers", response_model=AnswerResponse)
    def answer(body: SearchRequest, request: Request, admin: Admin):
        started = time.perf_counter()
        if settings.generation_mode == "provider":
            require_admin(admin)
        result = run_search(body.model_copy(update={"top_k": settings.candidate_limit}), admin)
        response, trace = generator.answer(body.question, result, request.state.request_id)
        metrics.observe_generation(response["status"])
        response["timings"]["total_ms"] = (time.perf_counter() - started) * 1000
        repo.save_trace(result.snapshot, request.state.request_id, {"answer": response, **trace})
        return response

    @app.get("/api/v1/evidence/{chunk_id}")
    def evidence(
        chunk_id: str,
        admin: Admin,
        corpus: Literal["sample", "private"] = "sample",
        history: bool = False,
    ):
        if history:
            require_admin(admin)
        return repo.get_evidence(permitted(corpus, admin), chunk_id, history)

    @app.get("/api/v1/developer/traces/{trace_id}")
    def trace(trace_id: str, admin: Admin):
        require_admin(admin)
        with db.transaction() as session:
            trace = session.get(Trace, trace_id)
            if not trace or trace.created_at < time.time() - settings.trace_retention_days * 86400:
                raise DomainError("trace_not_found", "Trace not found or expired", 404)
            return {
                "id": trace.id,
                "created_at": trace.created_at,
                "workspace": trace.workspace,
                **trace.payload,
            }

    @app.get("/api/v1/developer/experiments")
    def experiments(admin: Admin, limit: int = Query(20, ge=1, le=100)):
        require_admin(admin)
        with db.transaction() as session:
            return {
                "experiments": [
                    {
                        "id": e.id,
                        "created_at": e.created_at,
                        "manifest": e.manifest,
                        "summary": e.summary,
                    }
                    for e in session.scalars(
                        select(Experiment).order_by(Experiment.created_at.desc()).limit(limit)
                    )
                ]
            }

    @app.get("/api/v1/developer/metrics")
    def operational_metrics(admin: Admin):
        require_admin(admin)
        with db.transaction() as session:
            states = dict(
                session.execute(select(Job.state, func.count()).group_by(Job.state)).all()
            )
        return {
            **metrics.snapshot(),
            "ingestion_job_counts": states,
            "models": model_manager.memory,
        }

    return app
