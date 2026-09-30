# Free build and deployment

The verified full application runs on the user's M5 Air (24 GB RAM, 1 TB storage): CPU-compatible MiniLM and reranking, SQLite or Docker PostgreSQL/pgvector, and optional local Ollama/Qwen. Local engineering/evaluation used no paid service or API key purchase. The public v2 service now also uses Render Free and actual Groq Free calls. Local model files are ignored, outside Git. Only Docker resources named `doculens` belong to this project; unrelated running containers are not changed.

## Persistent local Compose

```bash
uv sync --frozen --python 3.12
# Add only an administrator token to .env if you want protected uploads/developer access.
# Generate a token with Python secrets; do not commit it.
docker compose up --build -d
curl http://127.0.0.1:8001/api/v1/readiness
docker compose ps
```

Default Compose uses explicitly labeled fixture models/answers so startup needs no model download. PostgreSQL listens only on 127.0.0.1:5433, API on 127.0.0.1:8001. Migration and sample seed are completed before API/worker start. Named `database`, `files`, `models`, and `results` volumes preserve content. `docker compose down` keeps volumes; `down -v` deletes them and must be a deliberate data-reset operation. No volume-deleting command was used in this build.

For real local models, set `DOCULENS_MODEL_BACKEND=sentence_transformer` and recreate services. Model fingerprints differ from fixtures, so seed creates new derived versions under the real pipeline before activation. The existing active fixture corpus stays available until each replacement is ready. Set local provider URL to `http://host.docker.internal:11434/v1`, generation mode to `provider`, model to `qwen2.5:7b-instruct`, placeholder key to `ollama`, timeout 120, and token parameter `max_tokens`. Start local Ollama with cloud access disabled and pull only the local model. Live generation requires admin access. CPU Torch wheels are locked for Linux, avoiding unused CUDA downloads.

The nonroot image uses Python 3.12.13 and uv 0.12.1; pgvector image is pinned by digest. The server handles SIGTERM gracefully; ingestion publication is fenced even if a worker is killed before completion. The lease expires after 300 seconds, then another worker may reclaim it subject to the three-attempt budget. To inspect state: `docker compose logs worker`, protected `/api/v1/jobs/{id}`. Actual stage timings are stored on completed jobs after migration 0002; earlier jobs have unknown timing `{}`.

Database backup example (contains potentially private data; keep it outside Git):

```bash
docker compose exec -T db pg_dump -U doculens -d doculens > var/doculens-backup.sql
```

Back up the file volume too. Restore database and raw files consistently; partial restores can leave queued jobs without original files. SQLite is supported for the small local corpus but no automatic SQLite-to-PostgreSQL private-content migration is advertised. Re-ingesting files creates new canonical versions; retaining version identities across backends would require an explicit export/import extension.

## Free hosted demonstration: Render + Groq

The native Python service is configured by `render.yaml`. `requirements-render.lock` is exported from the same uv lock with Torch/SentenceTransformers pruned; `pip install --no-deps -e .` installs the application without reintroducing those large libraries. ONNX Runtime loads the upstream pinned `onnx/model_quint8_avx2.onnx` encoder/reranker. Mean pooling, normalization, input bounds and real token offsets remain explicit. Quantized vectors have a distinct fingerprint and require freshly derived versions; original float model benchmark results are not treated as this runtime's results.

Build: `pip install --require-hashes -r requirements-render.lock && pip install --no-deps -e . && python scripts/prepare_render.py`. Start: `python scripts/prepare_render.py --serve`. Python 3.12.13; Singapore; plan `free`; one process; one inference/provider slot; one CPU inference thread. `HF_HOME=.render-cache` retains downloaded pinned weights in the build artifact. The seed is hashed and migrated with the same ingestion pipeline, never replaced by mock search results.

Groq's free `openai/gpt-oss-20b` endpoint uses the existing HTTPX/JSON-schema adapter with low reasoning effort and a 700-token completion bound. The ignored `.env` and Render environment store the key; no key is committed or supplied to the browser. Free account model quotas apply. The public sample provider is explicitly enabled with no admin credential or transport retries, and at most one schema/citation repair. The cloud context/completion budget is 3072 tokens per request, with 700 reserved for output. Two bounded calls fit within the nominal free model token allowance; the named local tokenizer is an estimate and provider limits are authoritative. A repair runs only when its additional feedback fits the estimated context budget. An atomic SQLite budget permits 30 requests per UTC day, at least 65 seconds apart across all visitors. Failed attempts consume a slot. That local budget survives a process restart on the same disk, but resets after disk replacement; the independent provider account quota continues to apply. Search remains available when answers are rate limited. [Groq limits](https://console.groq.com/docs/rate-limits), [structured outputs](https://console.groq.com/docs/structured-outputs).

Render Free has idle spin-down after 15 minutes, ephemeral storage, and 750 shared workspace instance-hours per month. Other existing free services share this allowance. No persistent free disk is available and free Render Postgres expires after 30 days. The public sample is rebuilt during deployment, with private uploads/admin routes disabled. Full persistent PostgreSQL/file workflows are verified in Compose; they are not advertised as durable on this public free service. No payment method or paid resource is needed for this configuration. [Official free-service limits](https://render.com/docs/free).

Remote deployment verification is pending in this revision. The ONNX sample build and an actual free Groq generation request passed locally; service creation/live HTTP/browser evidence will be recorded separately. Hugging Face Docker Spaces was not chosen because its current documentation requires a paid plan to create compute-backed Spaces even when CPU Basic has no hourly fee. [Official Spaces documentation](https://huggingface.co/docs/hub/spaces-overview).

## Validation after any deployment

Check health/readiness, list the sample documents, ask a real hosted question, open a citation, verify private/developer routes reject anonymous access, restart once and repeat. For full local operation, also upload a private fixture, wait for ready, replace it, fail a replacement, delete it and verify retrieval/evidence/traces cannot access it. See the acceptance checklist and browser smoke script. Do not claim this host's performance measurements as remote capacity.

## Public source and free CI

The public repository uses standard `ubuntu-latest` GitHub-hosted runners. Standard hosted runners are free for public repositories under the current [official runner policy](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). No larger/paid runner or paid GitHub add-on is configured. CI has read-only repository permissions and requires no model-provider secret. The code is published at [cyash24f3/doculens-v2](https://github.com/cyash24f3/doculens-v2). Both hosted CI jobs passed; actual run/commit details and fresh public-clone verification are in the acceptance evidence. The earlier repository and its Render deployment remain separate, as described in `version-boundary.md`.
