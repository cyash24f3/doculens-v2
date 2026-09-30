import json
from dataclasses import replace

import httpx
import pytest

from doculens.errors import DomainError
from doculens.generation.context import assemble
from doculens.generation.contracts import Claim, Proposal, Quote
from doculens.generation.provider import CompatibleProvider, Completion
from doculens.generation.service import Answerer
from doculens.generation.validation import validate_citations
from doculens.retrieval.search import Hit


def proposal(cid, span="Returns are accepted for 30 days."):
    return Proposal(
        status="answered",
        claims=[
            Claim(
                text="Returns are accepted for 30 days.",
                evidence_ids=[cid],
                quotes=[Quote(evidence_id=cid, span=span)],
            )
        ],
        missing_information=[],
    )


def test_context_budget_overlap_and_diversity(system, ingest):
    settings, repo, _, _, _ = system
    ingest("# Returns\n\nReturns are accepted for 30 days.")
    ingest("# Shipping\n\nShipping takes 5 days.", title="Shipping")
    a, b = repo.snapshot("sample").evidence
    same = replace(a, id="duplicate-overlap")
    hits = [Hit(a, 1, "bm25", 1), Hit(same, 0.9, "bm25", 2), Hit(b, 0.8, "bm25", 3)]
    context = assemble("What are the policies?", hits, settings)
    assert len(context.evidence) == 2
    assert any(r["reason"] == "overlap" for r in context.excluded)
    assert context.input_tokens_estimate + settings.answer_tokens <= settings.context_tokens
    huge = replace(a, text=" ".join(["multisyllabic-word"] * 2000), end=100000)
    context = assemble(
        "What are the policies?", [Hit(huge, 1, "bm25", 1), Hit(b, 0.8, "bm25", 2)], settings
    )
    assert any(r["reason"] == "token_budget" for r in context.excluded)
    assert b in context.evidence


def test_ids_quotes_and_claim_structure(system, ingest):
    settings, repo, _, _, retriever = system
    ingest("Returns are accepted for 30 days.")
    result = retriever.search(repo.snapshot("sample"), "Returns", "bm25", 5)
    context = assemble("Returns", result.hits, settings)
    cid = context.evidence[0].id
    assert validate_citations(proposal(cid, "Returns are accepted\nfor 30 days."), context)
    for p in [
        proposal("invented"),
        proposal(cid, "Returns are accepted for 300 days."),
        Proposal(status="answered", claims=[], missing_information=[]),
        Proposal(
            status="answered",
            claims=[Claim(text="Unsupported", evidence_ids=[], quotes=[])],
            missing_information=[],
        ),
        Proposal(
            status="conflicting_evidence", claims=proposal(cid).claims, missing_information=[]
        ),
    ]:
        with pytest.raises(DomainError):
            validate_citations(p, context)


class Stub:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return Completion(
            self.output, "test-provider", {"prompt_tokens": 1, "completion_tokens": 1}, 1
        )


@pytest.mark.parametrize(
    "output,expected",
    [
        ("not json", "invalid_generated_output"),
        ('{"status":"answered","claims":[],"missing_information":[]}', "invalid_generated_output"),
        ("x" * 25000, "invalid_generated_output"),
        (DomainError("provider_unavailable", "Timeout", 503), "provider_unavailable"),
        (
            '{"status":"insufficient_evidence","claims":[],"missing_information":["No delivery guarantee is specified."]}',
            "insufficient_evidence",
        ),
    ],
)
def test_invalid_output_and_provider_failures(system, ingest, output, expected):
    settings, repo, _, _, retriever = system
    ingest("Returns are accepted for 30 days.")
    result = retriever.search(repo.snapshot("sample"), "Returns", "bm25", 5)
    stub = Stub(output)
    answer, trace = Answerer(settings, stub).answer("Returns", result, "request")
    assert answer["status"] == expected
    assert stub.calls <= 2
    if expected == "invalid_generated_output":
        assert trace["validation_failures"]
    if expected == "provider_unavailable":
        assert stub.calls == 1 and answer["usage"] is None


def test_supported_conflict_and_empty_evidence(system, ingest):
    settings, repo, _, _, retriever = system
    ingest("Returns are accepted for 30 days.")
    ingest("Returns are accepted for 14 days.", title="Other")
    search = retriever.search(repo.snapshot("sample"), "Returns", "bm25", 5)
    ids = [h.evidence.id for h in search.hits]
    answer, _ = Answerer(
        settings, Stub(proposal(ids[0], search.hits[0].evidence.text).model_dump_json())
    ).answer("Returns", search, "req")
    assert answer["status"] == "answered" and answer["structural_validation"] == "passed"
    conflict = Proposal(
        status="conflicting_evidence",
        claims=[Claim(text="Policies disagree.", evidence_ids=ids, quotes=[])],
        missing_information=[],
    )
    answer, _ = Answerer(settings, Stub(conflict.model_dump_json())).answer(
        "Returns", search, "req"
    )
    assert answer["status"] == "conflicting_evidence" and len(answer["citations"]) == 2
    empty = retriever.search(repo.snapshot("private"), "Returns", "bm25", 5)
    stub = Stub("not json")
    answer, _ = Answerer(settings, stub).answer("Returns", empty, "req")
    assert answer["status"] == "insufficient_evidence" and stub.calls == 0


def test_real_http_adapter_envelope_retry_timeout_and_bounds(system):
    settings, *_ = system
    settings = settings.model_copy(
        update={
            "provider_url": "https://example.test/v1",
            "provider_model": "fixture-http",
            "provider_api_key": "test-placeholder",
            "provider_retries": 1,
        }
    )
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "model": "fixture-http",
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            },
        )

    provider = CompatibleProvider(settings, httpx.MockTransport(handler))
    result = provider.complete([{"role": "user", "content": "JSON please"}])
    assert result.attempts == 2 and result.usage["prompt_tokens"] == 5
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    assert calls[0]["max_tokens"] == settings.answer_tokens
    provider.close()
    for handler, code in [
        (lambda _: httpx.Response(200, content=b"x" * 70000), "invalid_generated_output"),
        (lambda _: httpx.Response(401), "provider_unavailable"),
        (lambda _: httpx.Response(200, json={"choices": []}), "invalid_generated_output"),
    ]:
        with pytest.raises(DomainError) as caught:
            provider = CompatibleProvider(settings, httpx.MockTransport(handler))
            provider.complete([])
        assert caught.value.code == code
        provider.close()

    def timeout(request):
        raise httpx.ReadTimeout("test timeout", request=request)

    provider = CompatibleProvider(settings, httpx.MockTransport(timeout))
    with pytest.raises(DomainError) as caught:
        provider.complete([])
    assert caught.value.code == "provider_unavailable"
    provider.close()
