# Acceptance evidence

Status reflects execution, not implementation intent. All quality results are bounded by the AI-authored labels and disclosed split exposure. No human semantic accuracy is claimed; remote checks are identified by their actual run/service evidence.

| Requested outcome | Status | Command or inspectable evidence |
|---|---|---|
| 1. Start from a clean checkout | verified | Fresh public GitHub clone, frozen uv install, lint/format/mypy, 36 passing tests/one unconfigured PostgreSQL skip, eight-question fixture benchmark, actual demo startup and three answer/citation/access checks: `evidence/clean-clone.json`. |
| 2. Ingest text/Markdown/text-bearing PDF and inspect provenance | verified | `doculens seed`; `tests/test_ingestion.py`; real-model `evidence/ingestion-profile.json` (nine ingestions); two visually inspected sample PDF pages; browser source screenshot. |
| 3. BM25/dense/hybrid/reranked against one active corpus | verified | `doculens benchmark --split test`; `evidence/retrieval-test/{manifest,summary}.json`, four method JSONL files and `report.md`; same-snapshot developer comparison screenshot/tests. |
| 4. Actual provider generation distinguished from fixtures | verified | Free local Ollama/Qwen 7B: `evidence/provider-api-smoke.json`, `local-provider-smoke-7b.json`, `answer-test/answers.jsonl`; UI mode badge. No purchased credential. |
| 5. Citations resolve to permitted source versions | verified | Actual API smoke source/trace flags; browser source screenshot; `test_api.py`, `test_generation.py` and scope/history/deletion tests. Semantic support is separately judged. |
| 6. Missing, conflict and provider failures | verified | Browser missing/conflict screenshots; actual local-model development smoke; HTTPX timeout/401/503/body/invalid-schema tests. Live outage injection was not needed to validate deterministic transport error handling. |
| 7. Replace/remove without stale or partial publication | verified | Browser replacement/failed-replacement screenshots and smoke log; worker lease/reclaim/atomic rollback/obsolete-sequence tests; deletion purges raw files, chunks and associated traces. |
| 8. Meaningful tests and frozen benchmark denominators | verified | 42 passing tests with local PostgreSQL configured (after the hosted-runtime change); Ruff/format/mypy; 200-intent dataset, split v2 and `evaluation.md`; CI configuration uses no paid provider. |
| 9. Actual comparisons, failures, latency and limitations | verified | Retrieval dev/test reports, cluster bootstrap; answer report with one unnecessary abstention; saved 3B failures/7B condition omission; `load.json`, `ingestion-profile.json`; `experiment-decisions.md`. |
| 10. Containers with persistence/access controls | verified | Final nonroot Docker image built/started; `evidence/docker-smoke.json` records actual upload/search/evidence, replacement, parser failure, API restart with sample/uploaded content preserved, and deletion/trace purge. PostgreSQL/pgvector isolated-schema integration passed. |

## Additional checks and limits

| Check | Status | Reason/evidence |
|---|---|---|
| Real browser/public and admin integration | verified | `evidence/browser-smoke.json`, screenshots; administrator token kept private. |
| Prompt-injection observation with a real local model | verified | `evidence/injection-smoke.json`; one controlled observation, not proof of immunity. |
| Remote free Render deployment | verified | [Live service](https://yash-doculens-v2.onrender.com); `evidence/hosted/{final-deployment,smoke}.json` and screenshots verify the actual free plan, real GPT-OSS 120B generation, four search methods, citations, missing/conflict statuses, quota/private denial and 390 px layout. Known condition omission remains disclosed; private storage stays in persistent Compose. |
| GitHub Actions on a pushed public repository | verified | Both deterministic and PostgreSQL jobs passed on deployed code commit `5f8c462`: `evidence/github-ci-hosted.json`, [actual run](https://github.com/cyash24f3/doculens-v2/actions/runs/36758789464). Initial execution details remain in `evidence/github-ci.json`. The initial health-command quoting failure and fix are retained in the record. |
| Human-authored fresh holdout/human semantic review | blocked | No independent human reviewer supplied. All source/question/answer review metadata says zero human review; automated same-model judge explicitly identified. |

A controlled no-retrieval generation quality comparison was not performed. The app's empty-evidence short circuit is not a provider baseline.

Reproduce the deterministic demo first, then real retrieval, then optional local generation. The highest-value remaining research work is independent labels and semantic condition review, not a larger infrastructure stack.
