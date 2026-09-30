"""Verify the public deployed application with real HTTP and browser requests.

Consumes three shared free answer slots, waiting for the disclosed quota interval.
No credentials are read, sent to the browser, printed or included in evidence.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/hosted"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "url": args.url,
        "checked_at": datetime.now(UTC).isoformat(),
        "answers": [],
        "javascript_errors": [],
    }
    with httpx.Client(base_url=args.url, timeout=90) as client:
        for path in ("health", "readiness", "config"):
            response = client.get("/api/v1/" + path)
            response.raise_for_status()
            report[path] = response.json()
        assert report["config"]["model_backend"] == "onnx"
        assert report["config"]["generation_mode"] == "provider"
        assert report["config"]["public_provider_enabled"]
        assert not report["config"]["admin_enabled"]
        documents = client.get("/api/v1/documents").json()["documents"]
        assert len(documents) == 20 and all(item["active"] for item in documents)
        report["active_documents"] = len(documents)
        denials = {}
        for path in ("documents?corpus=private", "developer/metrics", "developer/experiments"):
            denials[path] = client.get("/api/v1/" + path).status_code
        denials["private_answer"] = client.post(
            "/api/v1/answers", json={"question": "Private", "corpus": "private"}
        ).status_code
        denials["upload"] = client.post(
            "/api/v1/documents",
            data={"title": "Unauthorized"},
            files={
                "file": ("unauthorized.txt", b"Public demo must reject this upload.", "text/plain")
            },
        ).status_code
        assert all(status == 403 for status in denials.values()), denials
        report["anonymous_denials"] = denials
        report["retrieval"] = {}
        for method in ("bm25", "dense", "hybrid", "reranked"):
            response = client.post(
                "/api/v1/search",
                json={"question": "Which steps address Beacon error E17?", "method": method},
            )
            response.raise_for_status()
            result = response.json()
            assert result["results"] and all(
                hit["evidence"]["document_id"] in {document["id"] for document in documents}
                for hit in result["results"]
            )
            report["retrieval"][method] = result
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1080})
            page.on("pageerror", lambda error: report["javascript_errors"].append(str(error)))
            page.goto(args.url, wait_until="networkidle", timeout=90000)
            expect(page.locator("#mode-pill")).to_have_text("Live AI configured")
            expect(page.locator("#hosted-notice")).to_be_visible()
            expect(page.locator("#admin-open")).to_be_hidden()
            page.locator("#question").fill("Which steps address Beacon error E17?")
            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/search")
            ) as pending_search:
                page.locator("#search-button").click()
            assert pending_search.value.status == 200
            expect(page.locator("#answer-region")).to_contain_text("Source search")
            page.locator("#answer-region .citation-button").first.click()
            expect(page.locator("#source-passage")).to_contain_text("E17")
            page.locator('[data-close="source-dialog"]').click()
            report["source_search_without_provider"] = True
            page.screenshot(path=str(args.output / "search.png"), full_page=True)
            last_started = 0.0
            for name, button, expected_status in (
                ("answer", "Opened product returns", "answered"),
                ("missing", "Delivery guarantees", "insufficient_evidence"),
                ("conflict", "Conflicting policies", "conflicting_evidence"),
            ):
                while (
                    time.monotonic() - last_started
                    < report["config"]["public_answer_interval_seconds"] + 2
                ):
                    time.sleep(
                        min(
                            30,
                            report["config"]["public_answer_interval_seconds"]
                            + 2
                            - (time.monotonic() - last_started),
                        )
                    )
                last_started = time.monotonic()
                with page.expect_response(
                    lambda response: response.url.endswith("/api/v1/answers"), timeout=90000
                ) as pending:
                    page.get_by_role("button", name=button).click()
                response = pending.value
                assert response.status == 200, response.text()
                answer = response.json()
                report["answers"].append({"case": name, "response": answer})
                # Preserve real partial/failure evidence instead of losing it on assertion.
                report["result"] = "in_progress"
                (args.output / "smoke.json").write_text(json.dumps(report, indent=2) + "\n")
                assert (
                    answer["generation_mode"] == "provider"
                    and answer["model"] == "openai/gpt-oss-20b"
                )
                assert answer["status"] == expected_status, answer
                expect(page.locator("#answer-region")).to_contain_text(
                    expected_status.replace("_", " ").upper()
                )
                page.screenshot(path=str(args.output / f"{name}.png"), full_page=True)
                for citation in answer["citations"]:
                    source = client.get("/api/v1/evidence/" + citation["id"])
                    source.raise_for_status()
                    assert source.json()["version_id"] == citation["version_id"]
                if name == "answer":
                    report["answer_includes_conditions"] = (
                        "accessories" in answer["answer"].lower()
                        and "proof of purchase" in answer["answer"].lower()
                    )
                    page.locator("#answer-region .citation-button").first.click()
                    expect(page.locator("#source-dialog")).to_be_visible()
                    expect(page.locator("#source-passage")).to_contain_text("30 calendar days")
                    page.screenshot(path=str(args.output / "source.png"))
                    page.locator('[data-close="source-dialog"]').click()
                    quota = client.post("/api/v1/answers", json={"question": "Returns"})
                    assert (
                        quota.status_code == 429
                        and quota.json()["error"]["code"] == "public_answer_quota"
                    )
                    report["quota_denial"] = {"http_status": quota.status_code, **quota.json()}
                print(
                    f"Hosted {name}: {answer['status']}, citations={len(answer['citations'])}",
                    flush=True,
                )
            page.locator('[data-view="documents"]').click()
            expect(page.locator(".document-card")).to_have_count(20)
            page.screenshot(path=str(args.output / "documents.png"), full_page=True)
            page.locator('[data-view="ask"]').click()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
            assert not report["javascript_errors"], report["javascript_errors"]
            report["mobile_width"] = 390
            report["mobile_overflow"] = False
            browser.close()
    report["result"] = "passed"
    (args.output / "smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Hosted real HTTP/browser checks passed:", args.output)


if __name__ == "__main__":
    main()
