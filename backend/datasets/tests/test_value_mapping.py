import pandas as pd
import pytest

from datasets.exceptions import ColumnNotSuitable
from datasets.services import value_mapping

STATES = pd.DataFrame({"state": ["NSW", "vic", "Victoria", "NSW", "", "Victoria", "NSW"], "other": ["x"] * 7})


def test_lists_distinct_values_most_common_first():
    assert value_mapping.distinct_values(STATES, "state") == [("NSW", 3), ("Victoria", 2), ("vic", 1)]


def test_rejects_columns_with_too_many_values(monkeypatch):
    monkeypatch.setattr(value_mapping, "MAX_DISTINCT_VALUES", 2)
    with pytest.raises(ColumnNotSuitable, match="3 different values"):
        value_mapping.distinct_values(STATES, "state")


def test_rejects_free_text():
    frame = pd.DataFrame({"notes": ["x" * 201]})
    with pytest.raises(ColumnNotSuitable, match="free text"):
        value_mapping.distinct_values(frame, "notes")


def test_maps_whole_cell_values():
    outcome = value_mapping.map_values(STATES, "state", {"vic": "VIC", "Victoria": "VIC"}, sample_limit=1)

    assert outcome.frame["state"].tolist() == ["NSW", "VIC", "VIC", "NSW", "", "VIC", "NSW"]
    assert outcome.stats() == {
        "matches": 3,
        "cells_changed": 3,
        "rows_affected": 3,
        "matches_by_column": {"state": 3},
    }
    assert (outcome.samples[0].before, outcome.samples[0].after, outcome.samples[0].spans) == ("vic", "VIC", ((0, 3),))
    assert STATES.loc[1, "state"] == "vic"  # the input frame is left untouched
