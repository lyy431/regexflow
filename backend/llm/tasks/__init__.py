"""The kinds of questions RegexFlow asks a model. Each task supplies its prompt, schema and checks."""

from llm.tasks.find_replace import FindReplaceTask
from llm.tasks.normalize import NormalizeTask
from llm.tasks.reformat import ReformatTask

__all__ = ["FindReplaceTask", "NormalizeTask", "ReformatTask"]
