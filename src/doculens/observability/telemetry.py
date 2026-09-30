import json
import logging
import threading
from collections import defaultdict, deque

import numpy as np


class JsonFormatter(logging.Formatter):
    def format(self, record):
        values = {"level": record.levelname, "event": record.getMessage()}
        for key in (
            "request_id",
            "job_id",
            "version_id",
            "status",
            "total_ms",
            "extraction_ms",
            "embedding_ms",
        ):
            if hasattr(record, key):
                values[key] = getattr(record, key)
        return json.dumps(values)


def configure(level):
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger("doculens").handlers = [handler]
    logging.getLogger("doculens").setLevel(level)
    # HTTP access logs can reveal questions in URLs; only application events are retained.


class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.counts = defaultdict(int)
        self.generation_counts = defaultdict(int)
        self.latencies: deque[float] = deque(maxlen=1000)

    def observe(self, status: int, latency: float):
        with self.lock:
            self.counts[str(status)] += 1
            self.latencies.append(latency)

    def observe_generation(self, status: str):
        with self.lock:
            self.generation_counts[status] += 1

    def snapshot(self):
        with self.lock:
            values = list(self.latencies)
            return {
                "http_status_counts": dict(self.counts),
                "generation_status_counts": dict(self.generation_counts),
                "window_requests": len(values),
                "latency_ms_p50": float(np.percentile(values, 50)) if values else None,
                "latency_ms_p95": float(np.percentile(values, 95)) if values else None,
                "scope": "this API process; rolling last 1000 requests",
            }
