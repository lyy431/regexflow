"""End-to-end tests of the HTTP API, with the LLM replaced by scripted fakes."""

import io
from datetime import timedelta

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from datasets.models import Dataset
from datasets.services import generation, operations, storage
from llm import RegexGenerator
from llm.testing import FakeProvider, suggestion

pytestmark = pytest.mark.django_db

# The example scenario from the assignment brief.
PEOPLE_CSV = (
    "ID,Name,Email\n"
    "1,John Doe,john.doe@example.com\n"
    "2,Jane Smith,jane_smith@domain.com\n"
    "3,Alice Brown,alice.brown@website.org\n"
)
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"
EMAIL_SUGGESTION = suggestion(
    EMAIL_PATTERN, target_columns=["Email"], replacement_specified=True, replacement="REDACTED"
)
INSTRUCTION = "Find email addresses in the Email column and replace them with 'REDACTED'."


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def fake_llm(monkeypatch):
    """Answer LLM requests with the given scripted replies."""

    def install(*replies):
        provider = FakeProvider(*replies)
        monkeypatch.setattr(generation, "get_regex_generator", lambda: RegexGenerator([provider]))
        return provider

    return install


def upload(api, content: str | bytes = PEOPLE_CSV, name: str = "people.csv"):
    data = content.encode() if isinstance(content, str) else content
    return api.post("/api/datasets/", {"file": SimpleUploadedFile(name, data)}, format="multipart")


@pytest.fixture
def dataset_id(api):
    response = upload(api)
    assert response.status_code == 201, response.data
    return response.data["id"]


def url(dataset_id, suffix=""):
    return f"/api/datasets/{dataset_id}/{suffix}"


def error_code(response):
    return response.json()["error"]["code"]


class TestUpload:
    def test_returns_the_dataset_with_column_kinds(self, api):
        response = upload(api)

        assert response.status_code == 201
        assert response.data["row_count"] == 3
        assert response.data["columns"] == [
            {"name": "ID", "kind": "numeric"},
            {"name": "Name", "kind": "text"},
            {"name": "Email", "kind": "text"},
        ]
        assert response.data["current_version"] == 0

    def test_rejects_unsupported_files(self, api):
        response = upload(api, "{}", "data.json")
        assert (response.status_code, error_code(response)) == (400, "unsupported_file_type")

    def test_rejects_empty_files(self, api):
        response = upload(api, b"")
        assert (response.status_code, error_code(response)) == (400, "validation_error")

    def test_rejects_files_over_the_size_limit(self, api, settings):
        settings.MAX_UPLOAD_SIZE_MB = 0
        response = upload(api)
        assert (response.status_code, error_code(response)) == (413, "file_too_large")

    def test_reports_unparseable_files(self, api):
        response = upload(api, b"\x00garbage", "data.xlsx")
        assert (response.status_code, error_code(response)) == (400, "file_parse_error")


class TestRows:
    def test_pages_through_the_data(self, api):
        csv = "n\n" + "".join(f"{i}\n" for i in range(120))
        dataset_id = upload(api, csv).data["id"]

        page = api.get(url(dataset_id, "rows/"), {"page": 3, "page_size": 50}).data
        beyond = api.get(url(dataset_id, "rows/"), {"page": 99, "page_size": 50}).data

        assert (page["total_rows"], page["total_pages"], len(page["rows"])) == (120, 3, 20)
        assert page["rows"][0] == ["100"]
        assert page["changed_cells"] is None
        assert beyond["page"] == 3

    def test_validates_query_parameters(self, api, dataset_id):
        response = api.get(url(dataset_id, "rows/"), {"page_size": 10_000})
        assert (response.status_code, error_code(response)) == (400, "validation_error")


