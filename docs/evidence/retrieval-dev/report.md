# DocuLens measured retrieval report

Split: **dev**, questions: **60**, model backend: **sentence_transformer**.
All labels are AI-authored and not human-reviewed. Corpus includes fictional support policies and independently sourced Python documentation. These results describe this benchmark only.

| Method | Answerable | Missing | Hit@5 | Group recall@5 | MRR@5 | Full evidence@5 | Warm p50 ms | Warm p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 42 | 18 | 1.000 | 0.976 | 0.859 | 0.952 | 0.3 | 0.4 |
| dense | 42 | 18 | 1.000 | 0.976 | 0.940 | 0.952 | 5.9 | 8.7 |
| hybrid | 42 | 18 | 1.000 | 0.964 | 0.952 | 0.929 | 4.0 | 5.3 |
| reranked | 42 | 18 | 1.000 | 1.000 | 0.937 | 1.000 | 106.5 | 139.1 |

Hit counts any relevant passage. Group recall requires at least 95% union coverage of a canonical gold text span; alternatives within a group are interchangeable. Full coverage requires all groups. MRR is truncated to the five returned results. Missing-information cases are excluded from these quality denominators, but included in latency counts. Retrieval relevance does not measure answer correctness.

## Failures and fixes

### bm25
- **exports-multi-0**: For data export procedure, what are the rules on permissions and format? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `bm25.jsonl`.
- **exports-multi-1**: For data export procedure, what are the rules on retention and size? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `bm25.jsonl`.
### dense
- **access-multi-1**: For account recovery, what are the rules on email change and shared accounts? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `dense.jsonl`.
- **battery-multi-1**: For atlas battery guide, what are the rules on swelling and runtime? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `dense.jsonl`.
### hybrid
- **exports-multi-0**: For data export procedure, what are the rules on permissions and format? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `hybrid.jsonl`.
- **exports-multi-1**: For data export procedure, what are the rules on retention and size? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `hybrid.jsonl`.
- **battery-multi-1**: For atlas battery guide, what are the rules on swelling and runtime? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `hybrid.jsonl`.
### reranked
No full-evidence failures observed in this split; this is not universal accuracy.

Potential fixes must be tested on development data: improve section boundaries for long RST directives, retrieve larger bounded pools, and examine evidence diversity before adopting reranking. Semantic answer evaluation requires the separate rubric and review file. No paid calls are required for this retrieval report.

## Paired uncertainty

Differences are paired against BM25. Bootstrap seed 42, 1000 draws; entire source/theme groups are resampled to avoid assuming correlated questions are independent. Small group counts make these intervals exploratory.

```json
{
  "dense": {
    "mean_difference": 0.0,
    "ci95": [
      0.0,
      0.0
    ],
    "independent_groups": 6,
    "resampling_unit": "source/theme leakage group",
    "seed": 42,
    "bootstrap_samples": 1000
  },
  "hybrid": {
    "mean_difference": 0.0,
    "ci95": [
      0.0,
      0.0
    ],
    "independent_groups": 6,
    "resampling_unit": "source/theme leakage group",
    "seed": 42,
    "bootstrap_samples": 1000
  },
  "reranked": {
    "mean_difference": 0.0,
    "ci95": [
      0.0,
      0.0
    ],
    "independent_groups": 6,
    "resampling_unit": "source/theme leakage group",
    "seed": 42,
    "bootstrap_samples": 1000
  }
}
```

## Provenance

See `manifest.json`, `summary.json`, and method JSONL files for hashes, exact configuration, pinned model revisions, hardware, memory, timing, and every failure. Provider usage and cost: unavailable when generation is not run.
