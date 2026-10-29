import pandas as pd
import pytest

from datasets.exceptions import InvalidPattern, RegexTimeout
from datasets.services.regex_engine import (
    check_template,
    compile_pattern,
    finds_match,
    literal_template,
    replace_in_frame,
)

DATE = r"\b(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})\b"


def replace(frame, pattern, replacement, columns, flags=(), **options):
    """Replace with literal text, as find-and-replace does."""
    options.setdefault("timeout", 5)
    return replace_in_frame(frame, compile_pattern(pattern, flags), literal_template(replacement), columns, **options)


class TestCompilePattern:
    @pytest.mark.parametrize(
        ("pattern", "flags", "message"),
        [
            ("", (), "empty"),
            ("x" * 1001, (), "longer than"),
            ("[unclosed", (), "Invalid regular expression"),
            ("a", ("VERBOSE",), "Unsupported flag"),
            (r"\d*", (), "match empty text"),
            (r"\b", (), "match empty text"),
            (r"(?=a)", (), "match empty text"),
        ],
    )
    def test_rejects_unusable_patterns(self, pattern, flags, message):
        with pytest.raises(InvalidPattern, match=message):
            compile_pattern(pattern, flags)

    def test_allows_matching_whole_empty_cells(self):
        assert compile_pattern("^$").fullmatch("")

    def test_applies_flags(self):
        assert compile_pattern("hello", ["IGNORECASE"]).search("HELLO")


class TestReplaceInFrame:
    def test_replaces_matches_and_reports_what_changed(self):
        frame = pd.DataFrame({"a": ["cat cat", "dog", "cat"], "b": ["cat", "x", "y"]})

        outcome = replace(frame, r"\bcat\b", "pet", ["a", "b"])

        assert outcome.frame.to_dict("list") == {"a": ["pet pet", "dog", "pet"], "b": ["pet", "x", "y"]}
        assert outcome.stats() == {
            "matches": 4,
            "cells_changed": 3,
            "rows_affected": 2,
            "matches_by_column": {"a": 3, "b": 1},
        }
        assert frame.loc[0, "a"] == "cat cat"  # the input frame is left untouched

    def test_only_touches_the_requested_columns(self):
        frame = pd.DataFrame({"a": ["cat"], "b": ["cat"]})
        assert replace(frame, "cat", "pet", ["b"]).frame.values.tolist() == [["cat", "pet"]]

    def test_inserts_the_replacement_literally(self):
        frame = pd.DataFrame({"a": ["id 42"]})
        assert replace(frame, r"(\d+)", r"\1 \g<0> C:\temp", ["a"]).frame.loc[0, "a"] == r"id \1 \g<0> C:\temp"

    def test_can_fill_empty_cells(self):
        frame = pd.DataFrame({"a": ["", "x"]})
        assert replace(frame, "^$", "N/A", ["a"]).frame["a"].tolist() == ["N/A", "x"]

    def test_collects_samples_with_match_positions(self):
        frame = pd.DataFrame({"a": ["a1b22", "none", "3"]})

        outcome = replace(frame, r"\d+", "#", ["a"], sample_limit=1)

        assert len(outcome.samples) == 1
        sample = outcome.samples[0]
        assert (sample.row, sample.before, sample.after, sample.spans) == (0, "a1b22", "a#b#", ((1, 2), (3, 5)))

    def test_stops_patterns_that_backtrack_for_too_long(self):
        frame = pd.DataFrame({"a": ["a" * 40 + "!"]})
        with pytest.raises(RegexTimeout):
            replace(frame, r"(a|aa)+$", "x", ["a"], timeout=0.05)


class TestTemplates:
    def test_rearranges_named_groups(self):
        frame = pd.DataFrame({"a": ["31/01/2024", "2024-02-01", "joined 05/03/2024"]})

        outcome = replace_in_frame(frame, compile_pattern(DATE), r"\g<year>-\g<month>-\g<day>", ["a"], timeout=5)

        assert outcome.frame["a"].tolist() == ["2024-01-31", "2024-02-01", "joined 2024-03-05"]
        assert outcome.cells_changed == 2

    @pytest.mark.parametrize("template", [r"\g<year>-\g<month>", r"\g<0>!", r"\1/\3", r"a\\b", r"line\nbreak"])
    def test_accepts_templates_that_fit_the_pattern(self, template):
        check_template(compile_pattern(DATE), template)

    @pytest.mark.parametrize(
        ("template", "message"),
        [
            ("", "empty"),
            (r"\g<yyyy>", "no such group"),
            (r"\4", "has 3 group"),
            (r"\q", "stray backslash"),
            ("ends with \\", "stray backslash"),
        ],
    )
    def test_rejects_templates_that_do_not(self, template, message):
        with pytest.raises(InvalidPattern, match=message):
            check_template(compile_pattern(DATE), template)


class TestFindsMatch:
    def test_searches_only_the_text_cells_of_the_requested_columns(self):
        frame = pd.DataFrame({"a": ["dog", None], "b": ["x", "hot dog"]})

        assert finds_match(frame, compile_pattern("dog"), ["b"], timeout=5)
        assert not finds_match(frame, compile_pattern("cat"), ["a", "b"], timeout=5)

    def test_stops_patterns_that_backtrack_for_too_long(self):
        frame = pd.DataFrame({"a": ["a" * 40 + "!"]})
        with pytest.raises(RegexTimeout):
            finds_match(frame, compile_pattern(r"(a|aa)+$"), ["a"], timeout=0.05)
