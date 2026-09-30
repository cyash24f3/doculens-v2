from collections import defaultdict

import numpy as np


def retrieval_metrics(ranked_ids: list[str], gold_groups: list[set[str]], k: int) -> dict:
    """Small set-based contract used by CI; duplicate IDs never add evidence groups.

    Dataset runner additionally verifies source-span coverage before group credit.
    Empty gold is unanswerable and excluded from retrieval quality denominators.
    """
    if not gold_groups:
        return {"hit": None, "evidence_group_recall": None, "mrr": None, "full_evidence": None}
    top = set(ranked_ids[:k])
    relevant = set().union(*gold_groups)
    covered = sum(bool(top & g) for g in gold_groups)
    rank = next((i for i, cid in enumerate(ranked_ids, 1) if cid in relevant), None)
    return {
        "hit": float(bool(top & relevant)),
        "evidence_group_recall": covered / len(gold_groups),
        "mrr": 1 / rank if rank else 0.0,
        "full_evidence": float(covered == len(gold_groups)),
    }


def span_coverage(span: dict, evidence) -> float:
    intervals = sorted(
        (max(span["start"], e.start), min(span["end"], e.end))
        for e in evidence
        if e.version_id == span["resolved_version_id"]
        and e.end > span["start"]
        and e.start < span["end"]
    )
    covered, end = 0, span["start"]
    for a, b in intervals:
        covered += max(0, b - max(a, end))
        end = max(end, b)
    return covered / max(1, span["end"] - span["start"])


def aggregate(rows: list[dict]) -> dict:
    answerable = [r for r in rows if r["metrics"]["hit"] is not None]
    values = {
        key: float(np.mean([r["metrics"][key] for r in answerable])) if answerable else None
        for key in ("hit", "evidence_group_recall", "mrr", "full_evidence")
    }
    latency = [r["timings"]["retrieval_total_ms"] for r in rows if not r.get("error")]
    return {
        "questions": len(rows),
        "answerable": len(answerable),
        "unanswerable": len(rows) - len(answerable),
        "failures": sum(bool(r.get("error")) for r in rows),
        **values,
        "latency_ms_p50": float(np.percentile(latency, 50)) if latency else None,
        "latency_ms_p95": float(np.percentile(latency, 95)) if latency else None,
    }


def paired_bootstrap(
    left: list[dict], right: list[dict], metric: str = "hit", samples: int = 1000
) -> dict:
    groups = defaultdict(list)
    right_by_id = {r["question_id"]: r for r in right}
    for row in left:
        other = right_by_id[row["question_id"]]
        if row["metrics"][metric] is not None:
            groups[row["leakage_group"]].append(other["metrics"][metric] - row["metrics"][metric])
    rng = np.random.default_rng(42)
    keys = list(groups)
    if not keys:
        return {"mean_difference": None, "ci95": None, "independent_groups": 0}
    draws = [
        np.mean([v for key in rng.choice(keys, size=len(keys), replace=True) for v in groups[key]])
        for _ in range(samples)
    ]
    return {
        "mean_difference": float(np.mean([v for values in groups.values() for v in values])),
        "ci95": [float(v) for v in np.percentile(draws, [2.5, 97.5])],
        "independent_groups": len(keys),
        "resampling_unit": "source/theme leakage group",
        "seed": 42,
        "bootstrap_samples": samples,
    }
