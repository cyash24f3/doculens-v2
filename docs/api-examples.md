# API examples

The live OpenAPI contract is at `/openapi.json`, interactive docs at `/docs`. All routes use `/api/v1`. Set `BASE_URL` to http://127.0.0.1:8000 for the demo or http://127.0.0.1:8001 for Compose. `ADMIN_TOKEN` is an environment placeholder: use your ignored local credential, never a committed secret. IDs in the examples come from actual previous responses.

```bash
export BASE_URL=http://127.0.0.1:8000
export ADMIN_TOKEN='<your local administrator token>'
curl "$BASE_URL/api/v1/health"
curl "$BASE_URL/api/v1/readiness"
curl "$BASE_URL/api/v1/documents?corpus=sample&limit=50"
```

Admin upload to the private corpus (multipart, not JSON):

```bash
curl -X POST "$BASE_URL/api/v1/documents" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F title='Returns policy' -F corpus=private -F label=v1 \
  -F effective_date=2026-09-01 \
  -F 'tags=policy,returns' \
  -F 'file=@data/sample/returns.md;type=text/markdown'
```

The 202 response contains `document_id`, `version_id`, `job_id` and `duplicate`. Run `uv run doculens worker --demo` for demo storage, or `uv run doculens worker` for configured storage. Inspect actual progress:

```bash
export JOB_ID='<job_id from upload>'
curl "$BASE_URL/api/v1/jobs/$JOB_ID?corpus=private" -H "Authorization: Bearer $ADMIN_TOKEN"
```

Search and generation (anonymous sample or authenticated private):

```bash
curl -X POST "$BASE_URL/api/v1/search" -H 'Content-Type: application/json' \
  -d '{"question":"Which steps address error E17?","method":"bm25","top_k":5,"corpus":"sample"}'
curl -X POST "$BASE_URL/api/v1/answers" -H 'Content-Type: application/json' \
  -d '{"question":"Can I return an opened product after 20 days?","method":"hybrid","corpus":"sample"}'
curl -X POST "$BASE_URL/api/v1/answers" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"question":"Which return conditions apply?","method":"hybrid","corpus":"private"}'
```

Live provider mode requires admin credentials even for sample generation. Fixture responses explicitly include `generation_mode=fixture` and `model=scripted-demo-fixture-v1`. Disabled generation returns `provider_unavailable` while search remains available. Answer statuses also include answered, insufficient_evidence, conflicting_evidence and invalid_generated_output. Responses include request/corpus IDs, method, source versions, citations, actual available timings and nullable usage.

```bash
export CHUNK_ID='<id from a result or citation>'
export REQUEST_ID='<request_id from search or answer>'
curl "$BASE_URL/api/v1/evidence/$CHUNK_ID?corpus=sample"
curl "$BASE_URL/api/v1/developer/traces/$REQUEST_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -X POST "$BASE_URL/api/v1/developer/compare" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"question":"Which steps address error E17?","corpus":"sample","top_k":5}'
curl "$BASE_URL/api/v1/developer/experiments" -H "Authorization: Bearer $ADMIN_TOKEN"
curl "$BASE_URL/api/v1/developer/metrics" -H "Authorization: Bearer $ADMIN_TOKEN"
```

Developer comparison captures one snapshot for all four methods. Evidence includes surrounding text, source kind, actual PDF pages or null for text, and offsets explicitly labeled stored extracted text. Historical evidence needs `history=true` and an admin credential. It remains inaccessible after deletion.

Replacement and removal:

```bash
export DOCUMENT_ID='<existing document_id>'
curl -X POST "$BASE_URL/api/v1/documents" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F title='Returns policy' -F corpus=private -F label=v2 \
  -F "document_id=$DOCUMENT_ID" -F 'file=@data/sample/returns.md;type=text/markdown'
curl "$BASE_URL/api/v1/documents/$DOCUMENT_ID/versions?corpus=private" -H "Authorization: Bearer $ADMIN_TOKEN"
# Only retry a failed job when attempts remain:
curl -X POST "$BASE_URL/api/v1/jobs/$JOB_ID/retry?corpus=private" -H "Authorization: Bearer $ADMIN_TOKEN"
# This deletes all source content and associated traces for that logical document:
curl -X DELETE "$BASE_URL/api/v1/documents/$DOCUMENT_ID?corpus=private" -H "Authorization: Bearer $ADMIN_TOKEN"
```

The same bytes/pipeline yield a duplicate instead of a second active copy. A replacement with identical current bytes may therefore return the existing version. A replacement with a changed effective date or source locator creates a new immutable, auditable version even for identical file bytes; omitted effective date/source locator inherit the active version during replacement, and metadata patching is not implemented. Title/tags/type belong to the original logical document and replacement uploads do not mutate them.

Malformed inputs return 422; unavailable scopes 403/404; overlong bodies/uploads 413; a changed/deleted snapshot before final publication 409. Errors contain safe codes/messages and request IDs; default logs exclude private question/document content. Public body-size rejections occur before route processing and may not include a normal query trace.
