"""Helpers shared by the tasks."""

import json
from collections.abc import Iterable, Mapping, Sequence

from llm.exceptions import InvalidSuggestion
from llm.types import ColumnInfo

FLAG_SCHEMA = {"type": "array", "items": {"type": "string", "enum": ["IGNORECASE", "MULTILINE", "DOTALL"]}}

_FLAG_ALIASES = {
    "I": "IGNORECASE",
    "IGNORECASE": "IGNORECASE",
    "IGNORE_CASE": "IGNORECASE",
    "M": "MULTILINE",
    "MULTILINE": "MULTILINE",
    "S": "DOTALL",
    "DOTALL": "DOTALL",
}


def squash_whitespace(text: str) -> str:
    return " ".join(text.split())


def required_instruction(text: str) -> str:
    instruction = squash_whitespace(text)
    if not instruction:
        raise ValueError("instruction must not be empty")
    return instruction


def conversation(system: str, examples: Iterable[tuple[str, Mapping]], request: str) -> list[dict[str, str]]:
    """System prompt, then each example as a user turn with the ideal JSON answer, then the request."""
    messages = [{"role": "system", "content": system}]
    for example_request, answer in examples:
        messages.append({"role": "user", "content": example_request})
        messages.append({"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)})
    messages.append({"role": "user", "content": request})
    return messages


def describe_columns(columns: Sequence[ColumnInfo]) -> str:
    return json.dumps([{"name": c.name, "kind": c.kind} for c in columns], ensure_ascii=False)


def clean_pattern(pattern: str) -> str:
    # In JSON "\b" is a backspace character, but the model almost certainly meant
    # the regex word boundary.
    return pattern.replace("\x08", r"\b")


def clean_flags(flags: Sequence[str]) -> list[str]:
    cleaned = []
    for flag in flags:
        key = flag.strip().upper().removeprefix("RE.")
        cleaned.append(_FLAG_ALIASES.get(key, flag))  # unknown flags are reported by the validator
    return list(dict.fromkeys(cleaned))


def resolve_columns(names: Sequence[str], columns: Sequence[ColumnInfo]) -> list[str]:
    """Map the model's column names to the real ones (case-insensitively)."""
    by_lower = {c.name.lower(): c.name for c in columns}
    resolved, unknown = [], []
    for name in names:
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
    return resolved
