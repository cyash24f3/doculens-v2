import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select

from doculens.errors import DomainError
from doculens.ingestion.chunking import chunk
from doculens.ingestion.parsing import extract, validate_file
from doculens.storage.models import Chunk, Document, Job, Version


@pytest.mark.parametrize(
    "name,mime,raw,code",
    [
        ("bad.exe", "application/octet-stream", b"abc", "unsupported_extension"),
        ("empty.txt", "text/plain", b"", "empty_file"),
        ("space.txt", "text/plain", b" \n ", "empty_extraction"),
        ("bad.txt", "text/plain", b"\xff", "invalid_utf8"),
        ("binary.txt", "text/plain", b"hello\x00world", "binary_text"),
        ("fake.pdf", "application/pdf", b"abc", "corrupt_pdf"),
        ("text.md", "application/pdf", b"abc", "content_type_mismatch"),
        ("big.txt", "text/plain", b"a" * 2049, "file_too_large"),
    ],
)
def test_invalid_upload(name, mime, raw, code):
    with pytest.raises(DomainError) as caught:
        validate_file(name, mime, raw, 2048)
    assert caught.value.code == code


def test_image_only_corrupt_and_encrypted_pdf():
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt("password")
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(DomainError, match="Encrypted"):
        extract(output.getvalue(), "pdf", 20000)
    with pytest.raises(DomainError) as caught:
        extract(b"%PDF-1.7\nbroken", "pdf", 20000)
    assert caught.value.code == "corrupt_pdf"
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(200, 200))
    c.drawImage(ImageReader(Image.new("RGB", (100, 100), "gray")), 10, 10, 180, 180)
    c.showPage()
    c.save()
    with pytest.raises(DomainError) as caught:
        extract(output.getvalue(), "pdf", 20000)
    assert caught.value.code == "ocr_required"


def test_pdf_pages_and_text_offsets(system, ingest):
    _, repo, _, _, _ = system
    upload = ingest(
        Path("data/sample/beacon-quickstart.pdf").read_bytes(),
        filename="beacon.pdf",
        mime="application/pdf",
    )
    snapshot = repo.snapshot("sample")
    assert snapshot.evidence and all(e.page_start and e.page_end for e in snapshot.evidence)
    assert "firmware" in snapshot.evidence[0].text
    source = repo.get_evidence("sample", snapshot.evidence[0].id)
    assert source["offset_reference"] == "stored_extracted_text"
    assert repo.job("sample", upload["job_id"])["state"] == "completed"


def test_unicode_numbers_structure_duplicate_and_safe_filename(system, ingest):
    _, repo, models, _, _ = system
    text = "# Résumé\n\n₹1,299 costs 20% less. Deadline: 2026-09-30.\n\n## हिंदी\n\nनमस्ते café Wi-Fi E17."
    first = ingest(text, filename="../../policy.md")
    second = ingest(text)
    assert second["duplicate"] and first["version_id"] == second["version_id"]
    assert len(list(repo.files.iterdir())) == 1
    evidence = repo.snapshot("sample").evidence
    assert all(e.page_start is None for e in evidence)
    assert any("₹1,299" in e.text for e in evidence)
    extracted = extract(text.encode(), "markdown", 20000)
    a = chunk(extracted, models, 32, 8, 100)
    b = chunk(extracted, models, 32, 8, 100)
    assert a == b
    for piece in a:
        assert extracted.text[piece.start : piece.end] == piece.text
    assert evidence[0].id == repo.snapshot("sample").evidence[0].id


def test_chunk_window_and_model_limit(system):
    _, _, models, _, _ = system
    text = "# Long\n\n" + " ".join(f"word{i}" for i in range(250))
    result = chunk(extract(text.encode(), "markdown", 20000), models, 32, 8, 100)
    assert len(result) > 2 and all(p.token_count <= 32 for p in result)
    assert result[1].start < result[0].end
    with pytest.raises(DomainError):
        chunk(extract(text.encode(), "text", 20000), models, 300, 10, 100)
    with pytest.raises(DomainError):
        chunk(extract(text.encode(), "text", 20000), models, 32, 8, 1)


def test_replacement_failure_preserves_active_version(system, ingest):
    _, repo, _, worker, _ = system
    old = ingest("# Returns\n\nReturn unopened goods within 30 days.")
    broken = repo.upload(
        "sample",
        b"%PDF-1.7\nbroken",
        "bad.pdf",
        "application/pdf",
        "Policy",
        document_id=old["document_id"],
    )
    worker.run_once()
    assert repo.job("sample", broken["job_id"])["state"] == "failed"
    assert repo.snapshot("sample").versions == (old["version_id"],)
    new = ingest(
        "# Returns\n\nReturn unopened goods within 14 days.", document_id=old["document_id"]
    )
    assert repo.snapshot("sample").versions == (new["version_id"],)
    versions = repo.versions("sample", old["document_id"])
    assert [v["state"] for v in versions] == ["ready", "failed", "ready"]
    assert "14 days" in repo.snapshot("sample").evidence[0].text