class TestBriefExample:
    def test_redacts_emails_from_a_plain_english_instruction(self, api, dataset_id, fake_llm):
        fake_llm(EMAIL_SUGGESTION)

        preview = api.post(url(dataset_id, "preview/"), {"instruction": INSTRUCTION}, format="json")
        assert preview.status_code == 200, preview.data
        assert preview.data["pattern"] == EMAIL_PATTERN
        assert preview.data["columns"] == ["Email"]
        assert preview.data["replacement"] == "REDACTED"
        assert preview.data["source"] == "fake:model"
        assert preview.data["stats"]["matches"] == 3
        assert preview.data["samples"][0] == {
            "row": 0,
            "column": "Email",
            "before": "john.doe@example.com",
            "after": "REDACTED",
            "spans": [[0, 20]],
        }

        applied = api.post(
            url(dataset_id, "transformations/"),
            {key: preview.data[key] for key in ("pattern", "flags", "replacement", "columns", "explanation", "source")}
            | {"instruction": INSTRUCTION},
            format="json",
        )
        assert applied.status_code == 201, applied.data
        assert applied.data["current_version"] == 1
        assert applied.data["transformations"][0]["source"] == "fake:model"

        rows = api.get(url(dataset_id, "rows/")).data
        assert rows["rows"] == [
            ["1", "John Doe", "REDACTED"],
            ["2", "Jane Smith", "REDACTED"],
            ["3", "Alice Brown", "REDACTED"],
        ]
        assert rows["changed_cells"] == [[2], [2], [2]]


