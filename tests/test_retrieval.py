from dataclasses import replace

import pytest
from sqlalchemy import select

from doculens.errors import DomainError
from doculens.retrieval.search import Hit, rrf
from doculens.storage.models import Chunk, Trace


def test_exact_terms_scope_snapshot_and_cache(system, ingest):
    _, repo, _, _, retriever = system
    public = ingest("# Error E17\n\nReset Beacon B200 to clear E17.")
    private = ingest(
        "# Secret E17\n\nA private token is confidential.", scope="private", title="Private"
    )
    snapshot = repo.snapshot("sample")
    for method in ["bm25", "dense", "hybrid", "reranked"]:
        result = retriever.search(snapshot, "Beacon B200 E17", method, 5)
        assert result.hits and all(
            h.evidence.document_id == public["document_id"] for h in result.hits
        )
    assert retriever.cache
    with pytest.raises(DomainError):
        repo.snapshot("sample", [private["document_id"]])
    updated = ingest(
        "# Error E99\n\nReset Beacon B200 to clear E99.", document_id=public["document_id"]
    )
    after = repo.snapshot("sample")
    assert after.manifest != snapshot.manifest and after.revision > snapshot.revision
    assert retriever.search(after, "E17", "bm25", 5).hits == ()
    assert updated["version_id"] == after.evidence[0].version_id
    # Old materialized snapshot is internally consistent, but ineligible for publication.
    assert "E17" in snapshot.evidence[0].text
    with pytest.raises(DomainError, match="changed"):
        repo.save_trace(snapshot, "old-query", {})


def test_rrf_one_based_weights_absence_and_ties(system, ingest):
    _, repo, _, _, _ = system
    ingest("# A\n\nPolicy A.\n\n## B\n\nPolicy B.")
    a, b = repo.snapshot("sample").evidence
    lexical = [Hit(a, 900, "bm25", 1), Hit(b, 1, "bm25", 2)]
    dense = [Hit(b, 0.1, "cosine_similarity", 1)]
    result = rrf(lexical, dense, 60)
    assert result[0].evidence.id == b.id
    assert result[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert result[1].score == pytest.approx(1 / 61)
    assert rrf(lexical + [lexical[0]], dense, 60) == result
    ties = rrf([Hit(a, 1, "bm25", 1)], [Hit(b, 1, "cosine", 1)], 60)
    assert [h.evidence.id for h in ties] == sorted([a.id, b.id])


def test_embedding_incompatibility(system, ingest):
    _, repo, _, _, retriever = system
    ingest("A model compatibility policy.")
    snap = repo.snapshot("sample")
    bad = replace(snap, evidence=(replace(snap.evidence[0], embedding_fingerprint="other-model"),))
    with pytest.raises(DomainError, match="Reindex"):
        retriever.search(bad, "compatibility", "dense", 5)
    bad = replace(snap, evidence=(replace(snap.evidence[0], embedding=[1, 2]),))
    with pytest.raises(DomainError):
        retriever.search(bad, "compatibility", "dense", 5)


def test_deletion_removes_search_evidence_and_traces(system, ingest):
    _, repo, _, _, retriever = system
    item = ingest("Removed document contains the code E17.")
    snapshot = repo.snapshot("sample")
    cid = snapshot.evidence[0].id
    retriever.search(snapshot, "E17", "bm25", 5)
    repo.save_trace(snapshot, "query-to-remove", {"answer": snapshot.evidence[0].text})
    repo.remove("sample", item["document_id"])
    after = repo.snapshot("sample")
    for method in ["bm25", "dense", "hybrid", "reranked"]:
        assert not retriever.search(after, "E17", method, 5).hits
    with pytest.raises(DomainError):
        repo.get_evidence("sample", cid, history=True)
    with repo.db.transaction() as session:
        assert not session.get(Trace, "query-to-remove")
        assert not session.scalar(select(Chunk))
    assert not list(repo.files.iterdir())
    with pytest.raises(DomainError):
        repo.save_trace(snapshot, "in-flight", {})


def test_history_requires_explicit_selection(system, ingest):
    _, repo, _, _, _ = system
    old = ingest("Old policy: 30 days.")
    cid = repo.snapshot("sample").evidence[0].id
    ingest("New policy: 14 days.", document_id=old["document_id"])
    with pytest.raises(DomainError):
        repo.get_evidence("sample", cid)
    assert "30 days" in repo.get_evidence("sample", cid, history=True)["text"]
