"""Exercise only the local DocuLens Compose app; leaves existing content intact."""

import json
import subprocess
import time
from pathlib import Path

import httpx

from doculens.config import Settings


def main():
    credential = Settings().admin_token
    if not credential:
        raise SystemExit("Set a local administrator token before this lifecycle check")
    report = {"url": "http://127.0.0.1:8001", "checks": [], "jobs": []}
    client = httpx.Client(base_url=report["url"], timeout=10)
    headers = {"Authorization": f"Bearer {credential}"}
    doc_id = None

    def ready():
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                response = client.get("/api/v1/readiness")
                if response.status_code == 200:
                    return response.json()
            except httpx.RequestError:
                pass
            time.sleep(1)
        raise TimeoutError("Compose API did not become ready")

    def job(job_id):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = client.get(
                f"/api/v1/jobs/{job_id}", params={"corpus": "private"}, headers=headers
            )
            response.raise_for_status()
            item = response.json()
            if item["state"] in {"completed", "failed"}:
                report["jobs"].append(item)
                return item
            time.sleep(0.5)
        raise TimeoutError("Worker did not finish its job")

    def upload(raw, filename, label, replacement=None):
        nonlocal doc_id
        fields = {"title": "Container smoke policy", "label": label, "corpus": "private"}
        if replacement:
            fields["document_id"] = replacement
        response = client.post(
            "/api/v1/documents",
            data=fields,
            files={"file": (filename, raw, "application/octet-stream")},
            headers=headers,
        )
        assert response.status_code == 202, response.text
        item = response.json()
        if replacement is None:
            doc_id = item["document_id"]
        return item, job(item["job_id"])

    def search():
        response = client.post(
            "/api/v1/search",
            headers=headers,
            json={
                "question": "Container smoke return deadline",
                "corpus": "private",
                "document_ids": [doc_id],
                "method": "hybrid",
                "top_k": 5,
            },
        )
        response.raise_for_status()
        return response.json()

    try:
        report["readiness"] = ready()
        before = client.get("/api/v1/documents", params={"corpus": "sample", "limit": 100})
        before.raise_for_status()
        sample_ids = sorted(d["id"] for d in before.json()["documents"])
        assert len(sample_ids) == 20
        assert client.get("/api/v1/documents", params={"corpus": "private"}).status_code == 403
        assert client.get("/api/v1/developer/metrics").status_code == 403
        report["checks"].append("anonymous private/developer access denied")
        first, first_job = upload(
            b"# Returns\n\nContainer smoke returns accepted within 30 calendar days.", "x.md", "v1"
        )
        doc_id = first["document_id"]
        assert first_job["state"] == "completed"
        result = search()
        assert "30 calendar days" in json.dumps(result["results"])
        first_chunk = result["results"][0]["id"]
        evidence = client.get(
            f"/api/v1/evidence/{first_chunk}", params={"corpus": "private"}, headers=headers
        )
        assert evidence.status_code == 200
        report["checks"].append("authenticated upload, worker ready, scoped search and evidence")
        second, second_job = upload(
            b"# Returns\n\nContainer smoke returns accepted within 14 calendar days.",
            "x.md",
            "v2",
            doc_id,
        )
        assert second_job["state"] == "completed"
        result = search()
        assert "14 calendar days" in json.dumps(result["results"])
        assert "30 calendar days" not in json.dumps(result["results"])
        versions = client.get(
            f"/api/v1/documents/{doc_id}/versions", params={"corpus": "private"}, headers=headers
        )
        versions.raise_for_status()
        assert len(versions.json()["versions"]) == 2
        report["checks"].append("replacement activates atomically and history retained")
        _, failed = upload(b"%PDF-1.7\nbroken", "bad.pdf", "v3", doc_id)
        assert failed["state"] == "failed"
        assert "14 calendar days" in json.dumps(search()["results"])
        report["checks"].append("corrupt replacement fails while previous active remains")
        # Restart just this project's API; named DB/file volumes and worker remain.
        subprocess.run(["docker", "compose", "restart", "api"], check=True)
        ready()
        after = client.get("/api/v1/documents", params={"corpus": "sample", "limit": 100})
        after.raise_for_status()
        assert sorted(d["id"] for d in after.json()["documents"]) == sample_ids
        assert "14 calendar days" in json.dumps(search()["results"])
        report["sample_document_ids_survived_api_restart"] = sample_ids
        report["active_private_version_after_restart"] = second["version_id"]
        report["checks"].append("sample IDs and uploaded active content survive API restart")
        final_result = search()
        final_chunk = final_result["results"][0]["id"]
        trace = final_result["request_id"]
        removed = client.delete(
            f"/api/v1/documents/{doc_id}", params={"corpus": "private"}, headers=headers
        )
        removed.raise_for_status()
        assert (
            client.get(
                f"/api/v1/evidence/{final_chunk}", params={"corpus": "private"}, headers=headers
            ).status_code
            == 404
        )
        assert client.get(f"/api/v1/developer/traces/{trace}", headers=headers).status_code == 404
        doc_id = None
        report["checks"].append("deletion removes evidence and relevant traces")
        report["containers"] = [
            json.loads(line)
            for line in subprocess.check_output(["docker", "compose", "ps", "--format", "json"])
            .decode()
            .splitlines()
        ]
        Path("docs/evidence/docker-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
        print("Compose lifecycle and restart persistence checks passed")
    finally:
        if doc_id:
            client.delete(
                f"/api/v1/documents/{doc_id}", params={"corpus": "private"}, headers=headers
            )
        client.close()


if __name__ == "__main__":
    main()
