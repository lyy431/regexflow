"""Normalise values: replace the variants of each value in one column with a single clean form."""

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from datasets.models import Dataset, Transformation
from datasets.services import storage, value_mapping
from datasets.services.generation import suggest_mapping
from datasets.services.steps.base import PREVIEW_SAMPLE_LIMIT, commit_step, resolve_column, sample_payload

KIND = Transformation.Kind.NORMALIZE_VALUES


@dataclass(frozen=True)
class NormalizationPlan:
    column: str
    mapping: dict[str, str]
    counts: dict[str, int]  # how often each distinct value occurs
    explanation: str
    source: str  # the LLM that proposed the mapping, or "manual"
    cached: bool = False


@dataclass(frozen=True)
class NormalizePreview:
    kind: str
    column: str
    columns: list[str]
    mapping: list[dict]  # [{"from", "to", "count"}], most common first
    explanation: str
    source: str
    cached: bool
    stats: dict
    samples: list[dict]


def plan(
    dataset: Dataset,
    frame: pd.DataFrame,
    *,
    column: str,
    instruction: str = "",
    mapping: Mapping[str, str] | None = None,
) -> NormalizationPlan:
    """Use the given ``mapping`` (the user's, possibly edited) or ask the LLM to propose one."""
    name = resolve_column(dataset, column)
    values = value_mapping.distinct_values(frame, name)
    counts = dict(values)
    if mapping is not None:
        cleaned = {old: new for old, new in mapping.items() if old in counts and new != old}
        return NormalizationPlan(name, cleaned, counts, explanation="", source="manual")
    generated = suggest_mapping(name, values, instruction)
    suggestion = generated.suggestion
    return NormalizationPlan(
        name,
        {item.from_: item.to for item in suggestion.mapping},
        counts,
        explanation=suggestion.explanation,
        source=generated.provider,
        cached=generated.cached,
    )


def preview(
    dataset: Dataset, *, column: str, instruction: str = "", mapping: Mapping[str, str] | None = None
) -> NormalizePreview:
    """Show the proposed mapping and what it would change, without changing the dataset."""
    frame = storage.load_version(dataset.id, dataset.current_version)
    resolved = plan(dataset, frame, column=column, instruction=instruction, mapping=mapping)
    outcome = value_mapping.map_values(frame, resolved.column, resolved.mapping, sample_limit=PREVIEW_SAMPLE_LIMIT)
    rows = sorted(
        ({"from": old, "to": new, "count": resolved.counts[old]} for old, new in resolved.mapping.items()),
        key=lambda row: (-row["count"], row["from"]),
    )
    return NormalizePreview(
        kind=KIND,
        column=resolved.column,
        columns=[resolved.column],
        mapping=rows,
        explanation=resolved.explanation,
        source=resolved.source,
        cached=resolved.cached,
        stats=outcome.stats(),
        samples=sample_payload(outcome.samples),
    )


def apply(
    dataset: Dataset,
    *,
    column: str,
    instruction: str = "",
    mapping: Mapping[str, str] | None = None,
    explanation: str = "",
    source: str = "",
) -> Dataset:
    """Apply the mapping as a new version of the dataset and record it as a step."""
    frame = storage.load_version(dataset.id, dataset.current_version)
    resolved = plan(dataset, frame, column=column, instruction=instruction, mapping=mapping)
    return commit_step(
        dataset,
        kind=KIND,
        transform=lambda current: value_mapping.map_values(current, resolved.column, resolved.mapping, sample_limit=0),
        instruction=instruction,
        params={"column": resolved.column, "mapping": resolved.mapping},
        explanation=explanation or resolved.explanation,
        source=source or resolved.source,
    )
