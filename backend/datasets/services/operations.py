"""Dataset use cases: upload, browse, preview / apply / undo replacements, export and cleanup.

Views call these functions. They hold the business rules and coordinate the
database, the Parquet storage, the regex engine and the LLM.
"""

import io
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePath

import regex
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from datasets import exceptions
from datasets.models import Dataset, Transformation
from datasets.services import column_profile, regex_engine, storage
from datasets.services.file_reader import read_table
from datasets.services.generation import suggest_regex

logger = logging.getLogger(__name__)

PREVIEW_SAMPLE_LIMIT = 10
EXCEL_MAX_DATA_ROWS = 1_048_575  # Excel's row limit, minus the header row


# --- Upload and lifecycle -------------------------------------------------------------


def create_dataset(uploaded_file) -> Dataset:
    _purge_quietly()
    parsed = read_table(uploaded_file, uploaded_file.name)
    with transaction.atomic():
        dataset = Dataset.objects.create(
            name=PurePath(uploaded_file.name).name[:255],
            file_format=parsed.file_format,
            row_count=len(parsed.frame),
            columns=column_profile.profile_columns(parsed.frame),
        )
        storage.save_version(dataset.id, 0, parsed.frame)
    logger.info("Created dataset %s: %d rows, %d columns", dataset.id, dataset.row_count, len(dataset.columns))
    return dataset


def delete_dataset(dataset: Dataset) -> None:
    dataset_id = dataset.id
    dataset.delete()
    storage.delete_dataset(dataset_id)


def purge_expired() -> int:
    """Delete datasets idle for longer than DATASET_TTL_HOURS and return how many were removed."""
    if settings.DATASET_TTL_HOURS <= 0:
        return 0
    cutoff = timezone.now() - timedelta(hours=settings.DATASET_TTL_HOURS)
    expired = list(Dataset.objects.filter(updated_at__lt=cutoff).values_list("id", flat=True))
    if expired:
        Dataset.objects.filter(id__in=expired).delete()
        for dataset_id in expired:
            storage.delete_dataset(dataset_id)
        logger.info("Purged %d expired dataset(s)", len(expired))
    return len(expired)


def _purge_quietly() -> None:
    # Free hosting rarely offers cron jobs, so each upload also triggers the cleanup.
    try:
        purge_expired()
    except Exception:
        logger.exception("Purging expired datasets failed")


# --- Browsing ---------------------------------------------------------------------


def get_page(dataset: Dataset, page: int, page_size: int) -> dict:
    """Return one page of the current version, flagging cells changed by the latest step."""
    total_pages = max(1, math.ceil(dataset.row_count / page_size))
    page = min(page, total_pages)
    offset = (page - 1) * page_size
    rows = storage.read_rows(dataset.id, dataset.current_version, offset, page_size)
    changed_cells = None
    if dataset.current_version > 0:
        previous = storage.read_rows(dataset.id, dataset.current_version - 1, offset, page_size)
        changed_cells = [
            [index for index, (new, old) in enumerate(zip(row, old_row, strict=True)) if new != old]
            for row, old_row in zip(rows, previous, strict=True)
        ]
    return {
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_rows": dataset.row_count,
        "version": dataset.current_version,
        "columns": dataset.column_names,
        "rows": rows,
        "changed_cells": changed_cells,
    }


# --- Replacements -------------------------------------------------------------------


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
class Preview:
    pattern: str
    flags: list[str]
    columns: list[str]
    replacement: str | None
    explanation: str
    source: str
    cached: bool
    stats: dict
    samples: list[dict]


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


