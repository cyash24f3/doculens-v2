# DocuLens measured retrieval report

Split: **test**, questions: **140**, model backend: **onnx**.
All labels are AI-authored and not human-reviewed. Corpus includes fictional support policies and independently sourced Python documentation. These results describe this benchmark only.

| Method | Answerable | Missing | Hit@5 | Group recall@5 | MRR@5 | Full evidence@5 | Warm p50 ms | Warm p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 103 | 37 | 0.913 | 0.903 | 0.813 | 0.893 | 1.6 | 3.1 |
| dense | 103 | 37 | 0.951 | 0.908 | 0.787 | 0.893 | 10.9 | 20.8 |
| hybrid | 103 | 37 | 0.932 | 0.917 | 0.808 | 0.913 | 12.7 | 22.6 |
| reranked | 103 | 37 | 0.971 | 0.942 | 0.899 | 0.932 | 647.9 | 1135.2 |

Hit counts any relevant passage. Group recall requires at least 95% union coverage of a canonical gold text span; alternatives within a group are interchangeable. Full coverage requires all groups. MRR is truncated to the five returned results. Missing-information cases are excluded from these quality denominators, but included in latency counts. Retrieval relevance does not measure answer correctness.

## Failures and fixes

### bm25
- **warranty-multi-0**: For replacement and warranty policy, what are the rules on coverage and resellers? Coverage: [0.0, 1.0]; error: None. Inspect ranked passages and first-stage pools in `bm25.jsonl`.
- **orders-4**: What is the gift-note character limit? Coverage: [0.0]; error: None. Inspect ranked passages and first-stage pools in `bm25.jsonl`.
- **orders-multi-1**: For order changes procedure, what are the rules on preorders and gift notes? Coverage: [0.0, 1.0]; error: None. Inspect ranked passages and first-stage pools in `bm25.jsonl`.
### dense
- **wifi-multi-1**: For beacon wi-fi troubleshooting, what are the rules on captive portal and firmware? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `dense.jsonl`.
- **payments-multi-1**: For payment handling, what are the rules on invoice changes and duplicate charge? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `dense.jsonl`.
- **integrations-multi-1**: For webhook integration guide, what are the rules on deduplication and secret rotation? Coverage: [0.0, 1.0]; error: None. Inspect ranked passages and first-stage pools in `dense.jsonl`.
### hybrid
- **wifi-multi-1**: For beacon wi-fi troubleshooting, what are the rules on captive portal and firmware? Coverage: [1.0, 0.0]; error: None. Inspect ranked passages and first-stage pools in `hybrid.jsonl`.
- **python-venv-0**: Can venv environments be moved safely to another location? Coverage: [0.4279661016949153]; error: None. Inspect ranked passages and first-stage pools in `hybrid.jsonl`.
- **python-venv-1**: Do I need to activate a venv to use its interpreter? Coverage: [0.0]; error: None. Inspect ranked passages and first-stage pools in `hybrid.jsonl`.
### reranked
- **warranty-multi-0**: For replacement and warranty policy, what are the rules on coverage and resellers? Coverage: [0.0, 1.0]; error: None. Inspect ranked passages and first-stage pools in `reranked.jsonl`.
- **integrations-multi-1**: For webhook integration guide, what are the rules on deduplication and secret rotation? Coverage: [0.0, 1.0]; error: None. Inspect ranked passages and first-stage pools in `reranked.jsonl`.
- **python-venv-1**: Do I need to activate a venv to use its interpreter? Coverage: [0.6590038314176245]; error: None. Inspect ranked passages and first-stage pools in `reranked.jsonl`.

Potential fixes must be tested on development data: improve section boundaries for long RST directives, retrieve larger bounded pools, and examine evidence diversity before adopting reranking. Semantic answer evaluation requires the separate rubric and review file. No paid calls are required for this retrieval report.

## Paired uncertainty

Differences are paired against BM25. Bootstrap seed 42, 1000 draws; entire source/theme groups are resampled to avoid assuming correlated questions are independent. Small group counts make these intervals exploratory.

```json
{
  "dense": {
    "mean_difference": 0.038834951456310676,
    "ci95": [
      0.0,
      0.09615384615384616
    ],
    "independent_groups": 12,
    "resampling_unit": "source/theme leakage group",
    "seed": 42,
    "bootstrap_samples": 1000
  },
  "hybrid": {
    "mean_difference": 0.019417475728155338,
    "ci95": [
      -0.0196078431372549,
      0.06797782219683988
    ],
    "independent_groups": 12,
    "resampling_unit": "source/theme leakage group",
    "seed": 42,
    "bootstrap_samples": 1000
  },
  "reranked": {
    "mean_difference": 0.05825242718446602,
    "ci95": [
      0.0,
      0.12149532710280374
    ],
    "independent_groups": 12,
    "resampling_unit": "source/theme leakage group",
    "seed": 42,
    "bootstrap_samples": 1000
  }
}
```

## Provenance

See `manifest.json`, `summary.json`, and method JSONL files for hashes, exact configuration, pinned model revisions, hardware, memory, timing, and every failure. Provider usage and cost: unavailable when generation is not run.
