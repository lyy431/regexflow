"""What every kind of step shares: column resolution, preview samples and recording a new version."""

import logging
from collections.abc import Callable, Sequence

import pandas as pd
from django.conf import settings
from django.db import IntegrityError, transaction

from datasets import exceptions
from datasets.models import Dataset, Transformation
from datasets.services import column_profile, regex_engine, storage
from datasets.services.changes import CellChange, ReplacementOutcome

logger = logging.getLogger(__name__)

PREVIEW_SAMPLE_LIMIT = 10


def resolve_columns(dataset: Dataset, requested: Sequence[str]) -> list[str]:
    """Map requested names to real columns (case-insensitively), defaulting to the text columns."""
    if not requested:
        text_like = [c["name"] for c in dataset.columns if c["kind"] in column_profile.TEXT_LIKE_KINDS]
        return text_like or dataset.column_names
    by_lower = {name.lower(): name for name in dataset.column_names}
    resolved: list[str] = []
    for name in requested:
        actual = by_lower.get(name.strip().lower())
        if actual is None:
            raise exceptions.ColumnNotFound(
                f"There is no column named '{name}'. Columns: {', '.join(dataset.column_names)}."
            )
        if actual not in resolved:
            resolved.append(actual)
    return resolved


def resolve_column(dataset: Dataset, name: str) -> str:
    if not name.strip():
        raise exceptions.ColumnNotFound("Choose a column.")
    return resolve_columns(dataset, [name])[0]


def sample_payload(samples: Sequence[CellChange], *, include_after: bool = True) -> list[dict]:
    return [
        {
            "row": change.row,
            "column": change.column,
            "before": change.before,
            "after": change.after if include_after else None,
            "spans": [list(span) for span in change.spans],
        }
        for change in samples
    ]


def undo_double_escaping(dataset: Dataset, pattern: str, flags: Sequence[str], columns: Sequence[str]) -> str:
    """Return the pattern the model meant when it escaped its backslashes twice.

    Models sometimes write \\\\d (a literal backslash, then "d") where they mean \\d. Such
    a pattern finds nothing, so if the single-escaped version finds something in the
    data, that is the one the model meant.
    """
    if "\\\\" not in pattern:
        return pattern
    single = pattern.replace("\\\\", "\\")
    try:
        frame = storage.load_version(dataset.id, dataset.current_version)
        timeout = settings.REGEX_TIMEOUT_SECONDS
        if regex_engine.finds_match(frame, regex_engine.compile_pattern(pattern, flags), columns, timeout=timeout):
            return pattern
        if not regex_engine.finds_match(frame, regex_engine.compile_pattern(single, flags), columns, timeout=timeout):
            return pattern
    except (exceptions.InvalidPattern, exceptions.RegexTimeout):
        return pattern
    logger.info("Undid doubled backslashes in the generated pattern %r", pattern)
    return single


def commit_step(
    dataset: Dataset,
    *,
    kind: str,
    transform: Callable[[pd.DataFrame], ReplacementOutcome],
    instruction: str,
    params: dict,
    explanation: str,
    source: str,
) -> Dataset:
    """Apply ``transform`` to the current version and record the result as the next step."""
    try:
        with transaction.atomic():
            locked = Dataset.objects.select_for_update().get(pk=dataset.pk)
            outcome = transform(storage.load_version(locked.id, locked.current_version))
            if outcome.cells_changed == 0:
                raise exceptions.NoChanges()
            version = locked.current_version + 1
            storage.save_version(locked.id, version, outcome.frame)
            Transformation.objects.create(
                dataset=locked,
                version=version,
                kind=kind,
                instruction=instruction,
                params=params,
                explanation=explanation,
                source=source,
                stats=outcome.stats(),
            )
            locked.current_version = version
            locked.save(update_fields=["current_version", "updated_at"])
    except IntegrityError as exc:
        raise exceptions.ConcurrentModification() from exc
    logger.info(
        "Applied %s as step %d of dataset %s (%d cells changed)", kind, version, locked.id, outcome.cells_changed
    )
    return locked
