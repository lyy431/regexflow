"""Ask the LLM for the variable part of a step: a regex, a format rewrite or a value mapping."""

from collections.abc import Sequence

from datasets.exceptions import InvalidPattern
from datasets.models import Dataset
from datasets.services import regex_engine
from llm import (
    ColumnInfo,
    FindReplaceTask,
    GenerationResult,
    InvalidSuggestion,
    MappingSuggestion,
    NormalizeTask,
    ReformatSuggestion,
    ReformatTask,
    RegexSuggestion,
    get_generator,
)


def suggest_regex(dataset: Dataset, instruction: str) -> GenerationResult[RegexSuggestion]:
    # Only column names and kinds are sent to the model, never cell values.
    return get_generator().run(FindReplaceTask(instruction, _columns(dataset), validate=_check_regex))


def suggest_reformat(dataset: Dataset, instruction: str) -> GenerationResult[ReformatSuggestion]:
    # Only column names and kinds are sent to the model, never cell values.
    return get_generator().run(ReformatTask(instruction, _columns(dataset), validate=_check_reformat))


def suggest_mapping(column: str, values: Sequence[tuple[str, int]], goal: str) -> GenerationResult[MappingSuggestion]:
    # This step does send cell values: the column's distinct values. The UI says so up front.
    return get_generator().run(NormalizeTask(column, values, goal))


def configured_providers() -> list[str]:
    return [provider.label for provider in get_generator().providers]


def _columns(dataset: Dataset) -> list[ColumnInfo]:
    return [ColumnInfo(name=column["name"], kind=column["kind"]) for column in dataset.columns]


def _check_regex(suggestion: RegexSuggestion) -> None:
    try:
        regex_engine.compile_pattern(suggestion.pattern, suggestion.flags)
    except InvalidPattern as exc:
        raise InvalidSuggestion(exc.message) from exc


def _check_reformat(suggestion: ReformatSuggestion) -> None:
    try:
        compiled = regex_engine.compile_pattern(suggestion.pattern, suggestion.flags)
        regex_engine.check_template(compiled, suggestion.template)
    except InvalidPattern as exc:
        raise InvalidSuggestion(exc.message) from exc
