# Six-minute demonstration

Use the running sample at http://127.0.0.1:8000, or start `uv run doculens demo` and `uv run doculens worker --demo` in separate terminals. Set the local administrator token as described in the README. Keep the private corpus empty for the scripted sequence; do not remove someone else's documents. Everything below was exercised by the real browser smoke script, whose screenshots are in `evidence/screenshots/`.

**0:00–0:40 — Set expectations.** Show the Fixture demonstration badge and 20 sample documents. Explain that the interface/API/storage run normally while this credential-free path uses named model test doubles and three scripted answers. The real-model benchmark and actual free Ollama evaluation are separate saved evidence. Point out that the independently sourced Python documentation complements fictional support policies.

**0:40–1:30 — Supported answer and evidence.** Click Opened product returns. The answer allows 20-day returns within 30 calendar days only with all accessories and proof of purchase. Open a citation: show the exact paragraph, immutable version/effective date, section, hash and extracted-text offsets. Explain that the application constructs citations from permitted passages, and checks quoted spans without normalizing numbers away. Screenshot: `evidence/screenshots/source.png`. A structurally valid citation still does not prove the model preserved every condition: the saved live-provider smoke omitted accessories/proof of purchase, an actual known failure.

**1:30–2:10 — Missing and conflicting evidence.** Click Delivery guarantees: no Antarctic guarantee is documented, so the response identifies missing evidence. Click Conflicting policies: two active Harbor documents disagree about warranty length, and both citations remain inspectable. Distinguish these from a technical provider failure; `tests/test_generation.py` verifies timeout, malformed output and unavailable-provider paths. The saved local 7B development smoke exercised all three public answer statuses with actual generation.

**2:10–3:00 — Controlled retrieval comparison.** Connect Administrator, open Developer and compare “Which steps address Beacon error E17?” All four methods use one captured snapshot. Point to individual ranks and scores, then open the recorded report: full-evidence@5 was 89.3% BM25, 90.3% dense/hybrid and 92.2% reranked on 103 answerable comparison questions. Reranked warm p95 was 121.1 ms versus hybrid 4.3 ms. The labels are AI-authored, the final partition has known prior theme exposure, and these numbers measure retrieval rather than answer correctness. Screenshots/report are actual executions, not UI analytics.

**3:00–4:15 — Replacement and history.** Select Private on Ask, then Documents. Upload a small Markdown file titled Returns policy containing:

```markdown
# Returns

Opened products may be returned within 30 calendar days of delivery, provided all accessories and proof of purchase are included.
```

Watch real job progress become Active · v1. Search/ask the opened-return sample question. Replace the file with the same paragraph changed to **14 calendar days**, label v2. Wait for ready, then expand Version history. Ordinary search now uses v2; v1 remains explicit administrator-only history. Use Developer search to inspect the 14-day evidence. Do not expect arbitrary replacement text to produce a new scripted answer; use the configured local provider for live generation.

**4:15–5:10 — Reliability failure and removal.** Upload a malformed replacement PDF starting `%PDF-1.7` followed by invalid data, as produced by `scripts/browser_smoke.py`. Show v3 · failed and its safe parser error while Active · v2 remains. Explain database-backed claims, bounded attempts, fenced leases and the single activation transaction. Remove this demo document; the private list becomes empty and new search/evidence/traces cannot retrieve its content. Screenshot: `evidence/screenshots/failed-replacement.png`.

**5:10–6:00 — Reproducibility and honest next work.** Show the acceptance checklist, meaningful test results, Compose health and frozen benchmark manifest. The real local Qwen evaluation used 12 stratified questions with one unnecessary abstention and generation p50/p95 20.2/31.5 seconds. Its automated judge is the same model; there is no human calibration. The next improvement is an independently human-authored/reviewed holdout and condition-preservation review. Do not present machine judgment as human accuracy or localhost performance as free-host capacity.

Optional actual-provider demonstration: start the configured `doculens serve --port 8003` with local Ollama, real retrieval and the admin token, then ask a supported question. Allow 30–60 seconds for a cold response. The live badge and model identify real generation; inspect its citation and any omitted conditions. Keep this optional segment outside the six-minute fixture script if latency would obscure the lifecycle demonstration.

## Defensible portfolio bullets

- Built a FastAPI knowledge copilot with immutable document versions, durable fenced ingestion jobs, atomic activation, scoped retrieval and validated source citations; tested SQLite and PostgreSQL/pgvector paths.
- Compared BM25, exact MiniLM, RRF and cross-encoder reranking on an inspectable 200-intent AI-authored benchmark; reported full-evidence coverage, paired uncertainty, latency and split limitations rather than claiming universal accuracy.
- Verified real local Qwen generation, failure handling and 12 exploratory answer evaluations without paid provider calls; documented condition omissions and the need for human semantic calibration.

These describe verified work. Do not change them into “production deployed,” “97% answer accuracy,” “human-verified benchmark,” or claimed business savings.
