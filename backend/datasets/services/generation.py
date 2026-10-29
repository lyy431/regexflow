"""Ask the LLM for a regex that fits a dataset's columns."""

from datasets.exceptions import InvalidPattern
from datasets.models import Dataset
from datasets.services import regex_engine
from llm import ColumnInfo, GenerationResult, InvalidSuggestion, RegexSuggestion, get_regex_generator


def suggest_regex(dataset: Dataset, instruction: str) -> GenerationResult:
    # Only column names and kinds are sent to the model, never cell values.
    columns = [ColumnInfo(name=column["name"], kind=column["kind"]) for column in dataset.columns]
    return get_regex_generator().generate(instruction, columns, validate=_validate)


def configured_providers() -> list[str]:
    return [provider.label for provider in get_regex_generator().providers]


def _validate(suggestion: RegexSuggestion) -> None:
    try:
        regex_engine.compile_pattern(suggestion.pattern, suggestion.flags)
    except InvalidPattern as exc:
        raise InvalidSuggestion(exc.message) from exc
