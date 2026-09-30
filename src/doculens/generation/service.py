import time

import tiktoken
from pydantic import ValidationError

from doculens.errors import DomainError
from doculens.generation.context import PROMPT_VERSION, assemble
from doculens.generation.contracts import Proposal
from doculens.generation.fixture import FixtureProvider
from doculens.generation.provider import CompatibleProvider
from doculens.generation.validation import validate_citations


class Answerer:
    def __init__(self, settings, provider=None):
        self.settings = settings
        self.provider = provider or (
            CompatibleProvider(settings)
            if settings.generation_mode == "provider"
            else FixtureProvider()
            if settings.generation_mode == "fixture"
            else None
        )

    def answer(self, question: str, search, request_id: str) -> tuple[dict, dict]:
        context = assemble(question, search.hits, self.settings)
        base = {
            "request_id": request_id,
            "corpus_revision": search.snapshot.revision,
            "corpus_manifest": search.snapshot.manifest,
            "method": search.method,
            "generation_mode": self.settings.generation_mode,
            "model": None,
            "answer": "",
            "claims": [],
            "citations": [],
            "missing_information": [],
            "timings": dict(search.timings),
            "usage": None,
            "structural_validation": "not_run",
        }
        trace = {
            "prompt_version": PROMPT_VERSION,
            "context_ids": [e.id for e in context.evidence],
            "context_excluded": list(context.excluded),
            "tokenizer": context.tokenizer,
            "context_input_tokens_estimate": context.input_tokens_estimate,
            "stages": search.stages,
            "validation_failures": [],
            "repair_version": "structural-feedback-v2",
        }
        if self.provider is None:
            return {
                **base,
                "status": "provider_unavailable",
                "answer": "Answer generation is disabled. Retrieval remains available.",
            }, trace
        if not context.evidence:
            return {
                **base,
                "status": "insufficient_evidence",
                "answer": "No eligible source passages were found.",
                "missing_information": [
                    "Upload or select a document containing the requested information."
                ],
            }, trace
        started = time.perf_counter()
        usage_records = []
        messages = list(context.messages)
        for attempt in range(self.settings.provider_repair_attempts + 1):
            try:
                completion = (
                    self.provider.complete_context(question, context)
                    if isinstance(self.provider, FixtureProvider)
                    else self.provider.complete(messages)
                )
                base["model"] = completion.model
                usage_records.append(completion.usage)
                trace.setdefault("provider_attempts", []).append(completion.attempts)
                if len(completion.text.encode()) > self.settings.provider_output_bytes:
                    raise DomainError(
                        "invalid_generated_output", "Generated output exceeded the size limit", 502
                    )
                proposal = Proposal.model_validate_json(completion.text)
                citations = validate_citations(proposal, context)
                base.update(
                    status=proposal.status,
                    claims=[c.model_dump() for c in proposal.claims],
                    citations=citations,
                    missing_information=proposal.missing_information,
                    answer="\n\n".join(c.text for c in proposal.claims)
                    or "The selected documents do not provide enough evidence.",
                    structural_validation="passed",
                )
                break
            except (ValidationError, DomainError) as e:
                code = e.code if isinstance(e, DomainError) else "invalid_generated_output"
                reason = (
                    e.message
                    if isinstance(e, DomainError)
                    else "Generated JSON did not match the typed schema"
                )
                trace["validation_failures"].append(
                    {"attempt": attempt + 1, "code": code, "reason": reason}
                )
                if (
                    code == "provider_unavailable"
                    or attempt >= self.settings.provider_repair_attempts
                ):
                    base.update(
                        status=code,
                        answer="The generation provider is unavailable."
                        if code == "provider_unavailable"
                        else "The generated response failed validation. Please retry.",
                    )
                    break
                # Do not echo malicious provider content or raw validation text in the repair prompt.
                repair = {
                    "role": "system",
                    "content": (
                        "Previous output failed structural validation: "
                        + reason
                        + ". JSON only: all claims cite supplied IDs; conflict claims cite two different passages; quotes exact or empty."
                    ),
                }
                repair_tokens = (
                    len(tiktoken.get_encoding("cl100k_base").encode(repair["content"])) + 8
                )
                if (
                    context.input_tokens_estimate + repair_tokens + self.settings.answer_tokens
                    > self.settings.context_tokens
                ):
                    trace["repair_skipped"] = "context_budget"
                    base.update(
                        status="invalid_generated_output",
                        answer="The generated response failed validation. Please retry.",
                    )
                    break
                trace["repair_input_tokens_estimate"] = (
                    context.input_tokens_estimate + repair_tokens
                )
                messages = list(context.messages) + [repair]
        base["usage"] = (
            {"calls": usage_records}
            if usage_records and all(u is not None for u in usage_records)
            else None
        )
        base["timings"]["generation_ms"] = (time.perf_counter() - started) * 1000
        return base, trace
