import json
import time
from dataclasses import asdict, dataclass

from sqlalchemy import delete, select

from doculens.config import Settings
from doculens.errors import DomainError
from doculens.ingestion.parsing import sha, validate_file
from doculens.storage.database import Database
from doculens.storage.models import Chunk, Document, Job, Trace, Version, uid


@dataclass(frozen=True)
class Evidence:
    id: str
    document_id: str
    version_id: str
    title: str
    version: str
    effective_date: str | None
    source_kind: str
    source_locator: str | None
    text: str
    section: str | None
    page_start: int | None
    page_end: int | None
    start: int
    end: int
    ordinal: int
    token_count: int
    content_sha256: str
    embedding_fingerprint: str
    embedding: list[float]

    def public(self) -> dict:
        return {
            k: v for k, v in asdict(self).items() if k not in {"embedding", "embedding_fingerprint"}
        }


@dataclass(frozen=True)
class Snapshot:
    scope: str
    revision: int
    manifest: str
    versions: tuple[str, ...]
    evidence: tuple[Evidence, ...]


class Repository:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.files = settings.storage_dir.resolve()
        self.files.mkdir(parents=True, exist_ok=True)
        pipeline = {
            "parser": "pypdf-page-v1",
            "normalization": "crlf-strip-v1",
            "chunker": "offset-section-window-v1",
            "tokens": settings.chunk_tokens,
            "overlap": settings.chunk_overlap,
            "embedding": settings.embedding_fingerprint,
        }
        self.pipeline = sha(json.dumps(pipeline, sort_keys=True))

    def upload(
        self,
        scope: str,
        raw: bytes,
        filename: str,
        mime: str,
        title: str,
        label: str = "v1",
        document_id: str | None = None,
        document_type: str = "documentation",
        tags: list | None = None,
        effective_date: str | None = None,
        source_locator: str | None = None,
    ) -> dict:
        if not title.strip() or not label.strip():
            raise DomainError(
                "invalid_metadata", "Document title and version label must not be blank"
            )
        kind = validate_file(filename, mime, raw, self.settings.upload_bytes)
        raw_hash = sha(raw)
        key = f"{uid()}.{kind}"
        path = self.files / key
        path.write_bytes(raw)
        path.chmod(0o600)
        try:
            with self.db.transaction(write=True) as session:
                self.db.lock_scope(session, scope)
                doc = session.get(Document, document_id) if document_id else None
                if document_id and (not doc or doc.workspace != scope or doc.deleted):
                    raise DomainError(
                        "document_not_found", "Document is not available in this scope", 404
                    )
                if doc and doc.active_version_id:
                    current = session.get(Version, doc.active_version_id)
                    if effective_date is None:
                        effective_date = current.effective_date
                    if source_locator is None:
                        source_locator = current.source_locator
                duplicates = (
                    select(Version, Document)
                    .join(Document)
                    .where(
                        Document.workspace == scope,
                        Document.deleted.is_(False),
                        Version.raw_sha256 == raw_hash,
                        Version.pipeline_fingerprint == self.pipeline,
                        Version.state.in_(["pending", "processing", "ready"]),
                    )
                )
                if doc:
                    duplicates = duplicates.where(Document.id == doc.id)
                for previous, previous_doc in session.execute(duplicates):
                    if doc and (
                        previous.effective_date != effective_date
                        or previous.source_locator != source_locator
                    ):
                        # Explicit interpretation changes are new immutable, auditable versions.
                        continue
                    if previous.state != "ready" or previous_doc.active_version_id == previous.id:
                        job = session.scalar(select(Job).where(Job.version_id == previous.id))
                        path.unlink(missing_ok=True)
                        return {
                            "document_id": previous.document_id,
                            "version_id": previous.id,
                            "job_id": job.id,
                            "duplicate": True,
                        }
                if doc is None:
                    doc = Document(
                        id=uid(),
                        workspace=scope,
                        title=title,
                        document_type=document_type,
                        tags=tags or [],
                        latest_sequence=0,
                    )
                    session.add(doc)
                # Existing document metadata is immutable through replacement uploads.
                doc.latest_sequence += 1
                version = Version(
                    id=uid(),
                    document_id=doc.id,
                    sequence=doc.latest_sequence,
                    label=label,
                    source_kind=kind,
                    source_locator=source_locator,
                    effective_date=effective_date,
                    raw_sha256=raw_hash,
                    pipeline_fingerprint=self.pipeline,
                    embedding_fingerprint=self.settings.embedding_fingerprint,
                    embedding_dimension=self.settings.embedding_dimension,
                    storage_key=key,
                )
                session.add(version)
                session.flush()
                job = Job(id=uid(), version_id=version.id)
                session.add(job)
                return {
                    "document_id": doc.id,
                    "version_id": version.id,
                    "job_id": job.id,
                    "duplicate": False,
                }
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def documents(self, scope: str, offset: int = 0, limit: int = 50) -> list[dict]:
        with self.db.transaction() as session:
            docs = session.scalars(
                select(Document)
                .where(Document.workspace == scope, Document.deleted.is_(False))
                .order_by(Document.created_at.desc(), Document.id)
                .offset(offset)
                .limit(limit)
            ).all()
            results = []
            for doc in docs:
                latest = session.scalar(
                    select(Version)
                    .where(Version.document_id == doc.id)
                    .order_by(Version.sequence.desc())
                    .limit(1)
                )
                active = (
                    session.get(Version, doc.active_version_id) if doc.active_version_id else None
                )
                results.append(
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "document_type": doc.document_type,
                        "tags": doc.tags,
                        "created_at": doc.created_at,
                        "active_version_id": doc.active_version_id,
                        "active": self.version_dict(active) if active else None,
                        "latest": self.version_dict(latest) if latest else None,
                    }
                )
            return results

    @staticmethod
    def version_dict(version: Version) -> dict:
        excluded = {"extracted_text", "storage_key"}
        return {
            c.name: getattr(version, c.name)
            for c in Version.__table__.columns
            if c.name not in excluded
        }

    def versions(self, scope: str, doc_id: str) -> list[dict]:
        with self.db.transaction() as session:
            doc = session.get(Document, doc_id)
            if not doc or doc.workspace != scope or doc.deleted:
                raise DomainError("document_not_found", "Document not found", 404)
            return [
                self.version_dict(v)
                for v in session.scalars(
                    select(Version)
                    .where(Version.document_id == doc_id)
                    .order_by(Version.sequence.desc())
                )
            ]

    def job(self, scope: str, job_id: str) -> dict:
        with self.db.transaction() as session:
            row = session.execute(
                select(Job, Document)
                .join(Version, Job.version_id == Version.id)
                .join(Document, Version.document_id == Document.id)
                .where(Job.id == job_id, Document.workspace == scope, Document.deleted.is_(False))
            ).first()
            if not row:
                raise DomainError("job_not_found", "Job not found", 404)
            return {
                c.name: getattr(row.Job, c.name)
                for c in Job.__table__.columns
                if c.name not in {"lease_token"}
            }

    def retry(self, scope: str, job_id: str):
        with self.db.transaction(write=True) as session:
            self.db.lock_scope(session, scope)
            job = session.get(Job, job_id)
            version = session.get(Version, job.version_id) if job else None
            doc = session.get(Document, version.document_id) if version else None
            if not doc or doc.workspace != scope or doc.deleted or not job or not version:
                raise DomainError("job_not_found", "Job not found", 404)
            if job.state != "failed" or job.attempts >= self.settings.job_attempts:
                raise DomainError(
                    "retry_not_allowed",
                    "Only failed jobs with attempts remaining can be retried",
                    409,
                )
            job.state, job.stage, job.error_code, job.error_message = (
                "queued",
                "validating",
                None,
                None,
            )
            job.lease_token, job.lease_until, job.done, job.total = None, None, 0, None
            version.state, version.error_code = "pending", None

    def snapshot(self, scope: str, document_ids: list[str] | None = None) -> Snapshot:
        with self.db.transaction() as session:
            workspace = self.db.lock_scope(session, scope, read=True)
            docs_query = select(Document).where(
                Document.workspace == scope, Document.deleted.is_(False)
            )
            docs = list(session.scalars(docs_query))
            permitted = {d.id for d in docs}
            if document_ids and not set(document_ids) <= permitted:
                raise DomainError("scope_not_found", "Requested document scope is unavailable", 404)
            chosen = [d for d in docs if not document_ids or d.id in document_ids]
            versions = sorted(d.active_version_id for d in chosen if d.active_version_id)
            manifest = sha(
                json.dumps(
                    {"scope": scope, "revision": workspace.revision, "versions": versions},
                    sort_keys=True,
                )
            )
            statement = select(Chunk, Version, Document).join(
                Version, Chunk.version_id == Version.id
            )
            statement = statement.join(Document, Version.document_id == Document.id).where(
                Version.id.in_(versions), Version.state == "ready", Document.deleted.is_(False)
            )
            evidence = tuple(
                self.evidence(c, v, d) for c, v, d in session.execute(statement.order_by(Chunk.id))
            )
            return Snapshot(scope, workspace.revision, manifest, tuple(versions), evidence)

    @staticmethod
    def evidence(c: Chunk, v: Version, d: Document) -> Evidence:
        return Evidence(
            c.id,
            d.id,
            v.id,
            d.title,
            v.label,
            v.effective_date,
            v.source_kind,
            v.source_locator,
            c.text,
            c.section,
            c.page_start,
            c.page_end,
            c.start,
            c.end,
            c.ordinal,
            c.token_count,
            c.content_sha256,
            c.embedding_fingerprint,
            list(c.embedding),
        )

    def get_evidence(self, scope: str, chunk_id: str, history: bool = False) -> dict:
        with self.db.transaction() as session:
            row = session.execute(
                select(Chunk, Version, Document)
                .join(Version, Chunk.version_id == Version.id)
                .join(Document, Version.document_id == Document.id)
                .where(
                    Chunk.id == chunk_id,
                    Document.workspace == scope,
                    Document.deleted.is_(False),
                    Version.state == "ready",
                )
            ).first()
            if not row or (not history and row.Document.active_version_id != row.Version.id):
                raise DomainError("evidence_not_found", "Evidence is no longer available", 404)
            evidence = self.evidence(*row).public()
            evidence["surrounding_context"] = row.Version.extracted_text[
                max(0, row.Chunk.start - 300) : row.Chunk.end + 300
            ]
            evidence["offset_reference"] = "stored_extracted_text"
            return evidence

    def ensure_eligible(self, session, snapshot: Snapshot):
        self.db.lock_scope(session, snapshot.scope, read=True)
        active = set(
            session.scalars(
                select(Document.active_version_id).where(
                    Document.workspace == snapshot.scope, Document.deleted.is_(False)
                )
            )
        )
        if not set(snapshot.versions) <= active:
            raise DomainError(
                "corpus_changed", "Documents changed during this request; please retry", 409
            )

    def save_trace(self, snapshot: Snapshot, request_id: str, payload: dict):
        with self.db.transaction(write=True) as session:
            self.ensure_eligible(session, snapshot)
            session.add(
                Trace(
                    id=request_id,
                    workspace=snapshot.scope,
                    version_ids=list(snapshot.versions),
                    payload=payload,
                )
            )
            session.execute(
                delete(Trace).where(
                    Trace.created_at < time.time() - self.settings.trace_retention_days * 86400
                )
            )

    def remove(self, scope: str, doc_id: str):
        keys = []
        with self.db.transaction(write=True) as session:
            workspace = self.db.lock_scope(session, scope)
            doc = session.get(Document, doc_id)
            if not doc or doc.workspace != scope or doc.deleted:
                raise DomainError("document_not_found", "Document not found", 404)
            versions = list(session.scalars(select(Version).where(Version.document_id == doc_id)))
            ids = {v.id for v in versions}
            doc.deleted, doc.active_version_id = True, None
            workspace.revision += 1
            for version in versions:
                keys.append(version.storage_key)
                version.state, version.extracted_text, version.chunk_count = "deleted", None, 0
            session.execute(delete(Chunk).where(Chunk.version_id.in_(ids)))
            for job in session.scalars(select(Job).where(Job.version_id.in_(ids))):
                job.state, job.error_code = "failed", "document_deleted"
                job.lease_token, job.lease_until = None, None
            for trace in session.scalars(select(Trace).where(Trace.workspace == scope)):
                if ids & set(trace.version_ids):
                    session.delete(trace)
        for key in keys:
            (self.files / key).unlink(missing_ok=True)