class TestPreview:
    def test_accepts_a_hand_written_pattern_without_the_llm(self, api, dataset_id):
        response = api.post(
            url(dataset_id, "preview/"),
            {"pattern": r"\bJ\w+", "replacement": "J.", "columns": ["name"]},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert (response.data["source"], response.data["columns"]) == ("manual", ["Name"])
        assert response.data["stats"]["cells_changed"] == 2
        assert Dataset.objects.get(pk=dataset_id).current_version == 0  # previews change nothing

    def test_leaves_the_replacement_open_when_nobody_specified_it(self, api, dataset_id, fake_llm):
        fake_llm(suggestion(EMAIL_PATTERN))

        response = api.post(url(dataset_id, "preview/"), {"instruction": "email addresses"}, format="json")

        assert response.data["replacement"] is None
        assert response.data["samples"][0]["after"] is None
        assert response.data["columns"] == ["Name", "Email"]  # every text column by default

    def test_columns_picked_in_the_ui_win_over_the_llm(self, api, dataset_id, fake_llm):
        fake_llm(EMAIL_SUGGESTION)
        response = api.post(
            url(dataset_id, "preview/"), {"instruction": INSTRUCTION, "columns": ["Name"]}, format="json"
        )
        assert response.data["columns"] == ["Name"]

    def test_undoes_backslashes_the_model_escaped_twice(self, api, dataset_id, fake_llm):
        fake_llm(suggestion(EMAIL_PATTERN.replace("\\", "\\\\"), target_columns=["Email"]))

        response = api.post(url(dataset_id, "preview/"), {"instruction": "email addresses"}, format="json")

        assert response.data["pattern"] == EMAIL_PATTERN
        assert response.data["stats"]["matches"] == 3

    def test_keeps_double_backslashes_that_match_the_data(self, api, fake_llm):
        dataset_id = upload(api, "Path\nC:\\Users\\jane\n").data["id"]
        fake_llm(suggestion(r"C:\\Users"))

        response = api.post(url(dataset_id, "preview/"), {"instruction": "the Windows users folder"}, format="json")

        assert response.data["pattern"] == r"C:\\Users"
        assert response.data["stats"]["matches"] == 1

    def test_needs_an_instruction_or_a_pattern(self, api, dataset_id):
        response = api.post(url(dataset_id, "preview/"), {"instruction": "  "}, format="json")
        assert (response.status_code, error_code(response)) == (400, "validation_error")
        assert "plain English" in response.json()["error"]["message"]

    @pytest.mark.parametrize(
        ("payload", "status", "code"),
        [
            ({"pattern": "[unclosed"}, 400, "invalid_pattern"),
            ({"pattern": "a", "columns": ["Phone"]}, 400, "column_not_found"),
            ({"instruction": "emails"}, 503, "llm_not_configured"),  # no fake LLM installed
        ],
    )
    def test_reports_problems(self, api, dataset_id, payload, status, code):
        response = api.post(url(dataset_id, "preview/"), payload, format="json")
        assert (response.status_code, error_code(response)) == (status, code)

    def test_reports_requests_that_are_not_find_and_replace(self, api, dataset_id, fake_llm):
        fake_llm(suggestion("", error="Sorting rows is not a find-and-replace."))
        response = api.post(url(dataset_id, "preview/"), {"instruction": "sort by name"}, format="json")
        assert (response.status_code, error_code(response)) == (422, "pattern_not_expressible")


class TestApplyAndUndo:
    def test_applies_an_instruction_in_one_request(self, api, dataset_id, fake_llm):
        fake_llm(EMAIL_SUGGESTION)

        response = api.post(url(dataset_id, "transformations/"), {"instruction": INSTRUCTION}, format="json")

        assert response.status_code == 201, response.data
        step = response.data["transformations"][0]
        assert step["params"] == {
            "pattern": EMAIL_PATTERN,
            "flags": [],
            "replacement": "REDACTED",
            "columns": ["Email"],
        }
        assert step["stats"]["cells_changed"] == 3

    def test_needs_a_replacement(self, api, dataset_id, fake_llm):
        fake_llm(suggestion(EMAIL_PATTERN))
        response = api.post(url(dataset_id, "transformations/"), {"instruction": "emails"}, format="json")
        assert (response.status_code, error_code(response)) == (400, "missing_replacement")

    def test_refuses_steps_that_change_nothing(self, api, dataset_id):
        response = api.post(url(dataset_id, "transformations/"), {"pattern": "zzz", "replacement": "y"}, format="json")
        assert (response.status_code, error_code(response)) == (422, "no_changes")
        assert Dataset.objects.get(pk=dataset_id).current_version == 0

    def test_undo_restores_the_previous_version(self, api, dataset_id):
        api.post(url(dataset_id, "transformations/"), {"pattern": "Doe", "replacement": "Roe"}, format="json")

        undone = api.post(url(dataset_id, "transformations/undo/"))
        again = api.post(url(dataset_id, "transformations/undo/"))

        assert (undone.status_code, undone.data["current_version"], undone.data["transformations"]) == (200, 0, [])
        assert api.get(url(dataset_id, "rows/")).data["rows"][0][1] == "John Doe"
        assert (again.status_code, error_code(again)) == (409, "nothing_to_undo")


class TestExportAndLifecycle:
    def test_exports_the_current_version(self, api, dataset_id):
        api.post(url(dataset_id, "transformations/"), {"pattern": "Doe", "replacement": "Roe"}, format="json")

        csv = api.get(url(dataset_id, "export/"))
        xlsx = api.get(url(dataset_id, "export/"), {"file_type": "xlsx"})

        assert 'filename="people_processed.csv"' in csv["Content-Disposition"]
        assert "John Roe" in b"".join(csv.streaming_content).decode("utf-8-sig")
        sheet = openpyxl.load_workbook(io.BytesIO(b"".join(xlsx.streaming_content))).active
        assert sheet["B2"].value == "John Roe"

    def test_delete_removes_the_dataset(self, api, dataset_id):
        assert api.delete(url(dataset_id)).status_code == 204
        response = api.get(url(dataset_id))
        assert (response.status_code, error_code(response)) == (404, "dataset_not_found")

    def test_reports_data_files_that_disappeared(self, api, dataset_id):
        storage.delete_dataset(Dataset.objects.get(pk=dataset_id).id)
        response = api.get(url(dataset_id, "rows/"))
        assert (response.status_code, error_code(response)) == (410, "dataset_expired")

    def test_purges_idle_datasets(self, api, dataset_id, settings):
        settings.DATASET_TTL_HOURS = 1
        Dataset.objects.filter(pk=dataset_id).update(updated_at=timezone.now() - timedelta(hours=2))

        assert operations.purge_expired() == 1
        assert not Dataset.objects.filter(pk=dataset_id).exists()


def test_health_reports_limits_and_llm_providers(api, settings):
    settings.MAX_UPLOAD_SIZE_MB = 20
    assert api.get("/api/health/").json() == {
        "status": "ok",
        "llm_providers": [],
        "max_upload_size_mb": 20,
        "dataset_ttl_hours": settings.DATASET_TTL_HOURS,
    }


def test_unknown_api_paths_return_json(api):
    response = api.get("/api/nope/")
    assert (response.status_code, error_code(response)) == (404, "not_found")
