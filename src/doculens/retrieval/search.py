import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

import numpy as np
from rank_bm25 import BM25Okapi

from doculens.errors import DomainError
from doculens.ingestion.parsing import sha
from doculens.retrieval.models import tokenize
from doculens.storage.repository import Evidence, Snapshot

Method = Literal["bm25", "dense", "hybrid", "reranked"]


@dataclass(frozen=True)
class Hit:
    evidence: Evidence
    score: float
    score_type: str
    rank: int

    def public(self) -> dict:
        return {
            "evidence": self.evidence.public(),
            "rank": self.rank,
            "score": self.score,
            "score_type": self.score_type,
        }


@dataclass(frozen=True)
class SearchResult:
    snapshot: Snapshot
    method: str
    hits: tuple[Hit, ...]
    stages: dict
    timings: dict


def rrf(lexical: list[Hit], dense: list[Hit], constant: int, weights=(1.0, 1.0)) -> list[Hit]:
    scores: dict[str, float] = {}
    evidence: dict[str, Evidence] = {}
    for ranked, weight in zip((lexical, dense), weights, strict=True):
        seen = set()
        for hit in ranked:
            cid = hit.evidence.id
            if cid in seen:
                continue
            seen.add(cid)
            evidence[cid] = hit.evidence
            scores[cid] = scores.get(cid, 0) + weight / (constant + hit.rank)
    return [
        Hit(evidence[cid], float(score), "rrf", i)
        for i, (cid, score) in enumerate(sorted(scores.items(), key=lambda v: (-v[1], v[0])), 1)
    ]


class Retriever:
    def __init__(self, settings, models):
        self.settings, self.models = settings, models
        self.cache = OrderedDict()
        self.cache_lock = threading.Lock()

    def clear(self):
        with self.cache_lock:
            self.cache.clear()

    def lexical(self, snapshot: Snapshot, question: str) -> list[Hit]:
        if not snapshot.evidence:
            return []
        key = sha(
            json.dumps(
                {
                    "scope": snapshot.scope,
                    "manifest": snapshot.manifest,
                    "tokenizer": "unicode-casefold-identifiers-v1",
                    "k1": self.settings.bm25_k1,
                    "b": self.settings.bm25_b,
                },
                sort_keys=True,
            )
        )
        with self.cache_lock:
            cached = self.cache.get(key)
        if cached is None:
            terms = [tokenize(e.text) for e in snapshot.evidence]
            model = BM25Okapi(terms, k1=self.settings.bm25_k1, b=self.settings.bm25_b)
            cached = (model, [set(t) for t in terms])
            with self.cache_lock:
                self.cache[key] = cached
                while len(self.cache) > 4:
                    self.cache.popitem(last=False)
        model, word_sets = cached
        query = tokenize(question)
        scores = model.get_scores(query)
        eligible = [i for i, words in enumerate(word_sets) if set(query) & words]
        order = sorted(eligible, key=lambda i: (-scores[i], snapshot.evidence[i].id))
        return [
            Hit(snapshot.evidence[i], float(scores[i]), "bm25", rank)
            for rank, i in enumerate(order[: self.settings.candidate_limit], 1)
        ]

    def dense(self, snapshot: Snapshot, question: str) -> list[Hit]:
        if not snapshot.evidence:
            return []
        if any(
            e.embedding_fingerprint != self.models.fingerprint
            or len(e.embedding) != self.models.dimension
            for e in snapshot.evidence
        ):
            raise DomainError(
                "embedding_incompatible", "Reindex corpus with the configured embedding model", 409
            )
        query = np.asarray(self.models.encode([question])[0], dtype=np.float32)
        matrix = np.asarray([e.embedding for e in snapshot.evidence], dtype=np.float32)
        scores = matrix @ query  # normalized dot product = cosine similarity; exact scan
        if not np.isfinite(scores).all():
            raise DomainError("invalid_embedding", "Stored embeddings contain invalid values", 503)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], snapshot.evidence[i].id))
        return [
            Hit(snapshot.evidence[i], float(scores[i]), "cosine_similarity", rank)
            for rank, i in enumerate(order[: self.settings.candidate_limit], 1)
        ]

    def search(
        self, snapshot: Snapshot, question: str, method: Method, top_k: int = 5
    ) -> SearchResult:
        timings, stages = {}, {}
        lexical, dense = [], []
        started = time.perf_counter()
        if method in {"bm25", "hybrid", "reranked"}:
            mark = time.perf_counter()
            lexical = self.lexical(snapshot, question)
            timings["lexical_ms"] = (time.perf_counter() - mark) * 1000
            stages["lexical"] = [
                {"id": h.evidence.id, "rank": h.rank, "score": h.score} for h in lexical
            ]
        if method in {"dense", "hybrid", "reranked"}:
            mark = time.perf_counter()
            dense = self.dense(snapshot, question)
            timings["dense_with_query_embedding_ms"] = (time.perf_counter() - mark) * 1000
            stages["dense"] = [
                {"id": h.evidence.id, "rank": h.rank, "score": h.score} for h in dense
            ]
        if method == "bm25":
            final = lexical
        elif method == "dense":
            final = dense
        else:
            mark = time.perf_counter()
            final = rrf(
                lexical,
                dense,
                self.settings.rrf_constant,
                (self.settings.lexical_weight, self.settings.dense_weight),
            )[: self.settings.candidate_limit]
            timings["fusion_ms"] = (time.perf_counter() - mark) * 1000
            stages["fused"] = [
                {"id": h.evidence.id, "rank": h.rank, "score": h.score} for h in final
            ]
            if method == "reranked" and final:
                mark = time.perf_counter()
                scores = self.models.rerank(question, [h.evidence.text for h in final])
                order = sorted(
                    zip(final, scores, strict=True), key=lambda v: (-v[1], v[0].evidence.id)
                )
                final = [
                    Hit(
                        hit.evidence,
                        score,
                        "cross_encoder_score"
                        if self.settings.model_backend == "sentence_transformer"
                        else "fixture_term_overlap",
                        i,
                    )
                    for i, (hit, score) in enumerate(order, 1)
                ]
                timings["reranking_ms"] = (time.perf_counter() - mark) * 1000
        timings["retrieval_total_ms"] = (time.perf_counter() - started) * 1000
        return SearchResult(snapshot, method, tuple(final[:top_k]), stages, timings)
