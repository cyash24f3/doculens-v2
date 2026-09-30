# Live answer evaluation

12 frozen stratified test questions. Generator and automated judge: qwen2.5:7b-instruct. All runs use actual local provider calls, not fixtures.

**No human-reviewed answer score is available.** The judge is the same model and may share its errors. These exploratory machine judgments must be manually calibrated before making accuracy claims.

```json
{
  "questions": 12,
  "answerable": 10,
  "unanswerable": 2,
  "wrong_answer_status_on_unanswerable": 0,
  "unnecessary_abstention_status_on_answerable": 1,
  "technical_failures": 0,
  "automated_judged": 12,
  "judge_failures": 0,
  "automated_correctness_mean_0_2": 1.8333333333333333,
  "automated_condition_preservation_rate": 0.9166666666666666,
  "automated_citation_support_rate": 0.9166666666666666,
  "automated_citation_coverage_mean": 0.9166666666666666,
  "human_reviewed": 0,
  "judge_human_disagreement": null,
  "generation_ms_p50": 20176.23556200124,
  "generation_ms_p95": 31528.8477787908
}
```

## Observed failures

- **payments-multi-0**: For payment handling, what are the rules on supported methods and failure p402? Expected answered; observed insufficient_evidence. The answer is unsupported and insufficient because it claims there is no evidence, but it does not provide a detailed explanation of why the answer is unsupported. The required conditions are not preserved as the answer does not address the supported payment methods or the handling of failure code P402. There are no citations provided, and the answer does not cover the requested information.

Next: manually review a stratified sample, compare judge disagreements, and test stronger condition preservation on development questions. Provider token usage, citations, selected context, full references, and every judgment are in `answers.jsonl`. Local model calls have no provider fee; electricity/hardware are not priced. No cloud provider pricing estimate is made.
