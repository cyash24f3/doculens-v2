# DocuLens

[![checks](https://github.com/cyash24f3/doculens-v2/actions/workflows/ci.yaml/badge.svg)](https://github.com/cyash24f3/doculens-v2/actions/workflows/ci.yaml)

An evidence-grounded knowledge copilot for support documentation. Upload PDF, Markdown or text; search with BM25, MiniLM, reciprocal rank fusion or a cross-encoder; generate an answer locally or through a configured hosted model; inspect the exact source/version behind each citation.

Built and verified on a Mac M5 Air with 24 GB RAM and 1 TB storage. Development uses free software, downloaded local models and Docker. Hosted deployment uses Render Free, pinned quantized ONNX retrieval and Groq Free for real answers. No paid plan or paid provider was selected. Local fixture mode remains available for credential-free setup.

![Actual hosted live AI demonstration](docs/evidence/hosted/answer.png)

## Live on the free tier

**[Open DocuLens](https://yash-doculens-v2.onrender.com)** · [Public source](https://github.com/cyash24f3/doculens-v2)

`render.yaml` and `scripts/prepare_render.py` configure genuine MiniLM retrieval plus Groq `openai/gpt-oss-120b` answers on a free Python service. The key is a server-side secret, never a browser credential. Use **Search sources** at any time without an AI call. Public sample answers share a 30-per-UTC-day limit and are at least 65 seconds apart. Local fixtures are not used in the hosted answer path.

The live UI and all four retrieval methods have been checked against the remote service; recorded responses/screenshots include known generation failures and condition omissions. [Hosted evidence](docs/evidence/hosted/).

The free host serves the controlled sample corpus and disables administration/private uploads because its disk is disposable. Full versioned private-workspace operation is available through persistent Compose below. Render sleeps idle services and has a shared monthly workspace allowance; this is a portfolio demo, not a durable always-on production service. See [deployment details](docs/deployment.md).

## Start without credentials

From a checkout, with [uv](https://docs.astral.sh/uv/) installed:

```bash
git clone https://github.com/cyash24f3/doculens-v2.git
cd doculens-v2
uv sync --frozen --python 3.12
uv run doculens demo
```

Open <http://127.0.0.1:8000>. This migrates SQLite and seeds 20 active sample documents from 21 source versions. The interface clearly says **Fixture demonstration**: embeddings/reranking are deterministic test doubles, and three sample answers are scripted. Other questions abstain. This mode proves the application journeys; it makes no semantic model-quality claim and needs no LLM account or model downloads. `uv sync` installs the locked runtime, including Torch; first installation still downloads dependencies.

For real retrieval with the same credential-free scripted answers:

```bash
uv run doculens demo --real-models
```

This uses separate `var/demo-real.db`/file storage, downloads the pinned MiniLM models when needed and runs genuine embeddings/BM25/RRF/reranking. Answers remain visibly scripted.

## Administrator and worker

Generate a local credential once. This command refuses to overwrite an existing `.env`; if you already have one, add `DOCULENS_ADMIN_TOKEN` to it instead.

```bash
uv run python -c 'from pathlib import Path; import secrets; p=Path(".env"); f=p.open("x"); f.write("DOCULENS_ADMIN_TOKEN=" + secrets.token_urlsafe(32) + "\n"); f.close(); p.chmod(0o600)'
```

Restart the web process so it loads the credential. Read your local `.env` and paste its token into **Administrator** in the interface. It is held only in browser memory. Uploads, replacements, deletion, developer comparison and traces require it. Anonymous users can access only the controlled sample corpus; administrator uploads go to the private corpus by default.

Run a matching durable worker in a second terminal:

```bash
uv run doculens worker --demo
# If the web command uses --real-models:
uv run doculens worker --demo --real-models
```

The worker polls database jobs, reports actual extraction/chunking/embedding/activation progress and publishes complete versions atomically. A failed replacement leaves the previous active version searchable. The worker and API must use the same model mode/database.

## Free local generation on the M5

Use [Ollama's official installation](https://docs.ollama.com/quickstart), then run a local model. No subscription or purchased API key is needed. Set `OLLAMA_NO_CLOUD=1` for the server and use this local model tag:

```bash
OLLAMA_NO_CLOUD=1 ollama serve
# Another terminal:
ollama pull qwen2.5:7b-instruct
```

Add the following to your ignored `.env`, retaining the administrator token. `.env.example` documents the full settings contract; do not overwrite your existing token by copying it blindly.

```dotenv
DOCULENS_GENERATION_MODE=provider
DOCULENS_PROVIDER_URL=http://127.0.0.1:11434/v1
DOCULENS_PROVIDER_MODEL=qwen2.5:7b-instruct
DOCULENS_PROVIDER_API_KEY=ollama
DOCULENS_PROVIDER_TIMEOUT=120
DOCULENS_PROVIDER_TOKEN_PARAMETER=max_tokens
DOCULENS_PROVIDER_TEMPERATURE=0
```

Then use the ordinary configured application, which defaults to real retrieval models:

```bash
uv run doculens migrate
uv run doculens seed
uv run doculens serve
# Another terminal:
uv run doculens worker
```

`doculens demo` always overrides generation to fixture; use `serve` for real generation. Local provider generation requires the administrator credential, including for sample questions. The public host explicitly opts into bounded anonymous sample answers. With generation disabled, ingestion/search work and answers report `provider_unavailable`.

The verified Qwen 7B download is about 4.68 GB; Ollama reported about 4.74 GB loaded model memory at 4096 context. Real MiniLM/reranker process RSS was roughly 0.55–0.62 GB in the measured runs. This fits the supplied machine; keep inference concurrency bounded. The smaller 3B model failed the supported/conflicting development scenarios, and those failures are preserved. CPU-compatible retrieval is the default; the Ollama Metal runtime handles local generation.

For this build, the isolated Ollama binary and models are already in ignored `var/tooling/ollama/` and `var/ollama-models/`, with the server on **11435**. Use `DOCULENS_PROVIDER_URL=http://127.0.0.1:11435/v1` to use that server. It is not a paid remote endpoint. A fresh reviewer can follow the official setup above on 11434.

## Persistent PostgreSQL containers

With Docker Desktop running:

```bash
docker compose up --build -d
curl http://127.0.0.1:8001/api/v1/readiness
docker compose ps
```

Open <http://127.0.0.1:8001>. The nonroot API and separate worker use PostgreSQL/pgvector on loopback port 5433 and persistent named volumes. Default Compose uses fixture models/answers and loads `.env` administrator credentials. Migrations and sample seeding run before services start. `docker compose down` retains volumes; `down -v` deletes them. Local Compose was actually built, started and checked. See [deployment](docs/deployment.md) for real-model/local-provider settings, backups, environment variables and the free Render hosting configuration and its limits.

## Reproduce checks and experiments

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/doculens
uv run pytest -q

# Requires the project PostgreSQL container; tests use isolated temporary schemas:
DOCULENS_TEST_POSTGRES_URL=postgresql+psycopg://doculens:local-development-only@127.0.0.1:5433/doculens uv run pytest -q -m postgres

# Fast deterministic integration benchmark; fixture results are labeled:
uv run doculens benchmark --demo --split ci

# Genuine models on the ordinary seeded database:
uv run doculens benchmark --split dev
uv run doculens benchmark --split test

# Actual local generator and automated judge; requires provider settings above:
uv run doculens evaluate-answers --split test --questions 12

# Public deployment checks (three real calls; waits for shared free quota):
uv run python scripts/hosted_smoke.py --url https://yash-doculens-v2.onrender.com

# Running fixture API + matching worker + admin token; private corpus must be empty:
uv run playwright install chromium
uv run python scripts/browser_smoke.py --url http://127.0.0.1:8000

# Running real-retrieval API, with generation disabled:
uv run python scripts/load_test.py --url http://127.0.0.1:8002
uv run python scripts/profile_ingestion.py
```

Experiments save manifests, reports and per-question JSONL under ignored `outputs/<run_id>/`, and register summaries in the database. Configuration, dataset/source/split/lock hashes, model commits, prompt version, corpus snapshot, hardware and available timing/usage are recorded. The published original runs preceded the first repository commit and honestly record `uncommitted-initial-build`; later reproduction runs record their commit. Both GitHub Actions jobs passed on the public repository. A fresh public clone also passed installation, checks, its small benchmark and actual demo startup; see the [acceptance evidence](docs/acceptance.md).

## Measured findings

The 200-intent benchmark has 55 missing-information cases, AI-authored policy questions, a PDF track and independently sourced Python documentation. Frozen split version 2 contains 60 development and 140 final comparison questions. **Labels have no human review, and the final comparison is not a pristine unseen holdout** because some source themes appeared in an earlier exploratory development run. The exposure and decisions are documented.

Results on the 103 answerable final-comparison questions, top five passages:

| Method | Hit@5 | Evidence-group Recall@5 | Full evidence@5 | Warm p95 |
|---|---:|---:|---:|---:|
| BM25 | 91.3% | 90.3% | 89.3% | 0.4 ms |
| MiniLM dense | 96.1% | 91.7% | 90.3% | 8.7 ms |
| RRF hybrid | 92.2% | 90.8% | 90.3% | 4.3 ms |
| Hybrid + cross-encoder | 97.1% | 93.2% | 92.2% | 121.1 ms |

The separate free-host ONNX comparison had hybrid full-evidence@5 of 91.3% and warm p95 22.6 ms on this Mac. Its cross-encoder full-evidence@5 was 93.2%, but warm p95 was 1135 ms, exceeding the original 250 ms target. Hosted default retrieval remains hybrid. These are separate quantized-runtime observations, not remote performance predictions. [ONNX report and provenance](docs/evidence/retrieval-onnx/report.md).

These are retrieval measurements on this dataset, not answer accuracy. All four methods met the documented development-derived full-evidence >=0.85 and warm p95 <=250 ms targets. [Full report, failures and paired uncertainty](docs/evidence/retrieval-test/report.md).

The separate 12-question **actual local Qwen 7B** evaluation had 10 answerable/two missing questions, one unnecessary abstention, zero answered statuses on the two missing cases and zero technical failures. Generation p50/p95 were 20.2/31.5 seconds. The same-model automated judge gave mean correctness 1.83/2; this is exploratory self-judgment with no human calibration. A separate real API smoke returned a valid citation but omitted accessories/proof-of-purchase conditions in its answer, showing why citation validation alone is insufficient. [Answer report](docs/evidence/answer-test/report.md), [observed live API response](docs/evidence/provider-api-smoke.json).

The hosted generator uses Groq GPT-OSS 120B with `grounded-claims-v3`. The 20B development requests exposed omitted conditions, an invalid conflict output and a conflict misclassified as answered; these failures are preserved. Hosted prompt/model selection uses the documented demo/development questions, and the earlier Qwen answer evaluation remains a distinct model/prompt result. No new independent answer-quality score or human review is claimed.

The modest retrieval-only load test used 100 warm requests, concurrency two and one repeated question: no HTTP failures, p50 about 60 ms and p95 about 113 ms. It does not predict production capacity. [Raw load evidence](docs/evidence/load.json). Extraction/chunking/embedding/activation timings are separately recorded in [ingestion profiling](docs/evidence/ingestion-profile.json).

## How it works and what to inspect

- [Acceptance checklist](docs/acceptance.md): commands/tests/screenshots supporting each requested outcome.
- [Architecture](docs/architecture.md): snapshot consistency, exact search, fenced jobs and atomic promotion.
- [Learning guide](docs/learning-guide.md): original application logic, library responsibilities, failures and interview explanations.
- [Evaluation methodology](docs/evaluation.md) and [decision log](docs/experiment-decisions.md): denominators, labels, split exposure and frozen parameters.
- [API examples](docs/api-examples.md): current multipart/JSON contracts, access controls and citation inspection.
- [Security and deletion](docs/security.md): private scope, trace retention, injection observations and in-flight policy.
- [5–7 minute demo](docs/demo.md), [milestone record](docs/milestones.md) and [actual screenshots](docs/evidence/screenshots/).

Core limits: text-bearing PDFs only; OCR is reported as required. Exact vector scans materialize the small authorized corpus and are not designed for large collections. Context budgeting uses a named `cl100k_base` estimate rather than the local Qwen tokenizer; actual provider usage is recorded separately. Structural validation checks IDs/quotes/schema, while semantic support and condition completeness remain fallible. One prompt-injection observation is not a security guarantee. Simple admin/sample separation is not enterprise tenancy. Historical versions require explicit administrator access; deletion purges content and associated traces.

Highest-value next improvement: create a fresh independently human-authored/reviewed holdout, calibrate the semantic judge on a stratified sample, then test condition preservation on development questions. OCR, approximate indexing, multi-turn memory and enterprise authentication are outside this core.

Project code and authored fixtures use [MIT](LICENSE). Included Python documentation retains its [PSF license](data/public/PYTHON-LICENSE.txt); model weights are downloaded separately and are not committed. See [third-party notices](THIRD_PARTY_NOTICES.md).

This complete engineering build is published as `doculens-v2`. The [earlier DocuLens implementation](https://github.com/cyash24f3/doculens) and its existing deployment remain separate. Its CLI, database schema and deployment entry point differ; this repository does not claim an automatic upgrade of that database. [Version boundary](docs/version-boundary.md).
