import uuid

from django.db import models


class Dataset(models.Model):
    """An uploaded table and its version history.

    Version 0 is the parsed upload; each applied transformation produces the
    next version. The cell data lives in Parquet files managed by
    ``datasets.services.storage``; this model keeps only metadata.
    """

    class FileFormat(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel workbook"
        XLS = "xls", "Excel 97-2003 workbook"

    # A random UUID doubles as the access token: the API has no accounts.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    file_format = models.CharField(max_length=8, choices=FileFormat.choices)
    row_count = models.PositiveIntegerField()
    columns = models.JSONField(help_text='Column profiles: [{"name": ..., "kind": ...}, ...]')
    current_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def column_names(self) -> list[str]:
        return [column["name"] for column in self.columns]


class Transformation(models.Model):
    """One applied step in a dataset's history."""

    class Kind(models.TextChoices):
        REGEX_REPLACE = "regex_replace", "Find and replace"
        REFORMAT = "reformat", "Standardise a format"
        NORMALIZE_VALUES = "normalize_values", "Normalise values"

    dataset = models.ForeignKey(Dataset, related_name="transformations", on_delete=models.CASCADE)
    version = models.PositiveIntegerField(help_text="The dataset version this step produced.")
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.REGEX_REPLACE)
    instruction = models.TextField(blank=True, help_text="The user's plain-English request, if any.")
    params = models.JSONField(help_text="What the step does, depending on its kind (pattern, template, mapping...).")
    explanation = models.TextField(blank=True)
    source = models.CharField(max_length=64, blank=True, help_text="LLM that wrote the pattern, or 'manual'.")
    stats = models.JSONField(default=dict, help_text="Match and change counts.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["version"]
        constraints = [models.UniqueConstraint(fields=["dataset", "version"], name="unique_dataset_version")]

    def __str__(self) -> str:
        return f"{self.dataset_id} v{self.version}"
