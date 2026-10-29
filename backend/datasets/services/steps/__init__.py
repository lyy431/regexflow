"""Kinds of steps. Each module previews a request and applies it as a new version of the dataset."""

from datasets.models import Transformation
from datasets.services.steps import find_replace, normalize, reformat

BY_KIND = {
    Transformation.Kind.REGEX_REPLACE: find_replace,
    Transformation.Kind.REFORMAT: reformat,
    Transformation.Kind.NORMALIZE_VALUES: normalize,
}

__all__ = ["BY_KIND", "find_replace", "normalize", "reformat"]
