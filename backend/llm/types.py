from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


@dataclass(frozen=True)
class ColumnInfo:
    """What the model is told about a column: its name and inferred kind (never its values)."""

    name: str
    kind: str


class Answer(BaseModel):
    """Base for the JSON objects the model is asked to return. A null falls back to the field default."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("*", mode="before")
    @classmethod
    def _null_means_default(cls, value, info: ValidationInfo):
        field = cls.model_fields[info.field_name]
        if value is None and not field.is_required():
            return field.get_default(call_default_factory=True)
        return value


class RegexSuggestion(Answer):
    """Answer to a find-and-replace request."""

    pattern: str = ""
    flags: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    replacement_specified: bool = False
    replacement: str = ""
    explanation: str = ""
    error: str = ""


class ReformatSuggestion(Answer):
    """Answer to a request to rewrite values into another format."""

    pattern: str = ""
    flags: list[str] = Field(default_factory=list)
    template: str = ""
    target_columns: list[str] = Field(default_factory=list)
    explanation: str = ""
    error: str = ""


class ValueMapping(Answer):
    from_: str = Field(alias="from")
    to: str


class MappingSuggestion(Answer):
    """Answer to a request to write the values of one column consistently."""

    mapping: list[ValueMapping] = Field(default_factory=list)
    explanation: str = ""
    error: str = ""


@dataclass(frozen=True)
class GenerationResult[AnswerT: Answer]:
    suggestion: AnswerT
    provider: str  # label of the provider that answered, e.g. "gemini:gemini-3.1-flash-lite"
    cached: bool = False
