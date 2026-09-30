import re

from doculens.errors import DomainError
from doculens.generation.contracts import Proposal


def normalized_quote(text: str) -> str:
    # Collapse whitespace only; preserve case, punctuation, Unicode, and numbers.
    return re.sub(r"\s+", " ", text).strip()


def validate_citations(proposal: Proposal, context) -> list[dict]:
    allowed = {e.id: e for e in context.evidence}
    citations: dict[str, dict] = {}
    if proposal.status == "answered" and not proposal.claims:
        raise DomainError(
            "invalid_generated_output", "Answered output requires at least one cited claim", 502
        )
    for index, claim in enumerate(proposal.claims):
        if not claim.evidence_ids:
            raise DomainError(
                "invalid_generated_output", "Every factual claim must cite supplied evidence", 502
            )
        for cid in claim.evidence_ids:
            if cid not in allowed:
                raise DomainError(
                    "invalid_generated_output",
                    "Generated citation was not supplied in context",
                    502,
                )
            citation = citations.setdefault(
                cid, {**allowed[cid].public(), "claim_indices": [], "quotes": []}
            )
            citation["claim_indices"].append(index)
        for quote in claim.quotes:
            if quote.evidence_id not in claim.evidence_ids:
                raise DomainError(
                    "invalid_generated_output",
                    "Quoted evidence must be cited by the same claim",
                    502,
                )
            if normalized_quote(quote.span) not in normalized_quote(
                allowed[quote.evidence_id].text
            ):
                raise DomainError(
                    "invalid_generated_output",
                    "Quoted text does not match the supplied passage",
                    502,
                )
            citations[quote.evidence_id]["quotes"].append(quote.span)
    if proposal.status == "conflicting_evidence" and len(citations) < 2:
        raise DomainError(
            "invalid_generated_output", "Conflict output must cite at least two passages", 502
        )
    if sum(len(v) for v in proposal.missing_information) > 3000:
        raise DomainError("invalid_generated_output", "Missing-information output is too long", 502)
    return list(citations.values())
