from types import SimpleNamespace

import httpx2
import openai
import pytest

from llm import ProviderUnavailable
from llm.providers import OpenAICompatibleProvider, build_providers
from llm.tasks.find_replace import SCHEMA as SUGGESTION_SCHEMA

MESSAGES = [{"role": "user", "content": "hi"}]
REQUEST = httpx2.Request("POST", "https://llm.test/v1/chat/completions")


def status_error(error_class, status_code):
    return error_class(f"HTTP {status_code}", response=httpx2.Response(status_code, request=REQUEST), body=None)


def completion(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeClient:
    """Mimics ``openai.OpenAI().chat.completions`` with scripted results."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.requests.append(request)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return completion(result)


def provider(client, **options):
    return OpenAICompatibleProvider(name="test", model="m", base_url="https://llm.test/v1", client=client, **options)


def test_sends_a_json_schema_and_the_reasoning_effort():
    client = FakeClient('{"pattern": "a"}')

    reply = provider(client, json_mode="json_schema", reasoning_effort="low").complete(MESSAGES, SUGGESTION_SCHEMA)

    assert reply == '{"pattern": "a"}'
    request = client.requests[0]
    assert request["response_format"]["json_schema"]["schema"] == SUGGESTION_SCHEMA
    assert request["reasoning_effort"] == "low"


def test_omits_response_format_when_json_mode_is_none():
    client = FakeClient("{}")
    provider(client, json_mode="none").complete(MESSAGES, SUGGESTION_SCHEMA)
    assert "response_format" not in client.requests[0]


def test_retries_without_response_format_when_the_server_rejects_it():
    client = FakeClient(status_error(openai.BadRequestError, 400), '{"pattern": "a"}')

    assert provider(client).complete(MESSAGES, SUGGESTION_SCHEMA) == '{"pattern": "a"}'
    assert "response_format" in client.requests[0]
    assert "response_format" not in client.requests[1]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (status_error(openai.RateLimitError, 429), "rate-limited"),
        (status_error(openai.AuthenticationError, 401), "rejected the API key"),
        (status_error(openai.InternalServerError, 503), "returned HTTP 503"),
        (openai.APITimeoutError(request=REQUEST), "timed out"),
        (openai.APIConnectionError(request=REQUEST), "could not reach"),
    ],
)
def test_turns_sdk_errors_into_provider_unavailable(error, message):
    with pytest.raises(ProviderUnavailable, match=message):
        provider(FakeClient(error), json_mode="none").complete(MESSAGES, SUGGESTION_SCHEMA)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx2.Response(503, json={"error": {"message": "The model is overloaded."}}), "returned HTTP 503"),
        (httpx2.ReadTimeout("no reply"), "timed out"),
    ],
)
def test_makes_a_single_attempt_so_the_next_provider_is_tried_at_once(monkeypatch, failure, message):
    attempts = []

    def server(request):
        attempts.append(request)
        if isinstance(failure, Exception):
            raise failure
        return failure

    # Use the real SDK client, but answer its HTTP requests locally.
    sdk_client = openai.OpenAI
    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **options: sdk_client(**options, http_client=httpx2.Client(transport=httpx2.MockTransport(server))),
    )
    unreliable = OpenAICompatibleProvider(name="test", model="m", base_url="https://llm.test/v1", json_mode="none")

    with pytest.raises(ProviderUnavailable, match=message):
        unreliable.complete(MESSAGES, SUGGESTION_SCHEMA)
    assert len(attempts) == 1


def test_treats_an_empty_reply_as_unavailable():
    with pytest.raises(ProviderUnavailable, match="empty reply"):
        provider(FakeClient(""), json_mode="none").complete(MESSAGES, SUGGESTION_SCHEMA)


def test_rejects_an_unknown_json_mode():
    with pytest.raises(ValueError):
        provider(FakeClient(), json_mode="yaml")


def test_build_providers_keeps_order_and_skips_incomplete_ones():
    options = {
        "gemini": {"base_url": "https://g.test", "api_key": "", "model": "g", "requires_api_key": True},
        "groq": {"base_url": "https://q.test", "api_key": "key", "model": "q", "requires_api_key": True},
        "local": {"base_url": "http://localhost:11434/v1", "api_key": "", "model": "mine", "requires_api_key": False},
    }

    providers = build_providers(["local", "gemini", "unknown", "groq"], options, timeout=5)

    assert [p.label for p in providers] == ["local:mine", "groq:q"]
