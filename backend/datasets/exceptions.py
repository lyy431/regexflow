"""Errors that map directly to an HTTP response (see ``datasets.exception_handler``)."""


class AppError(Exception):
    status_code = 400
    code = "error"
    default_message = "Something went wrong."

    def __init__(self, message: str | None = None, *, details=None):
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class UnsupportedFileType(AppError):
    code = "unsupported_file_type"
    default_message = "Please upload a CSV or Excel file (.csv, .tsv, .xlsx, .xls)."


class FileTooLarge(AppError):
    status_code = 413
    code = "file_too_large"


class FileParseError(AppError):
    code = "file_parse_error"
    default_message = "The file could not be read."


class DatasetNotFound(AppError):
    status_code = 404
    code = "dataset_not_found"
    default_message = "Dataset not found. It may have expired; please upload the file again."


class DatasetDataMissing(AppError):
    status_code = 410
    code = "dataset_expired"
    default_message = "The data for this dataset is no longer available. Please upload the file again."


class InvalidPattern(AppError):
    code = "invalid_pattern"


class RegexTimeout(AppError):
    status_code = 422
    code = "regex_timeout"


class ColumnNotFound(AppError):
    code = "column_not_found"


class MissingReplacement(AppError):
    code = "missing_replacement"
    default_message = "Say what to replace the matches with, in the replacement field or in your description."


class NoChanges(AppError):
    status_code = 422
    code = "no_changes"
    default_message = "The pattern did not change any cell, so no step was added."


class NothingToUndo(AppError):
    status_code = 409
    code = "nothing_to_undo"
    default_message = "There are no steps to undo."


class ExportNotPossible(AppError):
    code = "export_not_possible"


class ConcurrentModification(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The dataset was changed by another request. Reload it and try again."
