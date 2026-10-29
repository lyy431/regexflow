"""Test doubles for code that depends on LLM providers."""

import json
from collections.abc import Mapping, Sequence
from typing import Any


class FakeProvider:
    """Replays scripted replies in order: strings, dicts (sent as JSON) or exceptions to raise."""

    def __init__(self, *replies, label: str = "fake:model"):
        self.label = label
        self._replies = list(replies)
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: Sequence[Mapping[str, str]], schema: Mapping[str, Any]) -> str:
        self.calls.append([dict(message) for message in messages])
        if not self._replies:
            raise AssertionError(f"{self.label} was called more times than it has scripted replies")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def suggestion(pattern: str, **overrides) -> dict:
    """A well-formed model reply for ``pattern``; override any field."""
    return {
        "pattern": pattern,
        "flags": [],
        "target_columns": [],
        "replacement_specified": False,
        "replacement": "",
        "explanation": "Test pattern.",
        "error": "",
        **overrides,
    }
