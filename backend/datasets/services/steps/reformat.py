"""Standardise a format: capture the parts of matching values and rearrange them with a template."""

from collections.abc import Sequence
from dataclasses import dataclass

import regex
from django.conf import settings

from datasets.models import Dataset, Transformation
from datasets.services import regex_engine, storage
from datasets.services.generation import suggest_reformat
from datasets.services.steps.base import (
    PREVIEW_SAMPLE_LIMIT,
    commit_step,
    resolve_columns,
    sample_payload,
    undo_double_escaping,
)

KIND = Transformation.Kind.REFORMAT


@dataclass(frozen=True)
class ReformatPlan:
    compiled: regex.Pattern
    pattern: str
    flags: list[str]
    template: str
    columns: list[str]
    explanation: str
    source: str  # the LLM that wrote the pattern, or "manual"
    cached: bool = False


@dataclass(frozen=True)
class ReformatPreview:
    kind: str
    pattern: str
    flags: list[str]
    template: str
    columns: list[str]
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
    template: str = "",
    columns: Sequence[str] = (),
) -> ReformatPlan:
    """Use the explicit ``pattern`` and ``template`` if given; otherwise ask the LLM for them."""
    if pattern:
        compiled = regex_engine.compile_pattern(pattern, flags)
        regex_engine.check_template(compiled, template)
        return ReformatPlan(
            compiled, pattern, list(flags), template, resolve_columns(dataset, columns), explanation="", source="manual"
        )
    generated = suggest_reformat(dataset, instruction)
    suggestion = generated.suggestion
    target_columns = resolve_columns(dataset, columns or suggestion.target_columns)
    pattern = undo_double_escaping(dataset, suggestion.pattern, suggestion.flags, target_columns)
    template = suggestion.template
    if pattern != suggestion.pattern:
        # A model that doubled the backslashes in the pattern doubled them in the template too.
        template = template.replace("\\\\", "\\")
    compiled = regex_engine.compile_pattern(pattern, suggestion.flags)
    regex_engine.check_template(compiled, template)
    return ReformatPlan(
        compiled,
        pattern,
        suggestion.flags,
        template,
        target_columns,
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
    template: str = "",
    columns: Sequence[str] = (),
) -> ReformatPreview:
    """Show what the rewrite would do, without changing the dataset."""
    resolved = plan(dataset, instruction=instruction, pattern=pattern, flags=flags, template=template, columns=columns)
    frame = storage.load_version(dataset.id, dataset.current_version)
    outcome = regex_engine.replace_in_frame(
        frame,
        resolved.compiled,
        resolved.template,
        resolved.columns,
        timeout=settings.REGEX_TIMEOUT_SECONDS,
        sample_limit=PREVIEW_SAMPLE_LIMIT,
    )
    return ReformatPreview(
        kind=KIND,
        pattern=resolved.pattern,
        flags=resolved.flags,
        template=resolved.template,
        columns=resolved.columns,
        explanation=resolved.explanation,
        source=resolved.source,
        cached=resolved.cached,
        stats=outcome.stats(),
        samples=sample_payload(outcome.samples),
    )


def apply(
    dataset: Dataset,
    *,
    instruction: str = "",
    pattern: str = "",
    flags: Sequence[str] = (),
    template: str = "",
    columns: Sequence[str] = (),
    explanation: str = "",
    source: str = "",
) -> Dataset:
    """Apply the rewrite as a new version of the dataset and record it as a step."""
    resolved = plan(dataset, instruction=instruction, pattern=pattern, flags=flags, template=template, columns=columns)
    return commit_step(
        dataset,
        kind=KIND,
        transform=lambda frame: regex_engine.replace_in_frame(
            frame,
            resolved.compiled,
            resolved.template,
            resolved.columns,
            timeout=settings.REGEX_TIMEOUT_SECONDS,
            sample_limit=0,
        ),
        instruction=instruction,
        params={
            "pattern": resolved.pattern,
            "flags": resolved.flags,
            "template": resolved.template,
            "columns": resolved.columns,
        },
        explanation=explanation or resolved.explanation,
        source=source or resolved.source,
    )
