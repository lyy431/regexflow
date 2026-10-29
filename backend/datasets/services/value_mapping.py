"""Replace whole cell values through a mapping (used to normalise categorical columns)."""

from collections.abc import Mapping

import pandas as pd

from datasets.exceptions import ColumnNotSuitable
from datasets.services.changes import CellChange, ReplacementOutcome

MAX_DISTINCT_VALUES = 300
MAX_VALUE_LENGTH = 200


def distinct_values(frame: pd.DataFrame, column: str) -> list[tuple[str, int]]:
    """The column's non-empty distinct values with their counts, most common first.

    Raises :class:`ColumnNotSuitable` for free-text columns: too many distinct or too long values.
    """
    counts: dict[str, int] = {}
    for value in frame[column].tolist():
        if isinstance(value, str) and value != "":
            counts[value] = counts.get(value, 0) + 1
    if len(counts) > MAX_DISTINCT_VALUES:
        raise ColumnNotSuitable(
            f"'{column}' has {len(counts):,} different values. Normalising works on columns with at most "
            f"{MAX_DISTINCT_VALUES} (such as states, countries or statuses)."
        )
    if any(len(value) > MAX_VALUE_LENGTH for value in counts):
        raise ColumnNotSuitable(
            f"'{column}' holds free text longer than {MAX_VALUE_LENGTH} characters, which can't be normalised."
        )
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def map_values(
    frame: pd.DataFrame, column: str, mapping: Mapping[str, str], *, sample_limit: int = 10
) -> ReplacementOutcome:
    """Replace each cell of ``column`` that equals a key of ``mapping`` with its value."""
    result = frame.copy()
    new_values = []
    samples: list[CellChange] = []
    changed = 0
    for row, value in enumerate(frame[column].tolist()):
        new_value = mapping.get(value, value) if isinstance(value, str) else value
        new_values.append(new_value)
        if new_value != value:
            changed += 1
            if len(samples) < sample_limit:
                samples.append(CellChange(row, column, value, new_value, ((0, len(value)),)))
    result[column] = new_values
    return ReplacementOutcome(result, {column: changed}, changed, changed, samples)
