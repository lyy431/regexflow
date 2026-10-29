"""Dataset use cases other than the steps themselves: upload, browse, undo, export and cleanup.

The steps (find and replace, reformat, normalise) live in ``datasets.services.steps``.
"""

import io
import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePath

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from datasets import exceptions
from datasets.models import Dataset
from datasets.services import column_profile, storage
from datasets.services.file_reader import read_table

logger = logging.getLogger(__name__)

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


# --- Undo -------------------------------------------------------------------------


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
