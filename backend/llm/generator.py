"""Ask LLM providers for a regex suggestion, validate it, and fall back between providers."""

import hashlib
import json
import logging
import re
from collections.abc import Callable, Sequence

from django.conf import settings
from django.core.cache import BaseCache, cache
from pydantic import ValidationError

from llm.exceptions import (
    AllProvidersFailed,
    InvalidOutput,
    InvalidSuggestion,
    NoProviderConfigured,
    PatternNotExpressible,
    ProviderError,
)
from llm.prompts import PROMPT_VERSION, SUGGESTION_SCHEMA, build_messages, repair_message
from llm.providers import LLMProvider, build_providers
from llm.types import ColumnInfo, GenerationResult, RegexSuggestion

logger = logging.getLogger(__name__)

Validator = Callable[[RegexSuggestion], None]

_FLAG_ALIASES = {
    "I": "IGNORECASE",
    "IGNORECASE": "IGNORECASE",
    "IGNORE_CASE": "IGNORECASE",
    "M": "MULTILINE",
    "MULTILINE": "MULTILINE",
    "S": "DOTALL",
    "DOTALL": "DOTALL",
}
_JSON_ESCAPE_PAIR = re.compile(r"\\(.)", re.DOTALL)
_VALID_JSON_ESCAPES = frozenset('"\\/bfnrtu')


class RegexGenerator:
    """Turns an instruction into a validated regex suggestion using the first provider that works."""

    max_repairs = 1

    def __init__(self, providers: Sequence[LLMProvider], cache: BaseCache | None = None, cache_ttl: int = 86400):
        self.providers = list(providers)
        self.cache = cache
        self.cache_ttl = cache_ttl

    def generate(
        self, instruction: str, columns: Sequence[ColumnInfo], validate: Validator | None = None
    ) -> GenerationResult:
        """Return a suggestion whose pattern passed ``validate``.

        ``validate`` raises :class:`InvalidSuggestion` for patterns the caller can't use;
        the model is then asked to fix its answer once before the next provider is tried.
        """
        instruction = " ".join(instruction.split())
        if not instruction:
            raise ValueError("instruction must not be empty")
        if not self.providers:
            raise NoProviderConfigured("No LLM provider is configured.")

        key = self._cache_key(instruction, columns)
        if self.cache is not None and (hit := self.cache.get(key)) is not None:
            return GenerationResult(RegexSuggestion.model_validate(hit["suggestion"]), hit["provider"], cached=True)

        failures = []
        for provider in self.providers:
            try:
                suggestion = self._ask(provider, instruction, columns, validate)
            except ProviderError as exc:
                logger.warning("LLM provider %s failed: %s", provider.label, exc)
                failures.append(f"{provider.label}: {exc}")
                continue
            logger.info("Generated a regex with %s", provider.label)
            if self.cache is not None:
                self.cache.set(key, {"suggestion": suggestion.model_dump(), "provider": provider.label}, self.cache_ttl)
            return GenerationResult(suggestion, provider.label)
        raise AllProvidersFailed(failures)

    def _ask(
        self, provider: LLMProvider, instruction: str, columns: Sequence[ColumnInfo], validate: Validator | None
    ) -> RegexSuggestion:
        messages = build_messages(instruction, columns)
        for attempt in range(self.max_repairs + 1):
            reply = provider.complete(messages, SUGGESTION_SCHEMA)
            try:
                return _check(parse_suggestion(reply), columns, validate)
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

    def _cache_key(self, instruction: str, columns: Sequence[ColumnInfo]) -> str:
        payload = json.dumps(
            {
                "prompt": PROMPT_VERSION,
                "instruction": instruction,
                "columns": [[c.name, c.kind] for c in columns],
                "providers": [p.label for p in self.providers],
            },
            sort_keys=True,
        )
        return "llm-regex:" + hashlib.sha256(payload.encode()).hexdigest()


def parse_suggestion(reply: str) -> RegexSuggestion:
    """Extract and validate the JSON object in a model reply, tolerating common mistakes."""
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end < start:
        raise InvalidSuggestion("The reply did not contain a JSON object.")
    data = _loads_lenient(reply[start : end + 1])
    if not isinstance(data, dict):
        raise InvalidSuggestion("The reply must be a JSON object.")
    try:
        suggestion = RegexSuggestion.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        raise InvalidSuggestion(f"Field '{field}': {first['msg']}.") from exc
    return _normalise(suggestion)


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


def _normalise(suggestion: RegexSuggestion) -> RegexSuggestion:
    # In JSON "\b" is a backspace character, but the model almost certainly meant
    # the regex word boundary.
    pattern = suggestion.pattern.replace("\x08", r"\b")
    flags = []
    for flag in suggestion.flags:
        key = flag.strip().upper().removeprefix("RE.")
        flags.append(_FLAG_ALIASES.get(key, flag))  # unknown flags are reported by the validator
    return suggestion.model_copy(update={"pattern": pattern, "flags": list(dict.fromkeys(flags))})


def _check(suggestion: RegexSuggestion, columns: Sequence[ColumnInfo], validate: Validator | None) -> RegexSuggestion:
    if suggestion.error:
        raise PatternNotExpressible(suggestion.error)
    if not suggestion.pattern:
        raise InvalidSuggestion("'pattern' is empty although 'error' is empty too.")
    suggestion = _resolve_target_columns(suggestion, columns)
    if validate is not None:
        validate(suggestion)
    return suggestion


def _resolve_target_columns(suggestion: RegexSuggestion, columns: Sequence[ColumnInfo]) -> RegexSuggestion:
    by_lower = {c.name.lower(): c.name for c in columns}
    resolved, unknown = [], []
    for name in suggestion.target_columns:
        actual = by_lower.get(name.strip().lower())
        if actual is None:
            unknown.append(name)
        elif actual not in resolved:
            resolved.append(actual)
    if unknown:
        listed = ", ".join(repr(name) for name in unknown)
        raise InvalidSuggestion(
            f"Unknown column(s) {listed}. Use only names from the column list, or [] for all text columns."
        )
    return suggestion.model_copy(update={"target_columns": resolved})


def get_regex_generator() -> RegexGenerator:
    """Build a generator from Django settings (provider order, keys, models)."""
    providers = build_providers(settings.LLM_PROVIDERS, settings.LLM_PROVIDER_OPTIONS, settings.LLM_TIMEOUT_SECONDS)
    return RegexGenerator(providers, cache=cache, cache_ttl=settings.LLM_CACHE_TTL_SECONDS)
