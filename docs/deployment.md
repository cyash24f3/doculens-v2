# Free build and deployment

The verified full application runs on the user's M5 Air (24 GB RAM, 1 TB storage): CPU-compatible MiniLM and reranking, SQLite or Docker PostgreSQL/pgvector, and optional local Ollama/Qwen. No paid service, API key purchase, cloud model call, or remote deployment occurred. Local model files are ignored, outside Git. Only Docker resources named `doculens` belong to this project; unrelated running containers are not changed.

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

## Optional free public demonstration: Render

`render.yaml` configures a **free fixture-only public demo**, with no admin token, no paid provider and no separate cloud database. Copy the repository to your own Git remote, create a Render Blueprint from it, review that the plan is `free`, and deploy. The configured command binds 0.0.0.0:10000, builds a deterministic sample SQLite corpus on each restart and checks `/api/v1/readiness`.

This path is chosen because the measured fixture API/worker processes use roughly 100 MB each and do not load Torch models at runtime. Real local MiniLM/reranker process RSS was around 620 MB in the first smoke, and the local quantized Qwen runtime reports about 4.74 GB model memory at 4096 context. They are not recommended for a tiny free web instance. Run real inference on the M5 for the interview/demo and publish the honest experiment reports.

Render's current free-service documentation specifies idle spin-down after 15 minutes, ephemeral local files, monthly limits and no persistent free disk. The public sample is therefore deliberately rebuilt and administration is disabled. Do not use this free deployment for private uploads or durable knowledge-base storage. To keep it free, do not add a payment method or enable paid resources; exhausted limits can suspend the demo. Free Postgres expires after 30 days, so this blueprint does not depend on it. [Official free-service limits](https://render.com/docs/free), [Blueprint reference](https://render.com/docs/blueprint-spec).

Remote Render creation/deployment and its validation API were **not performed** because account access was not supplied. The YAML is an implementation deliverable, not evidence of a successful remote deployment. Local Docker build/start, readiness, database integration and persistence checks are the verified path. Hugging Face Docker Spaces was not chosen: its current documentation requires a paid plan to create compute-backed Spaces even when CPU Basic has no hourly fee. [Official Spaces documentation](https://huggingface.co/docs/hub/spaces-overview).

## Validation after any deployment

Check health/readiness, list the sample documents, ask a scripted demo question, open a citation, verify private/developer routes reject anonymous access, restart once and repeat. For full local operation, also upload a private fixture, wait for ready, replace it, fail a replacement, delete it and verify retrieval/evidence/traces cannot access it. See the acceptance checklist and browser smoke script. Do not claim this host's performance measurements as remote capacity.

## Public source and free CI

The public repository uses standard `ubuntu-latest` GitHub-hosted runners. Standard hosted runners are free for public repositories under the current [official runner policy](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). No larger/paid runner or paid GitHub add-on is configured. CI has read-only repository permissions and requires no model-provider secret. Repository publication and actual CI run status are recorded in the acceptance evidence once completed.
