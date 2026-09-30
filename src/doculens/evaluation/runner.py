import json
import platform
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from doculens.errors import DomainError
from doculens.evaluation.metrics import (
    aggregate,
    paired_bootstrap,
    retrieval_metrics,
    span_coverage,
)
from doculens.generation.context import PROMPT_VERSION
from doculens.ingestion.parsing import sha
from doculens.storage.models import Document, Experiment, Version, uid

ROOT = Path(__file__).parents[3]


def provenance(settings, snapshot, dataset_path, split):
    try:
        git = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        git = "uncommitted-initial-build"
    return {
        "git_revision": git,
        "dataset_sha256": sha(dataset_path.read_bytes()),
        "source_manifest_sha256": sha((ROOT / "data/source_manifest.json").read_bytes()),
        "dependency_lock_sha256": sha((ROOT / "uv.lock").read_bytes()),
        "split_manifest_sha256": sha((ROOT / "benchmarks/splits.json").read_bytes()),
        "corpus_manifest": snapshot.manifest,
        "corpus_revision": snapshot.revision,
        "configuration": settings.public_config(),
        "model_backend": settings.model_backend,
        "prompt_version": PROMPT_VERSION,
        "split": split,
        "hardware": {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "search": "exact normalized vector scan; no ANN",
        "human_reviewed": False,
        "semantic_answer_judge": None,
        "conditions": "single-threaded questions, warm models after explicit warmup",
        "timestamp_utc_epoch": time.time(),
    }


def load_dataset(path: Path, split: str):
    questions = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Duplicate question IDs")
    group_splits = defaultdict(set)
    for q in questions:
        group_splits[q["leakage_group"]].add(q["split"])
    if any(len(splits) > 1 for splits in group_splits.values()):
        raise ValueError("Related source/theme groups leak across splits")
    return (
        [q for q in questions if q["split"] == split]
        if split != "ci"
        else [
            q
            for q in questions
            if q["id"]
            in {
                "returns-0",
                "wifi-1",
                "shipping-4",
                "warranty-1",
                "harbor-term",
                "missing-0",
                "python-venv-0",
                "python-zipfile-0",
            }
        ]
    )


def resolve_gold(repo, snapshot, questions):
    manifest = {s["key"]: s for s in json.loads((ROOT / "data/source_manifest.json").read_text())}
    with repo.db.transaction() as session:
        rows = session.execute(
            select(Version, Document).join(Document).where(Version.id.in_(snapshot.versions))
        ).all()
        by_hash = {v.raw_sha256: (v, d) for v, d in rows}
        resolved = {}
        for q in questions:
            groups = []
            for alternatives in q["gold_groups"]:
                spans = []
                for span in alternatives:
                    source = manifest[span["source_key"]]
                    if (
                        source["sha256"] != span["version_sha256"]
                        or span["version_sha256"] not in by_hash
                    ):
                        raise ValueError(
                            "Benchmark source version is missing or changed: " + span["source_key"]
                        )
                    v, d = by_hash[span["version_sha256"]]
                    if v.extracted_text[span["start"] : span["end"]] != span["text"]:
                        raise ValueError("Gold source span does not match extraction: " + q["id"])
                    relevant = [
                        e.id
                        for e in snapshot.evidence
                        if e.version_id == v.id
                        and min(e.end, span["end"]) - max(e.start, span["start"])
                        >= min(24, span["end"] - span["start"])
                    ]
                    if not relevant:
                        raise ValueError("Gold span does not resolve to chunks: " + q["id"])
                    spans.append(
                        {**span, "resolved_version_id": v.id, "resolved_chunk_ids": relevant}
                    )
                groups.append(spans)
            resolved[q["id"]] = groups
        return resolved


def run_benchmark(
    repo, retriever, split="dev", output=Path("outputs"), answerer=None, max_questions=None
):
    path = ROOT / "benchmarks/questions.jsonl"
    questions = load_dataset(path, split)
    if max_questions:
        questions = questions[:max_questions]
    snapshot = repo.snapshot("sample")
    gold = resolve_gold(repo, snapshot, questions)
    if not snapshot.evidence:
        raise ValueError("Seed the sample corpus first")
    if answerer and repo.settings.generation_mode == "fixture":
        raise ValueError("Scripted fixtures cannot be used to score answer quality")
    # Explicit warm-up keeps model download/cold inference out of reported warm latencies.
    for method in ("bm25", "dense", "hybrid", "reranked"):
        retriever.search(snapshot, "What are the return conditions?", method, 5)
    run_id = uid()
    directory = output / run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = provenance(repo.settings, snapshot, path, split)
    manifest.update(
        run_id=run_id,
        k=5,
        question_count=len(questions),
        output_path=str(directory),
        model_memory=retriever.models.memory,
        run_purpose="controlled comparison; no held-out tuning",
    )
    results: dict[str, list[dict]] = {
        method: [] for method in ("bm25", "dense", "hybrid", "reranked")
    }
    answer_rows = []
    for q in questions:
        resolved = gold[q["id"]]
        sets = [set(cid for s in group for cid in s["resolved_chunk_ids"]) for group in resolved]
        for method in results:
            try:
                search = retriever.search(snapshot, q["question"], method, 5)
                ranked = [h.evidence.id for h in search.hits]
                metrics = retrieval_metrics(ranked, sets, 5)
                if resolved:
                    coverage = [
                        max(span_coverage(s, [h.evidence for h in search.hits]) for s in group)
                        for group in resolved
                    ]
                    metrics["evidence_group_recall"] = sum(v >= 0.95 for v in coverage) / len(
                        coverage
                    )
                    metrics["full_evidence"] = float(all(v >= 0.95 for v in coverage))
                else:
                    coverage = []
                row = {
                    "question_id": q["id"],
                    "family_id": q["family_id"],
                    "leakage_group": q["leakage_group"],
                    "question": q["question"],
                    "expected_status": q["expected_status"],
                    "type": q["type"],
                    "track": q["track"],
                    "source_kinds": sorted({h.evidence.source_kind for h in search.hits}),
                    "required_groups": len(resolved),
                    "method": method,
                    "metrics": metrics,
                    "span_coverage": coverage,
                    "ranked": [h.public() for h in search.hits],
                    "gold": resolved,
                    "stages": search.stages,
                    "timings": search.timings,
                    "error": None,
                }
                if answerer:
                    full = retriever.search(
                        snapshot, q["question"], method, repo.settings.candidate_limit
                    )
                    answer, trace = answerer.answer(q["question"], full, uid())
                    # These checks are observable contracts, not semantic correctness scores.
                    answer_rows.append(
                        {
                            "question_id": q["id"],
                            "method": method,
                            "answer": answer,
                            "trace": trace,
                            "reference": q["reference_answer"],
                            "required_conditions": q["required_conditions"],
                            "expected_status": q["expected_status"],
                            "machine_checks": {
                                "status_matches": answer["status"] == q["expected_status"],
                                "structural_validation": answer["structural_validation"],
                                "correctness_0_2": None,
                                "claim_support": None,
                                "policy_condition_preservation": None,
                            },
                            "human_reviewed": False,
                        }
                    )
            except DomainError as e:
                row = {
                    "question_id": q["id"],
                    "family_id": q["family_id"],
                    "leakage_group": q["leakage_group"],
                    "question": q["question"],
                    "expected_status": q["expected_status"],
                    "type": q["type"],
                    "track": q["track"],
                    "required_groups": len(resolved),
                    "method": method,
                    "metrics": retrieval_metrics([], sets, 5),
                    "ranked": [],
                    "gold": resolved,
                    "stages": {},
                    "timings": {},
                    "error": e.code,
                }
            results[method].append(row)
    summary = {method: aggregate(rows) for method, rows in results.items()}
    breakdowns = {}
    for dimension in ("type", "track", "required_groups"):
        breakdowns[dimension] = {
            str(value): {
                method: aggregate([r for r in rows if r[dimension] == value])
                for method, rows in results.items()
            }
            for value in sorted({r[dimension] for r in results["bm25"]}, key=str)
        }
    paired = {
        method: paired_bootstrap(results["bm25"], results[method])
        for method in results
        if method != "bm25"
    }
    failures = {
        method: [r["question_id"] for r in rows if r["metrics"]["full_evidence"] == 0 or r["error"]]
        for method, rows in results.items()
    }
    full_summary = {
        "methods": summary,
        "breakdowns": breakdowns,
        "paired_vs_bm25_hit": paired,
        "failures": failures,
        "answer_evaluation": "not_run"
        if not answerer
        else "machine structural/status checks only; semantic review pending",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (directory / "summary.json").write_text(json.dumps(full_summary, indent=2) + "\n")
    for method, rows in results.items():
        (directory / (method + ".jsonl")).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        )
    if answerer:
        (directory / "answers.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in answer_rows)
        )
    report = [
        "# DocuLens measured retrieval report",
        "",
        f"Split: **{split}**, questions: **{len(questions)}**, model backend: **{repo.settings.model_backend}**.",
        "All labels are AI-authored and not human-reviewed. Corpus includes fictional support policies and independently sourced Python documentation. These results describe this benchmark only.",
        "",
        "| Method | Answerable | Missing | Hit@5 | Group recall@5 | MRR@5 | Full evidence@5 | Warm p50 ms | Warm p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, s in summary.items():
        report.append(
            f"| {method} | {s['answerable']} | {s['unanswerable']} | {s['hit']:.3f} | {s['evidence_group_recall']:.3f} | {s['mrr']:.3f} | {s['full_evidence']:.3f} | {s['latency_ms_p50']:.1f} | {s['latency_ms_p95']:.1f} |"
        )
    report += [
        "",
        "Hit counts any relevant passage. Group recall requires at least 95% union coverage of a canonical gold text span; alternatives within a group are interchangeable. Full coverage requires all groups. MRR is truncated to the five returned results. Missing-information cases are excluded from these quality denominators, but included in latency counts. Retrieval relevance does not measure answer correctness.",
        "",
        "## Failures and fixes",
        "",
    ]
    for method, rows in results.items():
        failed = [r for r in rows if r["metrics"]["full_evidence"] == 0 or r["error"]][:3]
        report.append(f"### {method}")
        if not failed:
            report.append(
                "No full-evidence failures observed in this split; this is not universal accuracy."
            )
        for r in failed:
            report.append(
                f"- **{r['question_id']}**: {r['question']} Coverage: {r.get('span_coverage')}; error: {r['error']}. Inspect ranked passages and first-stage pools in `{method}.jsonl`."
            )
    report += [
        "",
        "Potential fixes must be tested on development data: improve section boundaries for long RST directives, retrieve larger bounded pools, and examine evidence diversity before adopting reranking. Semantic answer evaluation requires the separate rubric and review file. No paid calls are required for this retrieval report.",
        "",
        "## Paired uncertainty",
        "",
        "Differences are paired against BM25. Bootstrap seed 42, 1000 draws; entire source/theme groups are resampled to avoid assuming correlated questions are independent. Small group counts make these intervals exploratory.",
        "",
        "```json",
        json.dumps(paired, indent=2),
        "```",
        "",
        "## Provenance",
        "",
        "See `manifest.json`, `summary.json`, and method JSONL files for hashes, exact configuration, pinned model revisions, hardware, memory, timing, and every failure. Provider usage and cost: unavailable when generation is not run.",
    ]
    (directory / "report.md").write_text("\n".join(report) + "\n")
    # Persist only safe sample-corpus benchmark summaries, never private excerpts.
    with repo.db.transaction(write=True) as session:
        session.add(Experiment(id=run_id, manifest=manifest, summary=full_summary))
    return directory, full_summary
