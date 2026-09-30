import logging
import time
from dataclasses import asdict

from sqlalchemy import delete, or_, select, update

from doculens.errors import DomainError
from doculens.ingestion.chunking import chunk
from doculens.ingestion.parsing import extract, sha
from doculens.storage.models import Chunk, Document, Job, Version, uid

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, repository, models):
        self.repo = repository
        self.db = repository.db
        self.settings = repository.settings
        self.models = models

    def claim(self) -> tuple[str, str] | None:
        now = time.time()
        with self.db.transaction(write=True) as session:
            eligible = or_(
                Job.state == "queued", (Job.state == "running") & (Job.lease_until < now)
            )
            rows = session.execute(
                select(Job.id, Document.workspace)
                .join(Version, Job.version_id == Version.id)
                .join(Document, Version.document_id == Document.id)
                .where(eligible, Document.deleted.is_(False))
                .order_by(Job.created_at, Job.id)
                .limit(10)
            ).all()
            for job_id, scope in rows:
                self.db.lock_scope(session, scope)
                job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
                if job.state != "queued" and not (job.state == "running" and job.lease_until < now):
                    continue
                version = session.get(Version, job.version_id)
                if job.attempts >= self.settings.job_attempts:
                    job.state, job.error_code, job.error_message = (
                        "failed",
                        "attempts_exhausted",
                        "Worker lease expired; retry budget exhausted",
                    )
                    version.state, version.error_code = "failed", "attempts_exhausted"
                    continue
                token = uid()
                job.state, job.lease_token, job.lease_until = (
                    "running",
                    token,
                    now + self.settings.job_lease_seconds,
                )
                job.attempts += 1
                job.stage, job.done, job.total = "extracting", 0, None
                version.state = "processing"
                return job.id, token
        return None

    def progress(
        self, job_id: str, token: str, stage: str, done: int = 0, total: int | None = None
    ):
        with self.db.transaction(write=True) as session:
            now = time.time()
            result = session.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.state == "running",
                    Job.lease_token == token,
                    Job.lease_until > now,
                )
                .values(
                    stage=stage,
                    done=done,
                    total=total,
                    lease_until=now + self.settings.job_lease_seconds,
                )
            )
            if result.rowcount != 1:
                raise DomainError("lease_lost", "Worker no longer owns this ingestion job", 409)

    def process(self, job_id: str, token: str):
        started = time.perf_counter()
        try:
            with self.db.transaction() as session:
                job = session.get(Job, job_id)
                version = session.get(Version, job.version_id)
                version_id, key, kind = version.id, version.storage_key, version.source_kind
                if (
                    version.embedding_fingerprint != self.models.fingerprint
                    or version.pipeline_fingerprint != self.repo.pipeline
                ):
                    raise DomainError(
                        "pipeline_mismatch",
                        "Worker configuration differs from upload configuration",
                    )
            self.progress(job_id, token, "extracting")
            source = extract(
                (self.repo.files / key).read_bytes(), kind, self.settings.extracted_chars
            )
            extraction_ms = (time.perf_counter() - started) * 1000
            self.progress(job_id, token, "chunking")
            chunking_start = time.perf_counter()
            pieces = chunk(
                source,
                self.models,
                self.settings.chunk_tokens,
                self.settings.chunk_overlap,
                self.settings.max_chunks,
            )
            chunking_ms = (time.perf_counter() - chunking_start) * 1000
            vectors = []
            embedding_start = time.perf_counter()
            for offset in range(0, len(pieces), 16):
                self.progress(job_id, token, "embedding", offset, len(pieces))
                vectors.extend(self.models.encode([p.text for p in pieces[offset : offset + 16]]))
            embedding_ms = (time.perf_counter() - embedding_start) * 1000
            self.progress(job_id, token, "activating", len(pieces), len(pieces))
            # No staged chunks are visible. All content publication is one fenced transaction.
            self.promote(
                job_id,
                token,
                version_id,
                source,
                pieces,
                vectors,
                {
                    "extraction_ms": extraction_ms,
                    "chunking_ms": chunking_ms,
                    "embedding_ms": embedding_ms,
                    "total_before_activation_ms": (time.perf_counter() - started) * 1000,
                },
            )
            log.info(
                "ingestion_completed",
                extra={
                    "job_id": job_id,
                    "version_id": version_id,
                    "extraction_ms": extraction_ms,
                    "embedding_ms": embedding_ms,
                    "total_ms": (time.perf_counter() - started) * 1000,
                },
            )
        except DomainError as e:
            if e.code != "lease_lost":
                self.fail(job_id, token, e.code, e.message)
        except Exception:
            # Operational code is logged; private contents and parser stack traces are not.
            self.fail(
                job_id,
                token,
                "ingestion_failed",
                "Ingestion failed; check worker configuration and file integrity",
            )
            log.warning(
                "ingestion_failed",
                extra={"job_id": job_id, "version_id": locals().get("version_id")},
            )

    def promote(self, job_id, token, version_id, source, pieces, vectors, timings=None):
        activation_start = time.perf_counter()
        with self.db.transaction(write=True) as session:
            version = session.get(Version, version_id)
            doc = session.get(Document, version.document_id)
            workspace = self.db.lock_scope(session, doc.workspace)
            session.refresh(doc)
            session.refresh(version)
            job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if (
                doc.deleted
                or job.state != "running"
                or job.lease_token != token
                or job.lease_until <= time.time()
            ):
                raise DomainError(
                    "lease_lost", "Publication rejected because job ownership expired", 409
                )
            if len(pieces) != len(vectors):
                raise DomainError("invalid_embedding", "Embedding count does not match chunks")
            session.execute(delete(Chunk).where(Chunk.version_id == version_id))
            for piece, vector in zip(pieces, vectors, strict=True):
                if len(vector) != self.settings.embedding_dimension:
                    raise DomainError(
                        "embedding_dimension_mismatch", "Embedding dimension differs from schema"
                    )
                values = asdict(piece)
                values["id"] = sha(
                    f"{version_id}:{piece.ordinal}:{piece.start}:{piece.end}:{piece.content_sha256}"
                )
                values["version_id"] = version_id
                values["embedding"] = vector
                values["embedding_fingerprint"] = self.models.fingerprint
                session.add(Chunk(**values))
            version.state, version.extracted_text = "ready", source.text
            version.extracted_sha256, version.chunk_count = sha(source.text), len(pieces)
            version.warnings, version.error_code = list(source.warnings), None
            if version.sequence == doc.latest_sequence:
                doc.active_version_id = version_id
                workspace.revision += 1
            job.state, job.stage = "completed", "completed"
            job.done, job.total, job.lease_token, job.lease_until = (
                len(pieces),
                len(pieces),
                None,
                None,
            )
            job.error_code, job.error_message = None, None
            job.timings = {
                **(timings or {}),
                "activation_before_commit_ms": (time.perf_counter() - activation_start) * 1000,
            }

    def fail(self, job_id: str, token: str, code: str, message: str):
        with self.db.transaction(write=True) as session:
            job = session.get(Job, job_id)
            version = session.get(Version, job.version_id)
            doc = session.get(Document, version.document_id)
            self.db.lock_scope(session, doc.workspace)
            session.refresh(job)
            if (
                job.state == "running"
                and job.lease_token == token
                and job.lease_until > time.time()
            ):
                job.state, job.error_code, job.error_message = "failed", code, message[:500]
                job.lease_token, job.lease_until = None, None
                version.state, version.error_code = "failed", code

    def run_once(self) -> bool:
        claimed = self.claim()
        if not claimed:
            return False
        self.process(*claimed)
        return True
