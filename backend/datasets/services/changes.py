"""The result of transforming a table: the new frame, counts, and a few example changes."""

from dataclasses import dataclass, field

import pandas as pd


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