def test_stale_worker_cannot_promote_and_crash_is_reclaimed(system):
    _, repo, _, worker, _ = system
    item = repo.upload("sample", b"# Status\n\nReady now.", "status.md", "text/markdown", "Status")
    old_claim = worker.claim()
    with repo.db.transaction(write=True) as session:
        session.get(Job, item["job_id"]).lease_until = time.time() - 1
    new_claim = worker.claim()
    assert new_claim and old_claim[1] != new_claim[1]
    worker.process(*old_claim)
    assert not repo.snapshot("sample").evidence
    worker.process(*new_claim)
    assert repo.job("sample", item["job_id"])["state"] == "completed"
    assert repo.job("sample", item["job_id"])["attempts"] == 2


def test_newer_upload_prevents_obsolete_promotion(system, ingest):
    _, repo, _, worker, _ = system
    initial = ingest("Initial working policy.")
    older = repo.upload(
        "sample",
        b"Older pending replacement.",
        "p.md",
        "text/markdown",
        "Policy",
        document_id=initial["document_id"],
    )
    claim = worker.claim()
    newest = repo.upload(
        "sample",
        b"Newest replacement.",
        "p.md",
        "text/markdown",
        "Policy",
        document_id=initial["document_id"],
    )
    worker.process(*claim)
    assert repo.job("sample", older["job_id"])["state"] == "completed"
    assert repo.snapshot("sample").versions == (initial["version_id"],)
    worker.run_once()
    assert repo.snapshot("sample").versions == (newest["version_id"],)


def test_claims_are_atomic_and_retry_is_bounded(system):
    _, repo, _, worker, _ = system
    item = repo.upload("sample", b"%PDF-1.7\nbroken", "x.pdf", "application/pdf", "Broken")
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: worker.claim(), range(2)))
    assert sum(c is not None for c in claims) == 1
    worker.process(*next(c for c in claims if c))
    for _ in range(2):
        repo.retry("sample", item["job_id"])
        worker.run_once()
    assert repo.job("sample", item["job_id"])["attempts"] == 3
    with pytest.raises(DomainError):
        repo.retry("sample", item["job_id"])


def test_promotion_rollback_never_exposes_partial_chunks(system, ingest, monkeypatch):
    _, repo, models, worker, _ = system
    initial = ingest("Initial policy works.")
    item = repo.upload(
        "sample",
        b"Bad embedding replaces policy.",
        "x.md",
        "text/markdown",
        "Policy",
        document_id=initial["document_id"],
    )
    monkeypatch.setattr(models, "encode", lambda _: [[0.0] * 3])
    worker.run_once()
    assert repo.job("sample", item["job_id"])["error_code"] == "embedding_dimension_mismatch"
    assert repo.snapshot("sample").versions == (initial["version_id"],)
    with repo.db.transaction() as session:
        assert not session.scalar(select(Chunk).where(Chunk.version_id == item["version_id"]))
        assert session.get(Version, item["version_id"]).state == "failed"
        assert (
            session.get(Document, initial["document_id"]).active_version_id == initial["version_id"]
        )


def test_interpretation_metadata_changes_are_new_immutable_versions(system, ingest):
    _, repo, _, worker, _ = system
    initial = ingest("Return goods within 30 days.")
    before = repo.versions("sample", initial["document_id"])[0]
    updated = repo.upload(
        "sample",
        b"Return goods within 30 days.",
        "policy.md",
        "text/markdown",
        "Policy",
        document_id=initial["document_id"],
        effective_date="2026-10-01",
        source_locator="https://example.test/policy",
    )
    assert not updated["duplicate"]
    worker.run_once()
    versions = repo.versions("sample", initial["document_id"])
    assert len(versions) == 2 and versions[0]["effective_date"] == "2026-10-01"
    assert versions[1]["effective_date"] == before["effective_date"] is None
    assert versions[0]["raw_sha256"] == versions[1]["raw_sha256"]
    assert repo.snapshot("sample").versions == (updated["version_id"],)
    duplicate = repo.upload(
        "sample",
        b"Return goods within 30 days.",
        "policy.md",
        "text/markdown",
        "Policy",
        document_id=initial["document_id"],
    )
    assert duplicate["duplicate"] and duplicate["version_id"] == updated["version_id"]
