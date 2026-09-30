from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from doculens.retrieval.search import Method


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    corpus: Literal["sample", "private"] = "sample"
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    method: Method = "hybrid"
    top_k: int = Field(5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Question must contain at least three non-whitespace characters")
        return value.strip()


class SearchResponse(BaseModel):
    request_id: str
    corpus_revision: int
    corpus_manifest: str
    method: str
    embedding_model: str
    results: list[dict]
    timings: dict[str, float]


class AnswerResponse(BaseModel):
    request_id: str
    corpus_revision: int
    corpus_manifest: str
    method: str
    generation_mode: str
    model: str | None
    status: Literal[
        "answered",
        "insufficient_evidence",
        "conflicting_evidence",
        "provider_unavailable",
        "invalid_generated_output",
    ]
    answer: str
    claims: list[dict]
    citations: list[dict]
    missing_information: list[str]
    timings: dict[str, float]
    usage: dict | None
    structural_validation: str


class UploadResponse(BaseModel):
    document_id: str
    version_id: str
    job_id: str
    duplicate: bool
