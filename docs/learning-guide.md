# Learn, debug and explain DocuLens

Start with `config.py`, then follow one document through `Repository.upload`, `Worker.process`, `chunk`, `Retriever.search`, `assemble`, `Answerer.answer`, and `validate_citations`. FastAPI is the boundary around these modules; business logic can run without HTTP or a paid key. Ordinary tests instantiate these modules directly.

## Parsing, chunks, embeddings and answers are different operations

Parsing turns a PDF/text file into readable stored text. It cannot infer words from an image-only page: `ocr_required` is a genuine failure, not success with zero chunks. PDF page references come from actual page-by-page extraction. Text offsets point into the stored string, never into PDF coordinates. Inspect `beacon-quickstart.pdf` and `test_pdf_pages_and_text_offsets`.

Chunking divides that string into passages with stable identities and boundaries. The source keeps capitalization, ₹ amounts, percentages, dates and Unicode. The chunker uses real model-tokenizer offsets; small Markdown sections remain whole, large sections become overlapping windows. Default chunks are 180 word pieces, overlap 32. The actual loaded MiniLM limit is 256, so blindly using 500-token chunks would truncate information. A pipeline fingerprint changes when chunk settings/model changes; duplicate bytes under a different pipeline need a distinct build.

Embedding produces a normalized 384-dimensional vector for each passage. The model is library functionality: the application does not train MiniLM. `embedding_fingerprint` prevents comparing vectors from different models or preprocessing. The fixture backend hashes tokens; it only tests deterministic wiring and is not a substitute for semantic embedding quality.

Generation reads selected passages and proposes statements. It is a separate configurable provider call. Documents do not become part of model weights. Updating a cancellation policy requires reindexing/version replacement, not fine-tuning.

## Why lexical search can win

BM25 uses exact token occurrences, document frequency and length normalization. Error E17, webhook W409, Beacon B200, and payment P402 are identifiers where a paraphrase model may miss a crucial character. This implementation case-folds only the search tokens and preserves IDs; citation text remains exact. No question-specific keyword rule chooses gold passages. BM25 uses `rank_bm25` rather than calling PostgreSQL `ts_rank` BM25.

Dense search can recognize related wording even without an exact match. It scans normalized vectors exactly, without ANN recall loss. Cosine similarity is a ranking measure, not a calibrated probability. Compare a public documentation question and an E17 question in Developer; the complex method is not guaranteed to win.

## RRF and cross-encoders

For rank 1, a retriever contributes `1/(60+1)` with the default weight. If a chunk is rank 2 in BM25 and rank 1 in dense search, its fused score is `1/62 + 1/61`. An absent chunk contributes zero. RRF combines ranks because BM25 and cosine raw scores have unrelated scales. Stable chunk IDs deduplicate candidates, and IDs break ties.

A cross-encoder reads the question and passage together. It rescores the top 20 fused candidates; it does not search omitted content. First-stage pools are saved so a missing-candidate failure is distinguishable from poor reranking. In the actual final benchmark, reranking reached 0.9223 full-evidence@5 versus hybrid 0.9029, at much higher warm latency. This is an experimental tradeoff, not universal superiority.

## Context can lose evidence after good retrieval

The first implementation chose one passage from each document before additional passages. In the fixture integration test, `Returns policy / Authorization` ranked first, and `Opened goods` ranked second. The diversity pass selected other documents and excluded the necessary second passage. A user received missing evidence despite successful first-stage retrieval. The fix preserves rank while allowing at most two passages per document. Tests check budget, overlap and diversity. The cap can still fail on questions requiring three sections from one document; that is a useful next development experiment.

The generation budget counts instructions, schema, question and evidence with a named tokenizer and reserves answer space. Candidates excluded by token/chunk/diversity/overlap limits are recorded. Whole passages are preferred. The tokenizer estimate is approximate for Qwen; provider token usage is the actual observation.

## Citations do not prove a claim

