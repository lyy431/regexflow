import json
import re

import pytest

from llm import (
    ColumnInfo,
    FindReplaceTask,
    Generator,
    InvalidSuggestion,
    NormalizeTask,
    ReformatTask,
    RegexSuggestion,
    RequestNotPossible,
    parse_reply,
)
from llm.testing import FakeProvider, mapping_answer, reformat_answer, suggestion

COLUMNS = [ColumnInfo("Joined", "date"), ColumnInfo("Name", "text")]
DATE_PATTERN = r"\b(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})\b"
STATES = [("NSW", 5), ("Victoria", 4), ("vic", 2), ("New South Wales", 1)]


class TestFindReplaceTask:
    def test_normalises_flags_and_word_boundaries(self):
        reply = json.dumps(suggestion("\bcat\b", flags=["i", "re.MULTILINE"]))
        answer = FindReplaceTask("cats", COLUMNS).check(parse_reply(reply, RegexSuggestion))

        assert answer.pattern == r"\bcat\b"
        assert answer.flags == ["IGNORECASE", "MULTILINE"]

    def test_asks_for_a_fix_when_a_column_does_not_exist(self):
        provider = FakeProvider(suggestion("cat", target_columns=["Mail"]), suggestion("cat"))
        result = Generator([provider]).run(FindReplaceTask("cats", COLUMNS))

        assert result.suggestion.target_columns == []
        assert "Unknown column(s) 'Mail'" in provider.calls[1][-1]["content"]

    def test_requires_an_instruction(self):
        with pytest.raises(ValueError):
            FindReplaceTask("   ", COLUMNS)


class TestReformatTask:
    def test_returns_a_pattern_with_its_template(self):
        provider = FakeProvider(reformat_answer(DATE_PATTERN, r"\g<year>-\g<month>-\g<day>", target_columns=["joined"]))
        result = Generator([provider]).run(ReformatTask("dates to ISO", COLUMNS))

        assert result.suggestion.template == r"\g<year>-\g<month>-\g<day>"
        assert result.suggestion.target_columns == ["Joined"]

    def test_asks_for_a_template_that_fits_the_pattern(self):
        def groups_exist(answer):
            names = set(re.compile(answer.pattern).groupindex)
            if not set(re.findall(r"\\g<(\w+)>", answer.template)) <= names:
                raise InvalidSuggestion("The template refers to a group the pattern does not have.")

        provider = FakeProvider(
            reformat_answer(DATE_PATTERN, r"\g<yyyy>-\g<month>-\g<day>"),
            reformat_answer(DATE_PATTERN, r"\g<year>-\g<month>-\g<day>"),
        )
        result = Generator([provider]).run(ReformatTask("dates to ISO", COLUMNS, validate=groups_exist))

        assert result.suggestion.template == r"\g<year>-\g<month>-\g<day>"
        assert "group the pattern does not have" in provider.calls[1][-1]["content"]

    def test_asks_for_a_fix_when_the_template_is_missing(self):
        provider = FakeProvider(reformat_answer(DATE_PATTERN, ""), reformat_answer(DATE_PATTERN, r"\g<year>"))
        assert Generator([provider]).run(ReformatTask("years only", COLUMNS)).suggestion.template == r"\g<year>"

    def test_passes_on_the_models_refusal(self):
        provider = FakeProvider(reformat_answer("", "", error="Translating is not a rewrite."))
        with pytest.raises(RequestNotPossible, match="Translating"):
            Generator([provider]).run(ReformatTask("translate to French", COLUMNS))


class TestNormalizeTask:
    def test_shows_the_model_the_values_and_the_goal(self):
        provider = FakeProvider(mapping_answer({"Victoria": "VIC"}))
        Generator([provider]).run(NormalizeTask("State", STATES, "official abbreviations"))

        request = provider.calls[0][-1]["content"]
        assert 'Column: "State"' in request
        assert "Goal: official abbreviations" in request
        assert '{"value": "Victoria", "count": 4}' in request

    def test_explains_when_there_is_no_goal(self):
        provider = FakeProvider(mapping_answer({}))
        Generator([provider]).run(NormalizeTask("State", STATES))
        assert "Goal: (none given" in provider.calls[0][-1]["content"]

    def test_drops_unchanged_and_repeated_entries(self):
        reply = json.dumps(
            {
                "mapping": [
                    {"from": "NSW", "to": "NSW"},
                    {"from": "vic", "to": " VIC "},
                    {"from": "vic", "to": "Victoria"},
                ],
                "explanation": "",
                "error": "",
            }
        )
        answer = NormalizeTask("State", STATES).check(parse_reply(reply, NormalizeTask.answer_model))

        assert [(item.from_, item.to) for item in answer.mapping] == [("vic", "VIC")]

    @pytest.mark.parametrize(
        ("bad_answer", "message"),
        [
            (mapping_answer({"Tasmania": "TAS"}), "not found: 'Tasmania'"),
            (mapping_answer({"vic": "  "}), "must be a clean value"),
        ],
    )
    def test_asks_for_a_fix_when_the_mapping_is_unusable(self, bad_answer, message):
        provider = FakeProvider(bad_answer, mapping_answer({"vic": "VIC"}))
        result = Generator([provider]).run(NormalizeTask("State", STATES))

        assert [(item.from_, item.to) for item in result.suggestion.mapping] == [("vic", "VIC")]
        assert message in provider.calls[1][-1]["content"]

    def test_cached_answers_depend_on_the_values(self):
        assert NormalizeTask("State", STATES).cache_key_data() != NormalizeTask("State", STATES[:2]).cache_key_data()
