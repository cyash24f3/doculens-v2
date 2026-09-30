import json
import threading
import time
from dataclasses import dataclass

import httpx

from doculens.errors import DomainError
from doculens.generation.contracts import Proposal


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: dict | None
    attempts: int


class CompatibleProvider:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=settings.provider_timeout, transport=transport, follow_redirects=False
        )
        self.slots = threading.BoundedSemaphore(settings.provider_concurrency)

    def close(self):
        self.client.close()

    def complete(self, messages: list[dict], schema: dict | None = None) -> Completion:
        settings = self.settings
        payload = {
            "model": settings.provider_model,
            "messages": messages,
            settings.provider_token_parameter: settings.answer_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "grounded_answer",
                    "strict": True,
                    "schema": schema or Proposal.model_json_schema(),
                },
            },
        }
        if settings.provider_temperature is not None:
            payload["temperature"] = settings.provider_temperature
        if settings.provider_reasoning_effort is not None:
            payload["reasoning_effort"] = settings.provider_reasoning_effort
        with self.slots:
            for attempt in range(settings.provider_retries + 1):
                try:
                    with self.client.stream(
                        "POST",
                        settings.provider_url.rstrip("/") + "/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {settings.provider_api_key}"},
                    ) as response:
                        if response.status_code == 429 or response.status_code >= 500:
                            if attempt < settings.provider_retries:
                                time.sleep(min(0.25 * (2**attempt), 1))
                                continue
                            raise DomainError(
                                "provider_unavailable",
                                "The generation provider is temporarily unavailable",
                                503,
                            )
                        if response.status_code != 200:
                            raise DomainError(
                                "provider_unavailable",
                                "Provider rejected the configured request",
                                503,
                            )
                        body = bytearray()
                        for part in response.iter_bytes():
                            body.extend(part)
                            if len(body) > settings.provider_output_bytes * 3:
                                raise DomainError(
                                    "invalid_generated_output",
                                    "Provider response exceeded the size limit",
                                    502,
                                )
                    data = json.loads(body)
                    content = data["choices"][0]["message"]["content"]
                    if (
                        not isinstance(content, str)
                        or len(content.encode()) > settings.provider_output_bytes
                    ):
                        raise DomainError(
                            "invalid_generated_output",
                            "Provider returned missing or oversized content",
                            502,
                        )
                    model = data.get("model", settings.provider_model)
                    if not isinstance(model, str) or len(model) > 200:
                        raise DomainError(
                            "invalid_generated_output",
                            "Provider returned invalid model metadata",
                            502,
                        )
                    usage = data.get("usage")
                    return Completion(
                        content,
                        model,
                        usage if isinstance(usage, dict) else None,
                        attempt + 1,
                    )
                except httpx.RequestError as e:
                    if attempt == settings.provider_retries:
                        raise DomainError(
                            "provider_unavailable",
                            "Provider request timed out or could not connect",
                            503,
                        ) from e
                    time.sleep(min(0.25 * (2**attempt), 1))
                except (ValueError, KeyError, IndexError, TypeError) as e:
                    raise DomainError(
                        "invalid_generated_output",
                        "Provider returned an invalid response envelope",
                        502,
                    ) from e
        raise DomainError("provider_unavailable", "Provider retry budget exhausted", 503)
