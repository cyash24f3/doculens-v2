"""Reproducible, real-browser UI checks and screenshots; server must be running."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    out = Path("docs/evidence/screenshots")
    out.mkdir(parents=True, exist_ok=True)
    checks = [
        "supported fixture answer",
        "source inspection",
        "missing fixture answer",
        "conflict fixture answer",
        "documents real API",
        "developer access protected",
        "390px mobile no overflow",
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
        failures = []
        page.on("pageerror", lambda e: failures.append(str(e)))
        page.goto(args.url)
        expect(page.locator("#mode-pill")).to_have_text("Fixture demonstration")
        page.screenshot(path=str(out / "ask.png"), full_page=True)
        page.get_by_role("button", name="Opened product returns").click()
        expect(page.locator("#answer-region")).to_contain_text("ANSWERED")
        expect(page.locator("#answer-region")).to_contain_text("proof of purchase")
        page.screenshot(path=str(out / "answer.png"), full_page=True)
        page.locator("#answer-region .citation-button").first.click()
        expect(page.locator("#source-dialog")).to_be_visible()
        expect(page.locator("#source-passage")).to_contain_text("30 calendar days")
        page.screenshot(path=str(out / "source.png"))
        page.locator('[data-close="source-dialog"]').click()
        page.get_by_role("button", name="Delivery guarantees").click()
        expect(page.locator("#answer-region")).to_contain_text("INSUFFICIENT EVIDENCE")
        page.screenshot(path=str(out / "missing.png"), full_page=True)
        page.get_by_role("button", name="Conflicting policies").click()
        expect(page.locator("#answer-region")).to_contain_text("CONFLICTING EVIDENCE")
        page.screenshot(path=str(out / "conflict.png"), full_page=True)
        page.locator('[data-view="documents"]').click()
        expect(page.locator(".document-card")).not_to_have_count(0)
        page.screenshot(path=str(out / "documents.png"), full_page=True)
        page.locator('[data-view="developer"]').click()
        expect(page.locator("#developer-lock")).to_be_visible()
        from doculens.config import Settings

        credential = Settings().admin_token
        if credential:
            page.locator("#admin-open").click()
            page.locator("#admin-token").fill(credential)
            page.locator("#admin-form .primary").click()
            expect(page.locator("#admin-open")).to_have_text("Administrator connected")
            page.locator('[data-view="developer"]').click()
            page.locator("#compare-question").fill("Which steps address Beacon error E17?")
            page.locator("#compare-form button").click()
            expect(page.locator(".comparison-card")).to_have_count(4)
            expect(page.locator("#toast")).to_be_hidden(timeout=10000)
            page.screenshot(path=str(out / "developer.png"), full_page=True)
            page.locator('[data-view="ask"]').click()
            page.locator("#corpus").select_option("private")
            page.locator('[data-view="documents"]').click()
            expect(page.locator("#documents-list")).to_contain_text("No documents yet")
            source = Path("var/browser-source.md")
            source.write_text(
                "# Returns\n\nOpened products may be returned within 30 calendar days of delivery, provided all accessories and proof of purchase are included."
            )
            page.locator("#upload-open").click()
            page.locator("#upload-title").fill("Returns policy")
            page.locator("#upload-file").set_input_files(source)
            page.locator("#upload-form .primary").click()
            expect(page.locator(".document-card")).to_contain_text("Active · v1", timeout=15000)
            page.locator('[data-view="ask"]').click()
            page.locator("#question").fill("Can I return an opened product after 20 days?")
            page.locator("#ask-button").click()
            expect(page.locator("#answer-region")).to_contain_text("ANSWERED")
            page.locator('[data-view="documents"]').click()
            source.write_text(
                "# Returns\n\nOpened products may be returned within 14 calendar days of delivery, provided all accessories and proof of purchase are included."
            )
            page.get_by_role("button", name="Replace version").click()
            page.locator("#upload-file").set_input_files(source)
            page.locator("#upload-form .primary").click()
            expect(page.locator(".document-card")).to_contain_text("Active · v2", timeout=15000)
            page.get_by_role("button", name="Version history").click()
            expect(page.locator(".version-history")).to_contain_text("v1 · ready")
            page.screenshot(path=str(out / "replacement.png"), full_page=True)
            bad = Path("var/browser-corrupt.pdf")
            bad.write_bytes(b"%PDF-1.7\nbroken")
            page.get_by_role("button", name="Replace version").click()
            page.locator("#upload-file").set_input_files(bad)
            page.locator("#upload-form .primary").click()
            expect(page.locator(".document-card")).to_contain_text("v3 · failed", timeout=15000)
            expect(page.locator(".document-card")).to_contain_text("Active · v2")
            page.screenshot(path=str(out / "failed-replacement.png"), full_page=True)
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Remove", exact=True).click()
            expect(page.locator("#documents-list")).to_contain_text("No documents yet")
            page.locator('[data-view="ask"]').click()
            page.locator("#corpus").select_option("sample")
            checks.extend(
                [
                    "administrator upload-to-ready",
                    "replacement history",
                    "failed replacement retains active version",
                    "document removal",
                    "same-snapshot retrieval comparison",
                ]
            )
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator('[data-view="ask"]').click()
        expect(page.locator("#toast")).to_be_hidden(timeout=10000)
        page.screenshot(path=str(out / "mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
            "Mobile layout overflows"
        )
        assert not failures, failures
        (out.parent / "browser-smoke.json").write_text(
            json.dumps(
                {
                    "url": args.url,
                    "checks": checks,
                    "admin_journeys": "verified" if credential else "skipped: no admin credential",
                    "javascript_errors": failures,
                    "screenshots": [str(p) for p in sorted(out.glob("*.png"))],
                },
                indent=2,
            )
            + "\n"
        )
        browser.close()
        print("Browser checks passed; screenshots:", out)


if __name__ == "__main__":
    main()
