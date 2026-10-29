"""Settings for the test suite: no real LLM calls, no throttling surprises."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")
os.environ["LLM_PROVIDERS"] = ""  # tests inject fake providers explicitly

from config.settings import *  # noqa: E402, F403

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"uploads": "1000/minute", "llm": "1000/minute"},
}
