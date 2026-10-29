"""Find and replace: match text with a regex and put fixed text in its place."""

from collections.abc import Sequence
from dataclasses import dataclass

import regex
from django.conf import settings

from datasets import exceptions
from datasets.models import Dataset, Transformation
from datasets.services import regex_engine, storage
from datasets.services.generation import suggest_regex
from datasets.services.steps.base import (
    PREVIEW_SAMPLE_LIMIT,
    commit_step,
    resolve_columns,
    sample_payload,
    undo_double_escaping,
)

KIND = Transformation.Kind.REGEX_REPLACE


@dataclass(frozen=True)
class ReplacementPlan:
    """A resolved replacement: what to match, where, and what to insert instead."""

    compiled: regex.Pattern
    pattern: str
    flags: list[str]
    columns: list[str]
    replacement: str | None  # None until the user, or their instruction, says what to use
    explanation: str
    source: str  # the LLM that wrote the pattern, or "manual"
    cached: bool = False


@dataclass(frozen=True)
class FindReplacePreview:
    kind: str
    pattern: str
    flags: list[str]
    columns: list[str]
    replacement: str | None
    explanation: str
    source: str
    cached: bool
    stats: dict
    samples: list[dict]


def plan(
    dataset: Dataset,
    *,
    instruction: str = "",
    pattern: str = "",
    flags: Sequence[str] = (),
    replacement: str | None = None,
    columns: Sequence[str] = (),
) -> ReplacementPlan:
    """Use the explicit ``pattern`` if given; otherwise ask the LLM to write one from ``instruction``."""
    if pattern:
        return ReplacementPlan(
            compiled=regex_engine.compile_pattern(pattern, flags),
            pattern=pattern,
            flags=list(flags),
            columns=resolve_columns(dataset, columns),
            replacement=replacement,
            explanation="",
            source="manual",
        )
    generated = suggest_regex(dataset, instruction)
    suggestion = generated.suggestion
    if replacement is None and suggestion.replacement_specified:
        replacement = suggestion.replacement
    # Columns picked in the UI win over the columns the model read from the instruction.
    target_columns = resolve_columns(dataset, columns or suggestion.target_columns)
    pattern = undo_double_escaping(dataset, suggestion.pattern, suggestion.flags, target_columns)
    return ReplacementPlan(
        compiled=regex_engine.compile_pattern(pattern, suggestion.flags),
        pattern=pattern,
        flags=suggestion.flags,
        columns=target_columns,
        replacement=replacement,
        explanation=suggestion.explanation,
        source=generated.provider,
        cached=generated.cached,
    )


def preview(
    dataset: Dataset,
    *,
    instruction: str = "",
    pattern: str = "",
    flags: Sequence[str] = (),
    replacement: str | None = None,
    columns: Sequence[str] = (),
) -> FindReplacePreview:
    """Show what a replacement would do, without changing the dataset."""
    resolved = plan(
        dataset, instruction=instruction, pattern=pattern, flags=flags, replacement=replacement, columns=columns
    )
    frame = storage.load_version(dataset.id, dataset.current_version)
    outcome = regex_engine.replace_in_frame(
        frame,
        resolved.compiled,
        regex_engine.literal_template(resolved.replacement or ""),
        resolved.columns,
        timeout=settings.REGEX_TIMEOUT_SECONDS,
        sample_limit=PREVIEW_SAMPLE_LIMIT,
    )
    return FindReplacePreview(
        kind=KIND,
        pattern=resolved.pattern,
        flags=resolved.flags,
        columns=resolved.columns,
        replacement=resolved.replacement,
        explanation=resolved.explanation,
        source=resolved.source,
        cached=resolved.cached,
        stats=outcome.stats(),
        samples=sample_payload(outcome.samples, include_after=resolved.replacement is not None),
    )


def apply(
    dataset: Dataset,
    *,
    instruction: str = "",
    pattern: str = "",
    flags: Sequence[str] = (),
    replacement: str | None = None,
    columns: Sequence[str] = (),
    explanation: str = "",
    source: str = "",
) -> Dataset:
    """Apply a replacement as a new version of the dataset and record it as a step."""
    resolved = plan(
        dataset, instruction=instruction, pattern=pattern, flags=flags, replacement=replacement, columns=columns
    )
    if resolved.replacement is None:
        raise exceptions.MissingReplacement()
    template = regex_engine.literal_template(resolved.replacement)
    return commit_step(
        dataset,
        kind=KIND,
        transform=lambda frame: regex_engine.replace_in_frame(
            frame, resolved.compiled, template, resolved.columns, timeout=settings.REGEX_TIMEOUT_SECONDS, sample_limit=0
        ),
        instruction=instruction,
        params={
            "pattern": resolved.pattern,
            "flags": resolved.flags,
            "replacement": resolved.replacement,
            "columns": resolved.columns,
        },
        explanation=explanation or resolved.explanation,
        source=source or resolved.source,
    )
