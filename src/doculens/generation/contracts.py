from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_id: str = Field(min_length=1, max_length=64)
    span: str = Field(min_length=1, max_length=2000)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(
        min_length=1,
        max_length=2000,
        description="A declarative answer statement supported by the evidence. Do not repeat the user question.",
    )
    evidence_ids: list[str] = Field(max_length=8)
    quotes: list[Quote] = Field(max_length=8)


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["answered", "insufficient_evidence", "conflicting_evidence"] = Field(
        description="answered when sources support the answer, conflicting_evidence when sources disagree, insufficient_evidence only when needed facts are missing"
    )
    claims: list[Claim] = Field(max_length=12)
    missing_information: list[str] = Field(max_length=8)