A model can cite a real paragraph and still misstate it. Validation catches invented IDs, references outside context, quotes changing 30 to 300, and missing per-claim citations. Whitespace is the only quote normalization. The initial local 3B model cited real text while repeating questions and unnecessarily abstaining. The 7B model answered the return question but omitted accessory/receipt conditions. Both cases explain why semantic correctness and condition preservation need a separate rubric.

Structured output is useful for enforceable contracts, but it can still be wrong. Invalid output after a bounded repair is `invalid_generated_output`; a timeout is `provider_unavailable`; lack of source information is `insufficient_evidence`. These states should not be merged into an empty answer.

## Version changes, snapshots and retries

A logical document owns an active-version pointer. New uploads have higher sequences. A successful new build makes the new pointer active; failed replacements leave the old pointer unchanged. Inspect the cancellation prior/current files and the replacement tests. Search snapshots capture exactly the ready active versions and all text/vectors before leaving the database transaction. A mid-query update cannot combine cached BM25 from one manifest with dense vectors from another.

A job lives in the database, not an unreliable background callback. Its lease token changes when a crashed job is reclaimed. Progress updates and final publication are conditional on current ownership and expiry. The old worker can finish expensive computation but cannot commit. Publication inserts all chunks and promotes the version atomically; a bad embedding length rolls back everything. Newer sequences fence obsolete promotion. Run the stale-worker and rollback tests to observe this behavior.

## Evaluation: inspect denominators and failures

Hit@5 counts questions with any relevant passage. Evidence-group recall counts required facts, and full coverage requires all facts. One return passage may hit a question requiring both refund timing and postage but cover only one group. Overlapping duplicate chunks do not count as independent evidence. Missing questions have no relevant gold; they need answer abstention evaluation, not passage-recall labels.

The 200 question intents are AI-authored, with shared themes and no human verification. Python documentation adds an independent source track, but its question labels remain AI-authored. The split groups related questions together. Bootstrap intervals resample source/theme groups; this conservative choice acknowledges correlation. Read failures in each report before quoting aggregate metrics. Do not tune on the final test set, and do not describe machine judgments as human labels.

## Hardware and the free workflow

The user device is an M5 Air with 24 GB RAM and 1 TB storage. Embeddings/reranking run with CPU-compatible Torch; Ollama can use Apple Silicon acceleration for a local quantized Qwen model. The build measured encoder+reranker process RSS around 620 MB in the first smoke check, and reports record later process measurements. API and worker each add memory. Qwen model download size is not the same as runtime memory; `/api/ps` and process measurements provide observations.

Latency includes queueing, database work, context, generation, retries and validation. A synchronous function in a thread pool prevents event-loop blocking but does not magically multiply CPU capacity. The measured loopback load result applies to this corpus/hardware, not a small remote free host. Local models have no provider fee; use a separate budget and dated price file if you ever choose a paid provider.

## Original application code and libraries

| Responsibility | Original application work | Library/runtime |
|---|---|---|
| Lifecycle | logical versions, promotion fencing, deletion, traces | SQLAlchemy, Alembic, PostgreSQL/SQLite |
| Parsing/chunking | limits, offsets, section windows, provenance | pypdf, model tokenizer |
| Retrieval | authorized snapshot, cache keys, deterministic fusion/pools | rank_bm25, NumPy, Sentence Transformers |
| Generation | context, typed claims, quote checks, statuses/retries | HTTPX, Pydantic, local Ollama/Qwen |
| Evaluation | spans/groups, split protection, uncertainty, per-question reports | NumPy, local automated judge |
| Interface | four real-data views and source inspection | FastAPI/Jinja2, plain JavaScript |

Debug one failing question with its JSONL row, resolved source spans, first-stage candidates, final context IDs and answer trace. Change one development parameter at a time and record why. Keep the fixture demonstration for wiring, and the real-model benchmark for retrieval claims.
