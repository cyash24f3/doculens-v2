import hashlib
import re
import threading
import time
from typing import Any

import numpy as np
import psutil

from doculens.config import Settings
from doculens.errors import DomainError


def tokenize(text: str) -> list[str]:
    # Preserve error codes and hyphenated IDs. No stemming or stop-word removal.
    return re.findall(r"[^\W_]+(?:[-_][^\W_]+)*", text.casefold(), flags=re.UNICODE)


class Models:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fingerprint = settings.embedding_fingerprint
        self.dimension = settings.embedding_dimension
        self.max_tokens = 256
        self.encoder: Any = None
        self.reranker: Any = None
        self.lock = threading.BoundedSemaphore(settings.inference_concurrency)
        self.load_lock = threading.Lock()
        self.loaded = False
        self.memory: dict = {}

    def initialize(self):
        with self.load_lock:
            if self.loaded:
                return
            before = psutil.Process().memory_info().rss
            started = time.perf_counter()
            if self.settings.model_backend == "sentence_transformer":
                import torch
                from sentence_transformers import SentenceTransformer

                torch.set_num_threads(self.settings.cpu_threads)
                self.encoder = SentenceTransformer(
                    self.settings.embedding_model,
                    revision=self.settings.embedding_revision,
                    device="cpu",
                    trust_remote_code=False,
                )
                self.max_tokens = self.encoder.max_seq_length
                if self.encoder.get_embedding_dimension() != self.dimension:
                    raise DomainError(
                        "embedding_dimension_mismatch",
                        "Loaded model is incompatible with schema",
                        503,
                    )
                if not self.encoder.tokenizer.is_fast:
                    raise DomainError(
                        "tokenizer_offsets_unavailable", "A fast tokenizer is required", 503
                    )
            if self.settings.chunk_tokens > self.max_tokens - 2:
                raise DomainError(
                    "chunk_model_limit", "Configured chunks exceed model input limit", 503
                )
            self.loaded = True
            self.memory = {
                "encoder_load_seconds": time.perf_counter() - started,
                "rss_before_bytes": before,
                "rss_encoder_bytes": psutil.Process().memory_info().rss,
                "dimension": self.dimension,
                "max_sequence_length": self.max_tokens,
            }

    def offsets(self, text: str) -> list[tuple[int, int]]:
        self.initialize()
        if self.encoder is None:
            return [m.span() for m in re.finditer(r"\S+", text)]
        return self.encoder.tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_offsets_mapping=True,
            verbose=False,
        )["offset_mapping"]

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.initialize()
        if any(len(self.offsets(t)) > self.max_tokens - 2 for t in texts):
            raise DomainError(
                "embedding_truncation", "Text would be truncated by the embedding model"
            )
        with self.lock:
            if self.encoder is not None:
                matrix = self.encoder.encode(
                    texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False
                )
            else:
                # Deterministic test double; not a semantic embedding model.
                matrix = np.zeros((len(texts), self.dimension), dtype=np.float32)
                for i, text in enumerate(texts):
                    for term in tokenize(text):
                        slot = (
                            int.from_bytes(hashlib.sha256(term.encode()).digest()[:4])
                            % self.dimension
                        )
                        matrix[i, slot] += 1
                norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                matrix /= np.maximum(norms, 1e-12)
            if matrix.shape != (len(texts), self.dimension) or not np.isfinite(matrix).all():
                raise DomainError("invalid_embedding", "Model returned invalid vectors", 503)
            return matrix.tolist()

    def rerank(self, question: str, passages: list[str]) -> list[float]:
        self.initialize()
        if self.settings.model_backend == "fixture":
            terms = set(tokenize(question))
            return [float(len(terms & set(tokenize(t)))) for t in passages]
        with self.load_lock:
            if self.reranker is None:
                from sentence_transformers import CrossEncoder

                started = time.perf_counter()
                self.reranker = CrossEncoder(
                    self.settings.reranker_model,
                    revision=self.settings.reranker_revision,
                    device="cpu",
                    trust_remote_code=False,
                )
                self.memory.update(
                    reranker_load_seconds=time.perf_counter() - started,
                    rss_reranker_bytes=psutil.Process().memory_info().rss,
                )
        # Reject silent pair truncation; query is already bounded at API validation.
        for passage in passages:
            tokens = self.reranker.tokenizer(question, passage, truncation=False)["input_ids"]
            if len(tokens) > self.reranker.max_length:
                raise DomainError(
                    "reranker_truncation", "Query/passage pair exceeds reranker input limit"
                )
        with self.lock:
            return [
                float(v)
                for v in self.reranker.predict(
                    [(question, t) for t in passages], batch_size=16, show_progress_bar=False
                )
            ]
