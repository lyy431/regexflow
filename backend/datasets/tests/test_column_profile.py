import pytest

from datasets.services.column_profile import ColumnKind, infer_kind


@pytest.mark.parametrize(
    ("values", "kind"),
    [
        (["1", "2.5", "-3", "1e5"], ColumnKind.NUMERIC),
        (["0412345678", "0298765432"], ColumnKind.TEXT),  # leading zeros: an identifier, not a number
        (["Yes", "no", "TRUE"], ColumnKind.BOOLEAN),
        (["2024-01-31", "31/01/2024", "2024-02-01 09:30"], ColumnKind.DATE),
        (["john@example.com", "42"], ColumnKind.TEXT),
        (["", "  "], ColumnKind.EMPTY),
    ],
)
def test_infers_column_kinds(values, kind):
    assert infer_kind(values) == kind
