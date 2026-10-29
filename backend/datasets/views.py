"""HTTP API for datasets.

Views stay thin: they validate input with serializers and delegate the work to
``datasets.services.operations`` and the step modules in ``datasets.services.steps``.
"""

import dataclasses
import io

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from datasets import exceptions
from datasets.models import Dataset, Transformation
from datasets.serializers import (
    DatasetSerializer,
    DatasetUploadSerializer,
    ExportQuerySerializer,
    FindReplaceApplySerializer,
    FindReplaceRequestSerializer,
    NormalizeApplySerializer,
    NormalizeRequestSerializer,
    ReformatApplySerializer,
    ReformatRequestSerializer,
    RowsQuerySerializer,
    StepKindSerializer,
)
from datasets.services import generation, operations, steps
from datasets.throttling import LLMRateThrottle, UploadRateThrottle

# For each kind of step: the serializer of a preview request and of an apply request.
STEP_SERIALIZERS: dict[str, tuple[type[serializers.Serializer], type[serializers.Serializer]]] = {
    Transformation.Kind.REGEX_REPLACE: (FindReplaceRequestSerializer, FindReplaceApplySerializer),
    Transformation.Kind.REFORMAT: (ReformatRequestSerializer, ReformatApplySerializer),
    Transformation.Kind.NORMALIZE_VALUES: (NormalizeRequestSerializer, NormalizeApplySerializer),
}


@api_view(["GET"])
def health(request):
    """Liveness check that also tells the frontend about limits and the configured LLMs."""
    return Response(
        {
            "status": "ok",
            "llm_providers": generation.configured_providers(),
            "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            "dataset_ttl_hours": settings.DATASET_TTL_HOURS,
        }
    )


class DatasetViewSet(mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Upload a table, page through it, and preview / apply / undo steps."""

    queryset = Dataset.objects.prefetch_related("transformations")
    serializer_class = DatasetSerializer

    def get_throttles(self):
        if self.action == "create":
            return [UploadRateThrottle()]
        if self.action in {"preview", "apply"}:
            return [LLMRateThrottle()]
        return super().get_throttles()

    def get_object(self) -> Dataset:
        try:
            return super().get_object()
        except Http404:
            raise exceptions.DatasetNotFound() from None

    def create(self, request):
        upload = DatasetUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        dataset = operations.create_dataset(upload.validated_data["file"])
        return Response(DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Dataset) -> None:
        operations.delete_dataset(instance)

    @action(detail=True, methods=["get"])
    def rows(self, request, pk=None):
        query = RowsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(operations.get_page(self.get_object(), **query.validated_data))

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        kind, payload = self._step_request(request.data, applying=False)
        result = steps.BY_KIND[kind].preview(self.get_object(), **payload)
        return Response(dataclasses.asdict(result))

    @action(detail=True, methods=["post"], url_path="transformations")
    def apply(self, request, pk=None):
        kind, payload = self._step_request(request.data, applying=True)
        dataset = steps.BY_KIND[kind].apply(self.get_object(), **payload)
        return Response(DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="transformations/undo")
    def undo(self, request, pk=None):
        dataset = operations.undo(self.get_object())
        return Response(DatasetSerializer(dataset).data)

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        query = ExportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        exported = operations.export(self.get_object(), query.validated_data["file_type"])
        return FileResponse(
            io.BytesIO(exported.content),
            as_attachment=True,
            filename=exported.filename,
            content_type=exported.content_type,
        )

    @staticmethod
    def _step_request(data, *, applying: bool) -> tuple[str, dict]:
        """Validate a step request with the serializer for its ``kind``."""
        kind_serializer = StepKindSerializer(data=data)
        kind_serializer.is_valid(raise_exception=True)
        kind = kind_serializer.validated_data["kind"]
        preview_serializer, apply_serializer = STEP_SERIALIZERS[kind]
        payload = (apply_serializer if applying else preview_serializer)(data=data)
        payload.is_valid(raise_exception=True)
        return kind, payload.validated_data
