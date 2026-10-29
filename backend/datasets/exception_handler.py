"""Render every API error as ``{"error": {"code": ..., "message": ..., "details": ...}}``."""

import logging
import math

from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from datasets.exceptions import AppError
from llm import AllProvidersFailed, NoProviderConfigured, RequestNotPossible

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    if isinstance(exc, AppError):
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)
    if isinstance(exc, RequestNotPossible):
        return _error_response(422, "request_not_possible", f"This kind of step can't do that: {exc}")
    if isinstance(exc, NoProviderConfigured):
        return _error_response(
            503,
            "llm_not_configured",
            "No language model is configured on the server. You can still enter a regular expression yourself.",
        )
    if isinstance(exc, AllProvidersFailed):
        return _error_response(
            503,
            "llm_unavailable",
            "The language model is busy or unavailable. Try again in a minute, or enter a regular expression yourself.",
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        view = context.get("view")
        logger.error("Unhandled error in %s", type(view).__name__, exc_info=exc)
        return _error_response(500, "server_error", "Something went wrong on the server. Please try again.")

    # Keep DRF's response (and headers such as Retry-After) but use our error shape.
    if isinstance(exc, drf_exceptions.ValidationError):
        response.data = _envelope("validation_error", _first_message(exc.detail), exc.detail)
    elif isinstance(exc, drf_exceptions.Throttled):
        wait = f" Try again in {math.ceil(exc.wait)} seconds." if exc.wait else ""
        response.data = _envelope("rate_limited", f"Too many requests.{wait}")
    else:
        response.data = _envelope(getattr(exc, "default_code", "error"), str(getattr(exc, "detail", exc)))
    return response


def _error_response(status: int, code: str, message: str, details=None) -> Response:
    return Response(_envelope(code, message, details), status=status)


def _envelope(code: str, message: str, details=None) -> dict:
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def _first_message(detail) -> str:
    """Pick one human-readable message out of DRF's nested validation errors."""
    if isinstance(detail, dict):
        for field, value in detail.items():
            message = _first_message(value)
            return message if field == "non_field_errors" else f"{field}: {message}"
    if isinstance(detail, list) and detail:
        return _first_message(detail[0])
    return str(detail)
