"""Ask LLM providers for a structured answer, validate it, and fall back between providers.

Each kind of question is a *task* (see ``llm.tasks``) that supplies the prompt, the
JSON schema, the answer model and the checks. The engine handles the rest: trying
providers in order, asking a model once to fix an unusable answer, and caching.
"""

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from django.conf import settings
from django.core.cache import BaseCache, cache
from pydantic import ValidationError

from llm.exceptions import AllProvidersFailed, InvalidOutput, InvalidSuggestion, NoProviderConfigured, ProviderError
from llm.providers import LLMProvider, build_providers
from llm.types import Answer, GenerationResult

logger = logging.getLogger(__name__)

_JSON_ESCAPE_PAIR = re.compile(r"\\(.)", re.DOTALL)
_VALID_JSON_ESCAPES = frozenset('"\\/bfnrtu')


class Task[AnswerT: Answer](Protocol):
    """One kind of question for the model."""

    name: str  # identifies the task in cache keys and logs
    answer_model: type[AnswerT]
    schema: Mapping[str, Any]

    def messages(self) -> list[dict[str, str]]:
        """The conversation to send: system prompt, examples and the actual request."""
        ...

    def check(self, answer: AnswerT) -> AnswerT:
        """Normalise and validate an answer; raise InvalidSuggestion to ask the model for a fix."""
        ...

    def cache_key_data(self) -> Mapping[str, Any]:
        """Everything that determines the answer: the inputs and the prompt version."""
        ...


class Generator:
    """Gets a validated answer to a task from the first provider that can give one."""

    max_repairs = 1

    def __init__(self, providers: Sequence[LLMProvider], cache: BaseCache | None = None, cache_ttl: int = 86400):
        self.providers = list(providers)
        self.cache = cache
        self.cache_ttl = cache_ttl

    def run[AnswerT: Answer](self, task: Task[AnswerT]) -> GenerationResult[AnswerT]:
        if not self.providers:
            raise NoProviderConfigured("No LLM provider is configured.")

        key = self._cache_key(task)
        if self.cache is not None and (hit := self.cache.get(key)) is not None:
            return GenerationResult(task.answer_model.model_validate(hit["answer"]), hit["provider"], cached=True)

        failures = []
        for provider in self.providers:
            try:
                answer = self._ask(provider, task)
            except ProviderError as exc:
                logger.warning("LLM provider %s failed on %s: %s", provider.label, task.name, exc)
                failures.append(f"{provider.label}: {exc}")
                continue
            logger.info("Answered %s with %s", task.name, provider.label)
            if self.cache is not None:
                self.cache.set(
                    key, {"answer": answer.model_dump(by_alias=True), "provider": provider.label}, self.cache_ttl
                )
            return GenerationResult(answer, provider.label)
        raise AllProvidersFailed(failures)

    def _ask[AnswerT: Answer](self, provider: LLMProvider, task: Task[AnswerT]) -> AnswerT:
        messages = task.messages()
        for attempt in range(self.max_repairs + 1):
            reply = provider.complete(messages, task.schema)
            try:
                return task.check(parse_reply(reply, task.answer_model))
            except InvalidSuggestion as exc:
                if attempt == self.max_repairs:
                    raise InvalidOutput(f"unusable answer after {attempt + 1} attempts: {exc}") from exc
                logger.info("%s gave an unusable answer (%s); asking it to fix it.", provider.label, exc)
                messages = [
                    *messages,
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": repair_message(str(exc))},
                ]
        raise AssertionError("unreachable")

    def _cache_key(self, task: Task) -> str:
        payload = json.dumps(
            {"data": task.cache_key_data(), "providers": [p.label for p in self.providers]},
            sort_keys=True,
            ensure_ascii=False,
        )
        return f"llm-{task.name}:" + hashlib.sha256(payload.encode()).hexdigest()


def parse_reply[AnswerT: Answer](reply: str, answer_model: type[AnswerT]) -> AnswerT:
    """Extract and validate the JSON object in a model reply, tolerating common mistakes."""
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end < start:
        raise InvalidSuggestion("The reply did not contain a JSON object.")
    data = _loads_lenient(reply[start : end + 1])
    if not isinstance(data, dict):
        raise InvalidSuggestion("The reply must be a JSON object.")
    try:
        return answer_model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        raise InvalidSuggestion(f"Field '{field}': {first['msg']}.") from exc


def _loads_lenient(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Models sometimes forget to double regex backslashes ("\d" instead of "\\d").
    # Walk the escape pairs left to right and double only the invalid ones.
    repaired = _JSON_ESCAPE_PAIR.sub(
        lambda m: m.group(0) if m.group(1) in _VALID_JSON_ESCAPES else "\\\\" + m.group(1), text
    )
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as exc:
        raise InvalidSuggestion(f"The reply was not valid JSON ({exc.msg}).") from exc


def repair_message(problem: str) -> str:
    return f"That reply could not be used: {problem} Reply again with only the corrected JSON object."


def get_generator() -> Generator:
    """Build a generator from Django settings (provider order, keys, models)."""
    providers = build_providers(settings.LLM_PROVIDERS, settings.LLM_PROVIDER_OPTIONS, settings.LLM_TIMEOUT_SECONDS)
    return Generator(providers, cache=cache, cache_ttl=settings.LLM_CACHE_TTL_SECONDS)
