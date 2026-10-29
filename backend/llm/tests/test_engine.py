import re

import pytest
from django.core.cache import cache

from llm import (
    AllProvidersFailed,
    ColumnInfo,
    FindReplaceTask,
    Generator,
    InvalidSuggestion,
    NoProviderConfigured,
    ProviderUnavailable,
    RegexSuggestion,
    RequestNotPossible,
    parse_reply,
)
from llm.testing import FakeProvider, suggestion

COLUMNS = [ColumnInfo("ID", "numeric"), ColumnInfo("Email", "text")]
EMAIL = r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"


def compiles(candidate) -> None:
    try:
        re.compile(candidate.pattern)
    except re.error as exc:
        raise InvalidSuggestion(f"Invalid regular expression: {exc}.") from exc


def task(instruction="emails", validate=None):
    return FindReplaceTask(instruction, COLUMNS, validate=validate)


class TestParseReply:
    def test_reads_json_inside_a_markdown_fence(self):
        parsed = parse_reply(r'```json {"pattern": "\\d+", "explanation": "Digits."} ```', RegexSuggestion)
        assert parsed.pattern == r"\d+"

    def test_repairs_regex_backslashes_that_were_not_escaped(self):
        assert parse_reply(r'{"pattern": "\d{3}\s\w+"}', RegexSuggestion).pattern == r"\d{3}\s\w+"

    def test_repair_keeps_backslashes_that_were_escaped(self):
        assert parse_reply(r'{"pattern": "\\d+\s"}', RegexSuggestion).pattern == r"\d+\s"

    def test_treats_nulls_as_defaults(self):
        parsed = parse_reply('{"pattern": "a", "replacement": null, "flags": null}', RegexSuggestion)
        assert (parsed.replacement, parsed.flags) == ("", [])

    @pytest.mark.parametrize("reply", ["no json here", '{"pattern": 5}', "[1, 2]", '{"pattern": "unterminated}'])
    def test_rejects_unusable_replies(self, reply):
        with pytest.raises(InvalidSuggestion):
            parse_reply(reply, RegexSuggestion)


class TestGenerator:
    def test_returns_the_first_providers_answer(self):
        provider = FakeProvider(suggestion(EMAIL, target_columns=["email"]))
        result = Generator([provider]).run(task("find   emails"))

        assert result.suggestion.pattern == EMAIL
        assert result.suggestion.target_columns == ["Email"]  # matched case-insensitively
        assert (result.provider, result.cached) == ("fake:model", False)
        request = provider.calls[0][-1]["content"]
        assert '"name": "Email"' in request
        assert "Request: find emails" in request  # whitespace is normalised

    def test_asks_the_model_to_fix_an_invalid_pattern(self):
        provider = FakeProvider(suggestion("[unclosed"), suggestion(EMAIL))
        result = Generator([provider]).run(task(validate=compiles))

        assert result.suggestion.pattern == EMAIL
        assert len(provider.calls) == 2
        assert "could not be used" in provider.calls[1][-1]["content"]

    def test_falls_back_when_a_provider_keeps_answering_badly(self):
        stubborn = FakeProvider(suggestion("[bad"), suggestion("[still bad"), label="first:model")
        backup = FakeProvider(suggestion(EMAIL), label="second:model")

        assert Generator([stubborn, backup]).run(task(validate=compiles)).provider == "second:model"

    def test_falls_back_when_a_provider_is_unavailable(self):
        down = FakeProvider(ProviderUnavailable("rate-limited"), label="first:model")
        backup = FakeProvider(suggestion(EMAIL), label="second:model")

        assert Generator([down, backup]).run(task()).provider == "second:model"

    def test_reports_every_failure_when_all_providers_fail(self):
        first = FakeProvider(ProviderUnavailable("timed out"), label="first:model")
        second = FakeProvider("not json", "still not json", label="second:model")

        with pytest.raises(AllProvidersFailed) as error:
            Generator([first, second]).run(task())
        assert [f.split(":")[0] for f in error.value.failures] == ["first", "second"]

    def test_stops_when_the_model_says_the_request_is_not_possible(self):
        first = FakeProvider(suggestion("", error="Sorting is not a find-and-replace."))
        second = FakeProvider(suggestion(EMAIL))

        with pytest.raises(RequestNotPossible, match="Sorting"):
            Generator([first, second]).run(task("sort by email"))
        assert second.calls == []

    def test_caches_answers(self):
        provider = FakeProvider(suggestion(EMAIL))
        generator = Generator([provider], cache=cache)

        first = generator.run(task())
        second = generator.run(task())

        assert len(provider.calls) == 1
        assert (first.cached, second.cached) == (False, True)
        assert second.suggestion == first.suggestion

    def test_requires_a_provider(self):
        with pytest.raises(NoProviderConfigured):
            Generator([]).run(task())
