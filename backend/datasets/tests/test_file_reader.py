import io

import openpyxl
import pytest

from datasets.exceptions import FileParseError, UnsupportedFileType
from datasets.services.file_reader import read_table


def read(content: bytes | str, filename: str = "data.csv"):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return read_table(io.BytesIO(content), filename)


def workbook_bytes(*rows) -> bytes:
    workbook = openpyxl.Workbook()
    for row in rows:
        workbook.active.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_reads_every_cell_as_text_and_keeps_leading_zeros():
    table = read("id,phone,postcode\n1,0412345678,0800\n2,,2000\n")

    assert table.file_format == "csv"
    assert table.frame.columns.tolist() == ["id", "phone", "postcode"]
    assert table.frame.values.tolist() == [["1", "0412345678", "0800"], ["2", "", "2000"]]


def test_detects_semicolons_and_a_utf8_byte_order_mark():
    table = read("﻿name;city\nZoë;Sydney\n".encode())
    assert table.frame.to_dict("records") == [{"name": "Zoë", "city": "Sydney"}]


def test_falls_back_to_a_legacy_encoding():
    table = read("name,city\nRené,Montréal\n".encode("cp1252"))
    assert table.frame.loc[0, "name"] == "René"


def test_reads_tab_separated_files():
    assert read("a\tb\n1\t2\n", "data.tsv").frame.values.tolist() == [["1", "2"]]


def test_cleans_blank_and_duplicate_headers_and_drops_blank_rows():
    table = read("Name,,Name,Name \nA,B,C,D\n,,,\nD,E,F,G\n")

    # pandas renames the second "Name" to "Name.1"; "Name " only clashes after stripping.
    assert table.frame.columns.tolist() == ["Name", "Column 2", "Name.1", "Name (2)"]
    assert table.frame.values.tolist() == [["A", "B", "C", "D"], ["D", "E", "F", "G"]]


def test_reads_excel_cells_as_text():
    table = read(workbook_bytes(["ID", "Phone", "Note"], [1, "0412345678", None], [2.5, None, "x"]), "data.xlsx")

    assert table.file_format == "xlsx"
    assert table.frame.values.tolist() == [["1", "0412345678", ""], ["2.5", "", "x"]]


@pytest.mark.parametrize(
    ("content", "filename", "message"),
    [
        (b"", "data.csv", "empty"),
        ("id,name\n", "data.csv", "no data rows"),
        (b"\x00not really a workbook", "data.xlsx", "could not be read"),
    ],
)
def test_reports_unreadable_files(content, filename, message):
    with pytest.raises(FileParseError, match=message):
        read(content, filename)


def test_rejects_unsupported_file_types():
    with pytest.raises(UnsupportedFileType):
        read("{}", "data.json")
