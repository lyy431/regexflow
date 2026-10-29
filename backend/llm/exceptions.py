class LLMError(Exception):
    """Base class for errors raised while asking an LLM."""


class NoProviderConfigured(LLMError):
    """No provider has the configuration (model, API key) it needs."""


class ProviderError(LLMError):
    """One provider failed; the next provider in the chain may still succeed."""


class ProviderUnavailable(ProviderError):
    """Network error, timeout, rate limit, rejected API key or server error."""


class InvalidOutput(ProviderError):
    """The provider kept returning unusable output, even after being asked to fix it."""


class AllProvidersFailed(LLMError):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("; ".join(failures) or "No provider produced a usable answer.")


class RequestNotPossible(LLMError):
    """The model explained that the request cannot be done with this kind of step."""


class InvalidSuggestion(Exception):
    """An answer failed validation. The message is sent back to the model so it can fix it."""
