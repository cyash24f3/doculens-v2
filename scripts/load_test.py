"""Bounded retrieval-only HTTP load. No generation or paid-provider calls."""

import argparse
import json
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument(
        "--method", default="hybrid", choices=["bm25", "dense", "hybrid", "reranked"]
    )
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/load.json"))
    args = parser.parse_args()
    assert 1 <= args.requests <= 500 and 1 <= args.concurrency <= 4
    with httpx.Client(base_url=args.url, timeout=120) as client:
        ready = client.get("/api/v1/readiness").json()
        config = client.get("/api/v1/config").json()
        payload = {
            "question": "Which troubleshooting steps apply to error E17?",
            "method": args.method,
            "top_k": 5,
        }
        assert client.post("/api/v1/search", json=payload).status_code == 200

        def request(_):
            start = time.perf_counter()
            response = client.post("/api/v1/search", json=payload)
            elapsed = (time.perf_counter() - start) * 1000
            return {
                "status": response.status_code,
                "total_ms": elapsed,
                "timings": response.json().get("timings"),
                "results": len(response.json().get("results", [])),
            }

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            results = list(pool.map(request, range(args.requests)))
    report = {
        "kind": "retrieval-only HTTP load",
        "requests": args.requests,
        "concurrency": args.concurrency,
        "method": args.method,
        "elapsed_seconds": time.perf_counter() - started,
        "failures": sum(r["status"] != 200 for r in results),
        "p50_ms": float(np.percentile([r["total_ms"] for r in results], 50)),
        "p95_ms": float(np.percentile([r["total_ms"] for r in results], 95)),
        "hardware": platform.platform(),
        "model_config": config,
        "readiness": ready,
        "conditions": "warm local loopback HTTP; single repeated question; no generation; not production capacity",
        "provider_usage": None,
        "provider_cost": None,
        "per_request": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"per_request", "model_config", "readiness"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