def plan_replacement(
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
    pattern = _undo_double_escaping(dataset, suggestion.pattern, suggestion.flags, target_columns)
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


def _undo_double_escaping(dataset: Dataset, pattern: str, flags: Sequence[str], columns: Sequence[str]) -> str:
    # Models sometimes escape backslashes twice and write \\d (a literal backslash, then "d")
    # where they mean \d. Such a pattern finds nothing, so if the single-escaped version
    # finds something in the data, that is the one the model meant.
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


def preview(
    dataset: Dataset,
    *,
    instruction: str = "",
    pattern: str = "",
    flags: Sequence[str] = (),
    replacement: str | None = None,
    columns: Sequence[str] = (),
) -> Preview:
    """Show what a replacement would do, without changing the dataset."""
    plan = plan_replacement(
        dataset, instruction=instruction, pattern=pattern, flags=flags, replacement=replacement, columns=columns
    )
    frame = storage.load_version(dataset.id, dataset.current_version)
    outcome = regex_engine.replace_in_frame(
        frame,
        plan.compiled,
        plan.replacement or "",
        plan.columns,
        timeout=settings.REGEX_TIMEOUT_SECONDS,
        sample_limit=PREVIEW_SAMPLE_LIMIT,
    )
    samples = [
        {
            "row": change.row,
            "column": change.column,
            "before": change.before,
            "after": change.after if plan.replacement is not None else None,
            "spans": [list(span) for span in change.spans],
        }
        for change in outcome.samples
    ]
    return Preview(
        pattern=plan.pattern,
        flags=plan.flags,
        columns=plan.columns,
        replacement=plan.replacement,
        explanation=plan.explanation,
        source=plan.source,
        cached=plan.cached,
        stats=outcome.stats(),
        samples=samples,
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
    plan = plan_replacement(
        dataset, instruction=instruction, pattern=pattern, flags=flags, replacement=replacement, columns=columns
    )
    if plan.replacement is None:
        raise exceptions.MissingReplacement()
    try:
        with transaction.atomic():
            locked = Dataset.objects.select_for_update().get(pk=dataset.pk)
            frame = storage.load_version(locked.id, locked.current_version)
            outcome = regex_engine.replace_in_frame(
                frame,
                plan.compiled,
                plan.replacement,
                plan.columns,
                timeout=settings.REGEX_TIMEOUT_SECONDS,
                sample_limit=0,
            )
            if outcome.cells_changed == 0:
                raise exceptions.NoChanges()
            version = locked.current_version + 1
            storage.save_version(locked.id, version, outcome.frame)
            Transformation.objects.create(
                dataset=locked,
                version=version,
                kind=Transformation.Kind.REGEX_REPLACE,
                instruction=instruction,
                params={
                    "pattern": plan.pattern,
                    "flags": plan.flags,
                    "replacement": plan.replacement,
                    "columns": plan.columns,
                },
                explanation=explanation or plan.explanation,
                source=source or plan.source,
                stats=outcome.stats(),
            )
            locked.current_version = version
            locked.save(update_fields=["current_version", "updated_at"])
    except IntegrityError as exc:
        raise exceptions.ConcurrentModification() from exc
    logger.info("Applied step %d to dataset %s (%d cells changed)", version, locked.id, outcome.cells_changed)
    return locked


def undo(dataset: Dataset) -> Dataset:
    """Remove the latest step and go back to the previous version."""
    with transaction.atomic():
        locked = Dataset.objects.select_for_update().get(pk=dataset.pk)
        if locked.current_version == 0:
            raise exceptions.NothingToUndo()
        removed = locked.current_version
        locked.transformations.filter(version=removed).delete()
        locked.current_version = removed - 1
        locked.save(update_fields=["current_version", "updated_at"])
        transaction.on_commit(lambda: storage.delete_version(locked.id, removed))
    return locked


# --- Export -------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportFile:
    content: bytes
    filename: str
    content_type: str


def export(dataset: Dataset, file_type: str) -> ExportFile:
    frame = storage.load_version(dataset.id, dataset.current_version)
    stem = PurePath(dataset.name).stem or "dataset"
    if file_type == "xlsx":
        if len(frame) > EXCEL_MAX_DATA_ROWS:
            raise exceptions.ExportNotPossible(
                f"Excel sheets hold at most {EXCEL_MAX_DATA_ROWS:,} rows; download a CSV instead."
            )
        buffer = io.BytesIO()
        frame.to_excel(buffer, index=False, engine="openpyxl")
        return ExportFile(
            buffer.getvalue(),
            f"{stem}_processed.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    # The byte-order mark makes Excel recognise UTF-8 when the CSV is double-clicked.
    return ExportFile(frame.to_csv(index=False).encode("utf-8-sig"), f"{stem}_processed.csv", "text/csv")
