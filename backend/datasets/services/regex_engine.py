"""Compile and apply untrusted regular expressions safely.

Patterns come from an LLM or straight from users. We use the ``regex``
package (a superset of the standard ``re`` syntax) because it supports
timeouts, so a catastrophically backtracking pattern cannot tie up the server.
"""

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import pandas as pd
import regex

from datasets.exceptions import InvalidPattern, RegexTimeout

MAX_PATTERN_LENGTH = 1000
SUPPORTED_FLAGS = {"IGNORECASE": regex.IGNORECASE, "MULTILINE": regex.MULTILINE, "DOTALL": regex.DOTALL}

# Non-empty probe strings used to reject patterns that can match zero characters
# inside text (such as \d* or \b): those would insert the replacement between
# characters. Matching a whole empty cell with ^$ is still allowed.
_ZERO_WIDTH_PROBES = ("a", "Hello, world 123", "user@example.com")
_PROBE_TIMEOUT_SECONDS = 0.5


def compile_pattern(pattern: str, flags: Iterable[str] = ()) -> regex.Pattern:
    """Compile ``pattern`` or raise :class:`InvalidPattern` with a readable reason."""
    if not pattern:
        raise InvalidPattern("The pattern is empty.")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise InvalidPattern(f"The pattern is longer than {MAX_PATTERN_LENGTH} characters.")
    flags = list(flags)
    unknown = sorted(set(flags) - SUPPORTED_FLAGS.keys())
    if unknown:
        raise InvalidPattern(f"Unsupported flag(s): {', '.join(unknown)}. Use IGNORECASE, MULTILINE or DOTALL.")
    combined = 0
    for flag in flags:
        combined |= SUPPORTED_FLAGS[flag]
    try:
        compiled = regex.compile(pattern, combined)
    except regex.error as exc:
        raise InvalidPattern(f"Invalid regular expression: {exc}.") from exc
    try:
        zero_width = any(
            match.start() == match.end()
            for probe in _ZERO_WIDTH_PROBES
            for match in compiled.finditer(probe, timeout=_PROBE_TIMEOUT_SECONDS)
        )
    except TimeoutError as exc:
        raise InvalidPattern("The pattern is too slow to evaluate (catastrophic backtracking).") from exc
    if zero_width:
        raise InvalidPattern(
            "The pattern can match empty text, so the replacement would be inserted between characters. "
            "Make it match at least one character."
        )
    return compiled


def literal_template(replacement: str) -> str:
    """Escape ``replacement`` so it is inserted verbatim, without group references."""
    return replacement.replace("\\", "\\\\")


@dataclass(frozen=True)
class CellChange:
    row: int
    column: str
    before: str
    after: str
    spans: tuple[tuple[int, int], ...]  # matched character ranges in ``before``


@dataclass
class ReplacementOutcome:
    frame: pd.DataFrame
    matches_by_column: dict[str, int]
    cells_changed: int
    rows_affected: int
    samples: list[CellChange] = field(default_factory=list)

    def stats(self) -> dict:
        return {
            "matches": sum(self.matches_by_column.values()),
            "cells_changed": self.cells_changed,
            "rows_affected": self.rows_affected,
            "matches_by_column": self.matches_by_column,
        }


def finds_match(frame: pd.DataFrame, compiled: regex.Pattern, columns: Sequence[str], *, timeout: float) -> bool:
    """Whether ``compiled`` matches anywhere in the text cells of ``columns``.

    Raises :class:`RegexTimeout` when the search takes longer than ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout
    for column in columns:
        for value in frame[column].tolist():
            if not isinstance(value, str):
                continue
            remaining = deadline - time.monotonic()
            try:
                if remaining <= 0:
                    raise TimeoutError
                if compiled.search(value, timeout=remaining):
                    return True
            except TimeoutError:
                raise RegexTimeout(f"Searching with the pattern took longer than {timeout:g} seconds.") from None
    return False


def replace_in_frame(
    frame: pd.DataFrame,
    compiled: regex.Pattern,
    replacement: str,
    columns: Sequence[str],
    *,
    timeout: float,
    sample_limit: int = 10,
) -> ReplacementOutcome:
    """Replace every match in ``columns`` with the literal ``replacement``.

    Raises :class:`RegexTimeout` when the whole operation exceeds ``timeout`` seconds.
    """
    template = literal_template(replacement)
    deadline = time.monotonic() + timeout
    result = frame.copy()
    matches_by_column: dict[str, int] = {}
    affected_rows: set[int] = set()
    cells_changed = 0
    samples: list[CellChange] = []

    for column in columns:
        new_values = []
        column_matches = 0
        for row, value in enumerate(frame[column].tolist()):
            if not isinstance(value, str):
                new_values.append(value)
                continue
            remaining = deadline - time.monotonic()
            try:
                if remaining <= 0:
                    raise TimeoutError
                new_value, count = compiled.subn(template, value, timeout=remaining)
            except TimeoutError:
                raise RegexTimeout(
                    f"Applying the pattern took longer than {timeout:g} seconds. "
                    "Try a simpler or more specific pattern."
                ) from None
            new_values.append(new_value)
            if not count:
                continue
            column_matches += count
            if new_value != value:
                cells_changed += 1
                affected_rows.add(row)
                if len(samples) < sample_limit:
                    spans = tuple(match.span() for match in compiled.finditer(value))
                    samples.append(CellChange(row, column, value, new_value, spans))
        result[column] = new_values
        matches_by_column[column] = column_matches

    return ReplacementOutcome(result, matches_by_column, cells_changed, len(affected_rows), samples)
