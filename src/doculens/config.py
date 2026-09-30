from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCULENS_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///var/doculens.db"
    storage_dir: Path = Path("var/files")
    admin_token: str = ""
    model_backend: Literal["sentence_transformer", "fixture"] = "sentence_transformer"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    embedding_dimension: int = 384
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    reranker_revision: str = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    cpu_threads: int = Field(2, ge=1, le=8)
    inference_concurrency: int = Field(1, ge=1, le=4)
    chunk_tokens: int = Field(180, ge=32, le=500)
    chunk_overlap: int = Field(32, ge=0, le=100)
    upload_bytes: int = Field(10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    extracted_chars: int = Field(2_000_000, ge=1000)
    max_chunks: int = Field(2000, ge=1, le=10000)
    bm25_k1: float = Field(1.5, gt=0)
    bm25_b: float = Field(0.75, ge=0, le=1)
    candidate_limit: int = Field(20, ge=5, le=100)
    rrf_constant: int = Field(60, ge=1)
    lexical_weight: float = Field(1, gt=0)
    dense_weight: float = Field(1, gt=0)
    context_tokens: int = Field(4096, ge=512, le=32768)
    answer_tokens: int = Field(700, ge=100, le=4096)
    context_chunks: int = Field(6, ge=1, le=12)
    generation_mode: Literal["disabled", "fixture", "provider"] = "disabled"
    provider_url: str = "http://127.0.0.1:11434/v1"
    provider_model: str = ""
    provider_model_revision: str | None = None
    provider_token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    provider_temperature: float | None = Field(None, ge=0, le=2)
    provider_api_key: str = ""
    provider_timeout: float = Field(30, gt=0, le=120)
    provider_retries: int = Field(1, ge=0, le=2)
    provider_repair_attempts: int = Field(1, ge=0, le=1)
    provider_output_bytes: int = Field(20000, ge=100, le=100000)
    provider_concurrency: int = Field(2, ge=1, le=8)
    job_lease_seconds: int = Field(300, ge=5, le=3600)
    job_attempts: int = Field(3, ge=1, le=5)
    trace_retention_days: int = Field(7, ge=1, le=30)
    log_level: str = "INFO"

    @model_validator(mode="after")
    def compatible(self):
        provider = urlparse(self.provider_url)
        if (
            provider.scheme not in {"http", "https"}
            or not provider.hostname
            or provider.username
            or provider.password
        ):
            raise ValueError(
                "provider_url must be an HTTP(S) endpoint without embedded credentials"
            )
        if self.embedding_dimension != 384:
            raise ValueError("Schema supports 384 dimensions; a different model needs a migration")
        if self.chunk_overlap >= self.chunk_tokens:
            raise ValueError("chunk_overlap must be smaller than chunk_tokens")
        if self.answer_tokens + 256 >= self.context_tokens:
            raise ValueError("context_tokens must reserve room for instructions and evidence")
        if self.generation_mode == "provider" and not (
            self.provider_api_key and self.provider_model
        ):
            raise ValueError("Provider mode requires provider_api_key and provider_model")
        if self.admin_token and len(self.admin_token) < 24:
            raise ValueError("admin_token must be at least 24 characters")
        return self

    @cached_property
    def embedding_fingerprint(self) -> str:
        if self.model_backend == "fixture":
            return "fixture:sha256-token-hash:384:v1"
        return f"{self.embedding_model}@{self.embedding_revision}:384:normalized"

    def public_config(self) -> dict:
        return self.model_dump(
            exclude={"admin_token", "provider_api_key", "database_url", "storage_dir"}
        )
