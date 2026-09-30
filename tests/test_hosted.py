import concurrent.futures
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from doculens.api.app import create_app
from doculens.api.quota import PublicAnswerQuota
from doculens.config import Settings
from doculens.errors import DomainError
from doculens.generation.provider import Completion
from doculens.generation.service import Answerer
from doculens.retrieval.onnx import OffsetTokenizer, mean_pool


def test_pooling_excludes_padding_and_normalizes():
    hidden = np.array([[[3, 0], [0, 4], [999, 999]]], dtype=np.float32)
    vector = mean_pool(hidden, np.array([[1, 1, 0]]))
    np.testing.assert_allclose(vector, [[0.6, 0.8]], atol=1e-6)
    assert (
        Settings(_env_file=None, model_backend="onnx").embedding_fingerprint
        != Settings(_env_file=None).embedding_fingerprint
    )


def test_offsets_preserve_unicode_and_disable_truncation(tmp_path):
    from tokenizers import Tokenizer, models, pre_tokenizers

    raw = Tokenizer(models.WordLevel({"[UNK]": 0, "café": 1, "paid": 2}, unk_token="[UNK]"))
    raw.pre_tokenizer = pre_tokenizers.Whitespace()
    raw.enable_truncation(max_length=1)
    path = tmp_path / "tokenizer.json"
    raw.save(str(path))
    tokenizer = OffsetTokenizer(str(path))
    assert tokenizer("café paid", add_special_tokens=False)["offset_mapping"] == [(0, 4), (5, 9)]


def test_quota_is_atomic_persists_and_resets_at_utc_day(tmp_path):
    quota = PublicAnswerQuota(tmp_path / "quota.sqlite", 65, 2)

    def reserve():
        try:
            quota.consume(1000)
            return "allowed"
        except DomainError as exc:
            return exc.status

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: reserve(), range(4)))
    assert results.count("allowed") == 1 and results.count(429) == 3
    new_instance = PublicAnswerQuota(quota.path, 65, 2)
    with pytest.raises(DomainError):
        new_instance.consume(1001)
    new_instance.consume(1066)
    with pytest.raises(DomainError):
        new_instance.consume(1200)
    new_instance.consume(86401)


def test_public_provider_is_opt_in_sample_only_and_never_exposes_key(system, ingest):
    settings, repo, models, _, _ = system
    ingest("Products may be returned within 30 days.")
    settings = settings.model_copy(
        update={
            "generation_mode": "provider",
            "provider_model": "test-only",
            "provider_api_key": "test-secret-not-for-client",
            "public_provider_enabled": True,
            "admin_token": "",
        }
    )

    class Stub:
        calls = 0

        def complete(self, messages):
            self.calls += 1
            return Completion(
                json.dumps(
                    {
                        "status": "insufficient_evidence",
                        "claims": [],
                        "missing_information": ["No deadline for this product."],
                    }
                ),
                "test-only",
                None,
                1,
            )

    stub = Stub()
    with TestClient(create_app(settings, repo.db, models, Answerer(settings, stub))) as client:
        assert (
            client.post(
                "/api/v1/answers", json={"question": "Returns", "corpus": "private"}
            ).status_code
            == 403
        )
        first = client.post("/api/v1/answers", json={"question": "Returns"})
        assert first.status_code == 200 and stub.calls == 1
        assert client.post("/api/v1/answers", json={"question": "Returns"}).status_code == 429
        assert client.post("/api/v1/search", json={"question": "Returns"}).status_code == 200
        assert settings.provider_api_key not in client.get("/api/v1/config").text
        assert client.get("/api/v1/developer/metrics").status_code == 403
    settings = settings.model_copy(update={"public_provider_enabled": False})
    with TestClient(create_app(settings, repo.db, models, Answerer(settings, stub))) as client:
        assert client.post("/api/v1/answers", json={"question": "Returns"}).status_code == 403
