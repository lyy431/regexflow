"""Infer a coarse kind for each column, so the UI and the LLM know which columns hold free text."""

import re
from collections.abc import Iterable
from enum import StrEnum
from itertools import islice

import pandas as pd


class ColumnKind(StrEnum):
    TEXT = "text"
    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    DATE = "date"
    EMPTY = "empty"


# Replacements apply to these kinds unless the user names other columns.
TEXT_LIKE_KINDS = frozenset({ColumnKind.TEXT, ColumnKind.DATE})

_SAMPLE_SIZE = 500
_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
# Leading zeros mean an identifier (phone number, postcode, account number), not a quantity.
_CODE_WITH_LEADING_ZERO = re.compile(r"^0\d")
_BOOLEANS = frozenset({"true", "false", "yes", "no"})
_DATE = re.compile(r"^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})([ T]\d{1,2}:\d{2}(:\d{2})?)?$")


def infer_kind(values: Iterable[str]) -> ColumnKind:
    sample = list(islice((v.strip() for v in values if isinstance(v, str) and v.strip()), _SAMPLE_SIZE))
    if not sample:
        return ColumnKind.EMPTY
    if all(_NUMBER.match(v) for v in sample) and not any(_CODE_WITH_LEADING_ZERO.match(v) for v in sample):
        return ColumnKind.NUMERIC
    if all(v.lower() in _BOOLEANS for v in sample):
        return ColumnKind.BOOLEAN
    if all(_DATE.match(v) for v in sample):
        return ColumnKind.DATE
    return ColumnKind.TEXT


def profile_columns(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [{"name": name, "kind": infer_kind(frame[name]).value} for name in frame.columns]
