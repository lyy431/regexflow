"""Compile and apply untrusted regular expressions safely.

Patterns come from an LLM or straight from users. We use the ``regex``
package (a superset of the standard ``re`` syntax) because it supports
timeouts, so a catastrophically backtracking pattern cannot tie up the server.
"""

import time
from collections.abc import Iterable, Sequence

import pandas as pd
import regex

from datasets.exceptions import InvalidPattern, RegexTimeout
from datasets.services.changes import CellChange, ReplacementOutcome

MAX_PATTERN_LENGTH = 1000
MAX_TEMPLATE_LENGTH = 1000
SUPPORTED_FLAGS = {"IGNORECASE": regex.IGNORECASE, "MULTILINE": regex.MULTILINE, "DOTALL": regex.DOTALL}

# A backslash in a replacement template: a group reference (\g<name>, \g<2>, \2),
# another escaped character, or a stray backslash at the very end.
_TEMPLATE_ESCAPE = regex.compile(r"\\(?:g<([^>]*)>|([0-9]{1,2})|(.)|$)", regex.DOTALL)
_TEMPLATE_CHARACTER_ESCAPES = frozenset("\\ntr")

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


def check_template(compiled: regex.Pattern, template: str) -> None:
    """Raise :class:`InvalidPattern` unless every group ``template`` refers to exists in ``compiled``."""
    if not template:
        raise InvalidPattern("The template is empty.")
    if len(template) > MAX_TEMPLATE_LENGTH:
        raise InvalidPattern(f"The template is longer than {MAX_TEMPLATE_LENGTH} characters.")
    for escape in _TEMPLATE_ESCAPE.finditer(template):
        name, number, character = escape.groups()
        if name is not None:
            if not (name.isdigit() and int(name) <= compiled.groups) and name not in compiled.groupindex:
                raise InvalidPattern(f"The template refers to \\g<{name}>, but the pattern has no such group.")
        elif number is not None:
            if not 1 <= int(number) <= compiled.groups:
                raise InvalidPattern(
                    f"The template refers to group {number}, but the pattern has {compiled.groups} group(s)."
                )
        elif character not in _TEMPLATE_CHARACTER_ESCAPES:
            raise InvalidPattern("The template has a stray backslash; write \\\\ for a literal backslash.")


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
    template: str,
    columns: Sequence[str],
    *,
    timeout: float,
    sample_limit: int = 10,
) -> ReplacementOutcome:
    """Replace every match in ``columns`` using a replacement ``template`` (``\\g<name>`` refers to a group).

    Pass ``literal_template(text)`` to insert text verbatim. Raises :class:`RegexTimeout`
    when the whole operation exceeds ``timeout`` seconds.
    """
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
            except (regex.error, IndexError) as exc:  # a template the checks above did not catch
                raise InvalidPattern(f"The replacement template could not be applied: {exc}.") from exc
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
