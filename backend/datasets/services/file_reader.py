"""Parse uploaded CSV and Excel files into DataFrames of strings.

Every cell is read as text so values such as phone numbers, postcodes and IDs
keep their leading zeros and exact formatting; regexes work on text anyway.
"""

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO

import pandas as pd
from charset_normalizer import from_bytes

from datasets.exceptions import FileParseError, UnsupportedFileType

logger = logging.getLogger(__name__)

FORMATS_BY_EXTENSION = {".csv": "csv", ".tsv": "csv", ".xlsx": "xlsx", ".xlsm": "xlsx", ".xls": "xls"}
_SNIFF_SAMPLE_CHARS = 64_000
_ENCODING_SAMPLE_BYTES = 1_000_000


@dataclass(frozen=True)
class ParsedTable:
    frame: pd.DataFrame
    file_format: str


def detect_format(filename: str) -> str:
    extension = PurePath(filename).suffix.lower()
    try:
        return FORMATS_BY_EXTENSION[extension]
    except KeyError:
        raise UnsupportedFileType(
            f"Unsupported file type '{extension or filename}'. "
            "Please upload a CSV or Excel file (.csv, .tsv, .xlsx, .xls)."
        ) from None


def read_table(fileobj: BinaryIO, filename: str) -> ParsedTable:
    file_format = detect_format(filename)
    raw = fileobj.read()
    if not raw:
        raise FileParseError("The file is empty.")
    frame = _read_csv(raw) if file_format == "csv" else _read_excel(raw, file_format)
    return ParsedTable(_normalise(frame), file_format)


def _read_csv(raw: bytes) -> pd.DataFrame:
    text = _decode(raw)
    try:
        return pd.read_csv(
            io.StringIO(text), sep=_sniff_delimiter(text), dtype=str, keep_default_na=False, na_filter=False
        )
    except pd.errors.EmptyDataError:
        raise FileParseError("The file has no columns to read.") from None
    except pd.errors.ParserError as exc:
        reason = str(exc).strip().splitlines()[-1] if str(exc).strip() else "malformed rows"
        raise FileParseError(f"The CSV file could not be parsed: {reason}") from exc


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    guess = from_bytes(raw[:_ENCODING_SAMPLE_BYTES]).best()
    if guess is not None:
        try:
            return raw.decode(guess.encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode("latin-1")  # never fails: every byte maps to a character


def _sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:_SNIFF_SAMPLE_CHARS], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _read_excel(raw: bytes, file_format: str) -> pd.DataFrame:
    engine = "openpyxl" if file_format == "xlsx" else "xlrd"
    try:
        return pd.read_excel(
            io.BytesIO(raw), sheet_name=0, dtype=str, engine=engine, keep_default_na=False, na_filter=False
        )
    except Exception as exc:  # the Excel readers raise many unrelated exception types
        logger.info("Could not read an uploaded %s workbook", file_format, exc_info=True)
        raise FileParseError(
            "The Excel file could not be read. Make sure it is a valid workbook and not password-protected."
        ) from exc


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.shape[1] == 0:
        raise FileParseError("The file has no columns.")
    frame.columns = _clean_column_names(frame.columns)
    frame = frame.loc[~(frame == "").all(axis=1)].reset_index(drop=True)  # drop fully blank rows
    if frame.empty:
        raise FileParseError("The file has a header row but no data rows.")
    return frame


def _clean_column_names(columns) -> list[str]:
    cleaned: list[str] = []
    for position, column in enumerate(columns, start=1):
        name = str(column).strip()
        if not name or name.startswith("Unnamed:"):
            name = f"Column {position}"
        unique, suffix = name, 2
        while unique in cleaned:
            unique, suffix = f"{name} ({suffix})", suffix + 1
        cleaned.append(unique)
    return cleaned
