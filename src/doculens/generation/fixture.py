"""Scripted demo responses only. Never used to score model answer quality."""

import json
from pathlib import Path

from doculens.generation.contracts import Claim, Proposal, Quote
from doculens.generation.provider import Completion


class FixtureProvider:
    def complete_context(self, question: str, context) -> Completion:
        path = Path(__file__).parents[3] / "data/sample/demo_answers.json"
        scenarios = json.loads(path.read_text()) if path.exists() else {}
        scenario = scenarios.get(question)
        claims = []
        status = "insufficient_evidence"
        missing = [
            "Fixture mode only supports the documented demo questions. Configure a provider for live answers."
        ]
        if scenario:
            for item in scenario.get("claims", []):
                matching = next(
                    (
                        e
                        for e in context.evidence
                        if item["span"] in e.text and e.title == item["title"]
                    ),
                    None,
                )
                if matching:
                    claims.append(
                        Claim(
                            text=item["text"],
                            evidence_ids=[matching.id],
                            quotes=[Quote(evidence_id=matching.id, span=item["span"])],
                        )
                    )
            if len(claims) == len(scenario.get("claims", [])):
                status, missing = scenario["status"], scenario.get("missing_information", [])
            else:
                claims = []
                missing = ["The scripted fixture evidence is not in the selected context."]
        proposal = Proposal.model_validate(
            {
                "status": status,
                "claims": [c.model_dump() for c in claims],
                "missing_information": missing,
            }
        )
        return Completion(proposal.model_dump_json(), "scripted-demo-fixture-v1", None, 1)
