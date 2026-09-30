from fastapi.testclient import TestClient

from doculens.api.app import create_app


def test_ui_api_upload_search_answer_and_source_inspection(system):
    settings, repo, models, worker, _ = system
    app = create_app(settings, database=repo.db, models=models)
    headers = {"Authorization": f"Bearer {settings.admin_token}"}
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/v1/readiness").json()["status"] == "ready"
        unauthorized = client.post(
            "/api/v1/documents",
            data={"title": "Returns"},
            files={"file": ("p.md", b"policy", "text/markdown")},
        )
        assert unauthorized.status_code == 403
        uploaded = client.post(
            "/api/v1/documents",
            headers=headers,
            data={"title": "Returns policy", "corpus": "sample"},
            files={
                "file": (
                    "../../returns.md",
                    b"# Returns\n\nOpened products may be returned within 30 calendar days of delivery, provided all accessories and proof of purchase are included.",
                    "text/markdown",
                )
            },
        )
        assert uploaded.status_code == 202
        item = uploaded.json()
        worker.run_once()
        assert (
            client.get(f"/api/v1/jobs/{item['job_id']}?corpus=sample", headers=headers).json()[
                "state"
            ]
            == "completed"
        )
        search = client.post("/api/v1/search", json={"question": "Opened products returns"})
        assert (
            search.status_code == 200
            and search.headers["X-Request-ID"] == search.json()["request_id"]
        )
        answer = client.post(
            "/api/v1/answers", json={"question": "Can I return an opened product after 20 days?"}
        )
        assert answer.status_code == 200 and answer.json()["status"] == "answered"
        cid = answer.json()["citations"][0]["id"]
        trace_id = answer.json()["request_id"]
        assert client.get(f"/api/v1/evidence/{cid}").json()["title"] == "Returns policy"
        assert client.get(f"/api/v1/developer/traces/{trace_id}").status_code == 403
        assert (
            client.get(f"/api/v1/developer/traces/{trace_id}", headers=headers).status_code == 200
        )
        assert client.get("/api/v1/documents?corpus=private").status_code == 403
        assert (
            client.post(
                "/api/v1/search", json={"question": "Returns", "corpus": "private"}
            ).status_code
            == 403
        )
        assert client.get(f"/api/v1/evidence/{cid}?history=true").status_code == 403
        assert (
            client.post("/api/v1/search", json={"question": "Returns", "top_k": 100}).status_code
            == 422
        )
        assert client.post("/api/v1/search", json={"question": "   "}).status_code == 422
        assert client.post("/api/v1/search", content=b"x" * 20000).status_code == 413
        assert (
            client.delete(
                f"/api/v1/documents/{item['document_id']}?corpus=sample", headers=headers
            ).status_code
            == 204
        )
        assert client.get(f"/api/v1/evidence/{cid}").status_code == 404
        assert (
            client.get(f"/api/v1/developer/traces/{trace_id}", headers=headers).status_code == 404
        )
        assert (
            client.post("/api/v1/search", json={"question": "Opened products returns"}).json()[
                "results"
            ]
            == []
        )
        assert (
            client.get("/api/v1/developer/metrics", headers=headers).json()["window_requests"] > 0
        )


def test_private_evidence_cannot_be_read_from_sample(system, ingest):
    settings, repo, models, _, _ = system
    private = ingest("Private E17 secret content.", scope="private", title="Secret")
    cid = repo.snapshot("private").evidence[0].id
    with TestClient(create_app(settings, database=repo.db, models=models)) as client:
        assert client.get(f"/api/v1/evidence/{cid}").status_code == 404
        assert client.get(f"/api/v1/documents/{private['document_id']}").status_code == 404
        assert (
            client.post(
                "/api/v1/search",
                json={"question": "Private E17", "document_ids": [private["document_id"]]},
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/v1/developer/experiments", headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 401
        )
