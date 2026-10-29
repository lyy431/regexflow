"""Structured answers from interchangeable LLM providers.

This package knows nothing about datasets or HTTP: a task describes a question
(find-and-replace regex, format rewrite, value mapping) and the engine returns a
validated answer from the first provider that can give one.
"""

from llm.engine import Generator, Task, get_generator, parse_reply
from llm.exceptions import (
    AllProvidersFailed,
    InvalidOutput,
    InvalidSuggestion,
    LLMError,
    NoProviderConfigured,
    ProviderError,
    ProviderUnavailable,
    RequestNotPossible,
)
from llm.tasks import FindReplaceTask, NormalizeTask, ReformatTask
from llm.types import (
    ColumnInfo,
    GenerationResult,
    MappingSuggestion,
    ReformatSuggestion,
    RegexSuggestion,
    ValueMapping,
)

__all__ = [
    "AllProvidersFailed",
    "ColumnInfo",
    "FindReplaceTask",
    "GenerationResult",
    "Generator",
    "InvalidOutput",
    "InvalidSuggestion",
    "LLMError",
    "MappingSuggestion",
    "NoProviderConfigured",
    "NormalizeTask",
    "ProviderError",
    "ProviderUnavailable",
    "ReformatSuggestion",
    "ReformatTask",
    "RegexSuggestion",
    "RequestNotPossible",
    "Task",
    "ValueMapping",
    "get_generator",
    "parse_reply",
]
