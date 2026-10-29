from django.conf import settings
from rest_framework import serializers

from datasets.exceptions import FileTooLarge
from datasets.models import Dataset, Transformation
from datasets.services.file_reader import detect_format
from datasets.services.regex_engine import MAX_PATTERN_LENGTH, MAX_TEMPLATE_LENGTH, SUPPORTED_FLAGS
from datasets.services.value_mapping import MAX_DISTINCT_VALUES, MAX_VALUE_LENGTH

# --- Responses ----------------------------------------------------------------------


class TransformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transformation
        fields = ["id", "version", "kind", "instruction", "params", "explanation", "source", "stats", "created_at"]


class DatasetSerializer(serializers.ModelSerializer):
    transformations = TransformationSerializer(many=True, read_only=True)

    class Meta:
        model = Dataset
        fields = [
            "id",
            "name",
            "file_format",
            "row_count",
            "columns",
            "current_version",
            "transformations",
            "created_at",
            "updated_at",
        ]


# --- Requests -----------------------------------------------------------------------


class DatasetUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=False)

    def validate_file(self, upload):
        detect_format(upload.name)  # raises UnsupportedFileType
        limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if upload.size > limit:
            raise FileTooLarge(
                f"The file is {upload.size / 1024 / 1024:.1f} MB; the limit is {settings.MAX_UPLOAD_SIZE_MB} MB."
            )
        return upload


class RowsQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=500, default=50)


class ExportQuerySerializer(serializers.Serializer):
    # Not called "format": DRF reserves that query parameter for content negotiation.
    file_type = serializers.ChoiceField(choices=["csv", "xlsx"], default="csv")


class StepKindSerializer(serializers.Serializer):
    """Picks the kind of step a preview or apply request is about."""

    kind = serializers.ChoiceField(choices=Transformation.Kind.choices, default=Transformation.Kind.REGEX_REPLACE)


class _StepRecordFields(serializers.Serializer):
    """What the client showed in the preview, recorded with an applied step."""

    explanation = serializers.CharField(max_length=1000, default="", allow_blank=True)
    source = serializers.CharField(max_length=64, default="", allow_blank=True)


def _flags_field():
    return serializers.ListField(child=serializers.ChoiceField(choices=sorted(SUPPORTED_FLAGS)), default=list)


def _columns_field():
    return serializers.ListField(child=serializers.CharField(max_length=255), default=list, max_length=500)


class FindReplaceRequestSerializer(serializers.Serializer):
    """Either a plain-English ``instruction`` (sent to the LLM) or an explicit regex ``pattern``."""

    instruction = serializers.CharField(max_length=1000, default="", allow_blank=True)
    pattern = serializers.CharField(max_length=MAX_PATTERN_LENGTH, default="", allow_blank=True, trim_whitespace=False)
    flags = _flags_field()
    # null means "not specified": take it from the instruction. "" removes the matches.
    replacement = serializers.CharField(
        max_length=1000, default=None, allow_null=True, allow_blank=True, trim_whitespace=False
    )
    columns = _columns_field()

    def validate(self, attrs):
        if not attrs["instruction"].strip() and not attrs["pattern"]:
            raise serializers.ValidationError("Describe what to find in plain English, or enter a regular expression.")
        return attrs


class FindReplaceApplySerializer(_StepRecordFields, FindReplaceRequestSerializer):
    pass


class ReformatRequestSerializer(serializers.Serializer):
    """Either a plain-English ``instruction`` or an explicit ``pattern`` with its ``template``."""

    instruction = serializers.CharField(max_length=1000, default="", allow_blank=True)
    pattern = serializers.CharField(max_length=MAX_PATTERN_LENGTH, default="", allow_blank=True, trim_whitespace=False)
    flags = _flags_field()
    template = serializers.CharField(
        max_length=MAX_TEMPLATE_LENGTH, default="", allow_blank=True, trim_whitespace=False
    )
    columns = _columns_field()

    def validate(self, attrs):
        if attrs["pattern"]:
            if not attrs["template"]:
                raise serializers.ValidationError("Enter the template that rewrites the matched text.")
        elif not attrs["instruction"].strip():
            raise serializers.ValidationError(
                "Describe the format change in plain English, or enter a pattern and a template."
            )
        return attrs


class ReformatApplySerializer(_StepRecordFields, ReformatRequestSerializer):
    pass


class NormalizeRequestSerializer(serializers.Serializer):
    """A ``column`` and an optional goal. A ``mapping`` (old value -> new value) skips the LLM."""

    column = serializers.CharField(max_length=255)
    instruction = serializers.CharField(max_length=1000, default="", allow_blank=True)
    mapping = serializers.DictField(
        child=serializers.CharField(max_length=MAX_VALUE_LENGTH, trim_whitespace=False),
        default=None,
        allow_null=True,
    )

    def validate_mapping(self, mapping):
        if mapping is not None and len(mapping) > MAX_DISTINCT_VALUES:
            raise serializers.ValidationError(f"A mapping can have at most {MAX_DISTINCT_VALUES} entries.")
        return mapping


class NormalizeApplySerializer(_StepRecordFields, NormalizeRequestSerializer):
    pass
