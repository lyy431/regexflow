"""On-disk storage of dataset contents: one Parquet file per version."""

import logging
import shutil
from pathlib import Path
from uuid import UUID

import pandas as pd
import pyarrow.parquet as pq
from django.conf import settings

from datasets.exceptions import DatasetDataMissing

logger = logging.getLogger(__name__)


def save_version(dataset_id: UUID, version: int, frame: pd.DataFrame) -> None:
    path = _version_path(dataset_id, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)  # atomic, so readers never see a half-written file


def load_version(dataset_id: UUID, version: int) -> pd.DataFrame:
    return pd.read_parquet(_existing_path(dataset_id, version))


def read_rows(dataset_id: UUID, version: int, offset: int, limit: int) -> list[list[str]]:
    """Return rows ``offset`` to ``offset + limit`` as lists of cell values."""
    table = pq.read_table(_existing_path(dataset_id, version)).slice(offset, limit)
    columns = [table.column(i).to_pylist() for i in range(table.num_columns)]
    return [list(row) for row in zip(*columns, strict=True)]


def delete_version(dataset_id: UUID, version: int) -> None:
    try:
        _version_path(dataset_id, version).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete version %s of dataset %s", version, dataset_id, exc_info=True)


def delete_dataset(dataset_id: UUID) -> None:
    shutil.rmtree(_dataset_dir(dataset_id), ignore_errors=True)


def _dataset_dir(dataset_id: UUID) -> Path:
    return Path(settings.MEDIA_ROOT) / "datasets" / str(dataset_id)


def _version_path(dataset_id: UUID, version: int) -> Path:
    return _dataset_dir(dataset_id) / f"v{version}.parquet"


def _existing_path(dataset_id: UUID, version: int) -> Path:
    path = _version_path(dataset_id, version)
    if not path.exists():
        raise DatasetDataMissing()
    return path
