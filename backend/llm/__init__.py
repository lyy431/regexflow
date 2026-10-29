"""Natural language -> regular expression generation, backed by interchangeable LLM providers.

This package knows nothing about datasets or HTTP: it receives an instruction
plus column metadata and returns a validated :class:`RegexSuggestion`.
"""

from llm.exceptions import (
    AllProvidersFailed,
    InvalidOutput,
    InvalidSuggestion,
    LLMError,
    NoProviderConfigured,
    PatternNotExpressible,
    ProviderError,
    ProviderUnavailable,
)
from llm.generator import RegexGenerator, get_regex_generator, parse_suggestion
from llm.types import ColumnInfo, GenerationResult, RegexSuggestion

__all__ = [
    "AllProvidersFailed",
    "ColumnInfo",
    "GenerationResult",
    "InvalidOutput",
    "InvalidSuggestion",
    "LLMError",
    "NoProviderConfigured",
    "PatternNotExpressible",
    "ProviderError",
    "ProviderUnavailable",
    "RegexGenerator",
    "RegexSuggestion",
    "get_regex_generator",
    "parse_suggestion",
]
