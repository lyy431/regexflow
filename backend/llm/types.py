from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True)
class ColumnInfo:
    """What the model is told about a column: its name and inferred kind (never its values)."""

    name: str
    kind: str


class RegexSuggestion(BaseModel):
    """The JSON object the model is asked to return."""

    model_config = ConfigDict(extra="ignore")

    pattern: str = ""
    flags: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    replacement_specified: bool = False
    replacement: str = ""
    explanation: str = ""
    error: str = ""

    @field_validator("pattern", "replacement", "explanation", "error", mode="before")
    @classmethod
    def _null_to_empty_string(cls, value):
        return "" if value is None else value

    @field_validator("flags", "target_columns", mode="before")
    @classmethod
    def _null_to_empty_list(cls, value):
        return [] if value is None else value


@dataclass(frozen=True)
class GenerationResult:
    suggestion: RegexSuggestion
    provider: str  # label of the provider that answered, e.g. "gemini:gemini-3.1-flash-lite"
    cached: bool = False
