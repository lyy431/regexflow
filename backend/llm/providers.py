"""LLM providers.

Gemini, Groq and local model servers (Ollama, llama.cpp, vLLM, LM Studio) all
offer an OpenAI-compatible Chat Completions API, so one provider class covers
them; they differ only in configuration.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import openai

from llm.exceptions import ProviderUnavailable

logger = logging.getLogger(__name__)

Message = Mapping[str, str]
JSON_MODES = ("json_schema", "json_object", "none")


class LLMProvider(Protocol):
    label: str

    def complete(self, messages: Sequence[Message], schema: Mapping[str, Any]) -> str:
        """Return the text of the model's reply. Raise ProviderUnavailable on failure."""
        ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str = "",
        json_mode: str = "json_object",
        reasoning_effort: str = "",
        timeout: float = 15.0,
        client: Any = None,
    ):
        if json_mode not in JSON_MODES:
            raise ValueError(f"json_mode must be one of {JSON_MODES}, not {json_mode!r}")
        self.name = name
        self.model = model
        self.json_mode = json_mode
        self.reasoning_effort = reasoning_effort
        self.label = f"{name}:{model}"
        # Local servers ignore the key, but the SDK insists on a non-empty one.
        # No automatic retries: a retry would sit out a second timeout (or a long
        # Retry-After) while the next provider could answer straight away.
        self._client = client or openai.OpenAI(
            base_url=base_url, api_key=api_key or "not-needed", timeout=timeout, max_retries=0
        )

    def complete(self, messages: Sequence[Message], schema: Mapping[str, Any]) -> str:
        request: dict[str, Any] = {"model": self.model, "messages": [dict(m) for m in messages]}
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort
        response_format = self._response_format(schema)
        try:
            if response_format is None:
                return self._create(request)
            try:
                return self._create({**request, "response_format": response_format})
            except openai.BadRequestError as exc:
                # Some OpenAI-compatible servers reject structured-output options. The
                # prompt asks for JSON anyway, so try once more without them.
                logger.warning("%s rejected response_format (%s); retrying without it.", self.label, exc)
                return self._create(request)
        except openai.RateLimitError as exc:
            raise ProviderUnavailable(f"{self.label} is rate-limited") from exc
        except openai.APITimeoutError as exc:
            raise ProviderUnavailable(f"{self.label} timed out") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailable(f"could not reach {self.label}") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise ProviderUnavailable(f"{self.label} rejected the API key") from exc
        except openai.APIStatusError as exc:
            raise ProviderUnavailable(f"{self.label} returned HTTP {exc.status_code}") from exc

    def _create(self, request: dict[str, Any]) -> str:
        completion = self._client.chat.completions.create(**request)
        content = completion.choices[0].message.content if completion.choices else None
        if not content:
            raise ProviderUnavailable(f"{self.label} returned an empty reply")
        return content

    def _response_format(self, schema: Mapping[str, Any]) -> dict[str, Any] | None:
        if self.json_mode == "json_schema":
            return {"type": "json_schema", "json_schema": {"name": "regex_suggestion", "schema": dict(schema)}}
        if self.json_mode == "json_object":
            return {"type": "json_object"}
        return None


def build_providers(
    names: Sequence[str], options: Mapping[str, Mapping[str, Any]], timeout: float
) -> list[OpenAICompatibleProvider]:
    """Create the configured providers, in priority order, skipping incomplete ones."""
    providers = []
    for name in names:
        config = options.get(name)
        if config is None:
            logger.warning("Unknown LLM provider %r in LLM_PROVIDERS; skipping it.", name)
            continue
        if not config.get("model") or (config.get("requires_api_key") and not config.get("api_key")):
            logger.debug("LLM provider %r has no model or API key configured; skipping it.", name)
            continue
        providers.append(
            OpenAICompatibleProvider(
                name=name,
                model=config["model"],
                base_url=config["base_url"],
                api_key=config.get("api_key", ""),
                json_mode=config.get("json_mode", "json_object"),
                reasoning_effort=config.get("reasoning_effort", ""),
                timeout=timeout,
            )
        )
    return providers
