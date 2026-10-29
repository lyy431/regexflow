"""Per-IP rate limits that protect the free LLM quota and the server's disk."""

from rest_framework.throttling import AnonRateThrottle


class UploadRateThrottle(AnonRateThrottle):
    scope = "uploads"


class LLMRateThrottle(AnonRateThrottle):
    scope = "llm"
