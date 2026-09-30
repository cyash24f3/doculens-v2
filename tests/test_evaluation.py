from pathlib import Path

from doculens.evaluation.metrics import aggregate, paired_bootstrap, retrieval_metrics
from doculens.evaluation.runner import load_dataset


def test_hit_and_evidence_recall_have_different_denominators():
    metrics = retrieval_metrics(["a", "a", "noise"], [{"a", "a-overlap"}, {"b"}], 5)
    assert (
        metrics["hit"] == 1
        and metrics["evidence_group_recall"] == 0.5
        and metrics["full_evidence"] == 0
    )
    assert metrics["mrr"] == 1
    missing = retrieval_metrics(["a"], [], 5)
    assert all(v is None for v in missing.values())
    assert retrieval_metrics(["noise"], [{"a"}], 5)["mrr"] == 0
    rows = [
        {
            "question_id": "q",
            "leakage_group": "g",
            "metrics": metrics,
            "timings": {"retrieval_total_ms": 1},
            "error": None,
        },
        {
            "question_id": "missing",
            "leakage_group": "other",
            "metrics": missing,
            "timings": {"retrieval_total_ms": 2},
            "error": None,
        },
    ]
    result = aggregate(rows)
    assert result["answerable"] == 1 and result["unanswerable"] == 1 and result["hit"] == 1
    interval = paired_bootstrap(rows, rows)
    assert (
        interval["mean_difference"] == 0
        and interval["ci95"] == [0, 0]
        and interval["independent_groups"] == 1
    )


def test_frozen_splits_and_provenance():
    path = Path("benchmarks/questions.jsonl")
    dev = load_dataset(path, "dev")
    test = load_dataset(path, "test")
    assert len(dev) == 60 and len(test) == 140
    assert {q["leakage_group"] for q in dev}.isdisjoint({q["leakage_group"] for q in test})
    assert sum(q["expected_status"] == "insufficient_evidence" for q in dev + test) == 55
    assert all(q["AI_generated"] and not q["human_reviewed"] for q in dev + test)
    assert any(q["track"] == "public" for q in test)
