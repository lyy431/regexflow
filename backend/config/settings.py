"""Django settings for the RegexFlow backend.

Every environment-specific value comes from environment variables, optionally
loaded from ``backend/.env``. See ``.env.example`` for the full list.
"""

import re
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

env = environ.Env()
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

# --- Core ---------------------------------------------------------------------

DEBUG = env.bool("DJANGO_DEBUG", default=False)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY, or DJANGO_DEBUG=true for local development.")
    SECRET_KEY = "insecure-local-development-key"

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "datasets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

if not DEBUG:
    # Hosting platforms terminate TLS at their proxy.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
X_FRAME_OPTIONS = "DENY"
# The API uses no cookies or sessions, so there is nothing for CSRF protection to guard.
SILENCED_SYSTEM_CHECKS = ["security.W003"]

# --- Storage ------------------------------------------------------------------

# Holds the SQLite database and the uploaded datasets. Point it at a
# persistent volume in production if uploads should survive restarts.
DATA_DIR = Path(env("DATA_DIR", default=str(BASE_DIR / "var")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MEDIA_ROOT = DATA_DIR / "media"

# The React build (frontend/dist) is served by WhiteNoise under /static/.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(exist_ok=True)  # WhiteNoise warns when it is missing (before collectstatic)
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}


def _is_hashed_asset(path: str, url: str) -> bool:
    """Vite puts a content hash in asset file names, so they can be cached forever."""
    return bool(re.match(r"^.+[.-][0-9a-zA-Z_-]{8,12}\..+$", url))


WHITENOISE_IMMUTABLE_FILE_TEST = _is_hashed_asset

# --- API ------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # The API is anonymous: datasets are only reachable through their random UUID.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "datasets.exception_handler.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "uploads": env("UPLOAD_RATE_LIMIT", default="30/hour"),
        "llm": env("LLM_RATE_LIMIT", default="60/hour"),
    },
    # Number of reverse proxies in front of the app, so throttling sees real client IPs.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=None),
}

# --- Application ----------------------------------------------------------------

MAX_UPLOAD_SIZE_MB = env.int("MAX_UPLOAD_SIZE_MB", default=50)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # bigger uploads are streamed to a temp file
DATASET_TTL_HOURS = env.int("DATASET_TTL_HOURS", default=24)  # 0 keeps datasets forever
REGEX_TIMEOUT_SECONDS = env.float("REGEX_TIMEOUT_SECONDS", default=10.0)

# --- LLM providers ----------------------------------------------------------------

# Tried in order; providers without the configuration they need are skipped.
LLM_PROVIDERS = [name.strip().lower() for name in env.list("LLM_PROVIDERS", default=["gemini", "groq"]) if name.strip()]
LLM_TIMEOUT_SECONDS = env.float("LLM_TIMEOUT_SECONDS", default=15.0)  # one attempt per provider, no retries
LLM_CACHE_TTL_SECONDS = env.int("LLM_CACHE_TTL_SECONDS", default=24 * 60 * 60)
LLM_PROVIDER_OPTIONS = {
    "gemini": {
        "base_url": env("GEMINI_BASE_URL", default="https://generativelanguage.googleapis.com/v1beta/openai/"),
        "api_key": env("GEMINI_API_KEY", default=""),
        "model": env("GEMINI_MODEL", default="gemini-3.1-flash-lite"),
        "json_mode": env("GEMINI_JSON_MODE", default="json_schema"),
        "reasoning_effort": env("GEMINI_REASONING_EFFORT", default="low"),
        "requires_api_key": True,
    },
    "groq": {
        "base_url": env("GROQ_BASE_URL", default="https://api.groq.com/openai/v1"),
        "api_key": env("GROQ_API_KEY", default=""),
        "model": env("GROQ_MODEL", default="openai/gpt-oss-120b"),
        "json_mode": env("GROQ_JSON_MODE", default="json_object"),
        "reasoning_effort": env("GROQ_REASONING_EFFORT", default=""),
        "requires_api_key": True,
    },
    # Any OpenAI-compatible server, e.g. Ollama, llama.cpp, vLLM or LM Studio serving your own model.
    "local": {
        "base_url": env("LOCAL_LLM_BASE_URL", default="http://localhost:11434/v1"),
        "api_key": env("LOCAL_LLM_API_KEY", default=""),
        "model": env("LOCAL_LLM_MODEL", default=""),
        "json_mode": env("LOCAL_LLM_JSON_MODE", default="json_object"),
        "reasoning_effort": env("LOCAL_LLM_REASONING_EFFORT", default=""),
        "requires_api_key": False,
    },
}

# --- Logging ------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
