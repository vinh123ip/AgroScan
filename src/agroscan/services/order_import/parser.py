"""Read order import files (.csv, .xlsx) into header-keyed rows that keep source row numbers."""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from agroscan.services.order_import.normalizer import normalize_cell, normalize_header

SUPPORTED_SUFFIXES = (".csv", ".xlsx")
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DATA_ROWS = 10_000
_DELIMITERS = (",", ";", "\t")


class ImportFileError(ValueError):
    """The file cannot be read as an order import table."""


@dataclass(frozen=True)
class ParsedRow:
    """One data row; ``row_number`` is the 1-based line/row in the source file."""

    row_number: int
    values: dict[str, str]


@dataclass(frozen=True)
class ParsedFile:
    headers: tuple[str, ...]
    rows: list[ParsedRow]


Table = list[tuple[int, list[str]]]


def parse_order_file(file_path: Union[Path, str]) -> ParsedFile:
    """Parse ``file_path`` into normalized headers and rows.

    Raises:
        ImportFileError: Unsupported, empty, corrupted, oversized or ambiguous file.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ImportFileError(f"Unsupported file type '{path.suffix or path.name}'. Use .csv or .xlsx.")
    if not path.is_file():
        raise ImportFileError(f"Import file not found: {path}")
    size = path.stat().st_size
    if size == 0:
        raise ImportFileError("The file is empty.")
    if size > MAX_FILE_BYTES:
        raise ImportFileError(f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    table = _read_csv(path) if suffix == ".csv" else _read_xlsx(path)
    return _to_rows(table)


def _read_csv(path: Path) -> Table:
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise ImportFileError("The CSV file contains binary data.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError("The CSV file must be UTF-8 encoded.") from None
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = _detect_delimiter(first_line)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    table: Table = []
    line = 0
    try:
        for cells in reader:
            table.append((line + 1, [normalize_cell(c) for c in cells]))
            line = reader.line_num
    except csv.Error as exc:
        raise ImportFileError(f"The CSV file is malformed: {exc}") from None
    return table


def _detect_delimiter(line: str) -> str:
    counts = {d: 0 for d in _DELIMITERS}
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes and ch in counts:
            counts[ch] += 1
    return max(_DELIMITERS, key=counts.__getitem__)


def _read_xlsx(path: Path) -> Table:
    corrupted = "The Excel file is corrupted or is not a valid .xlsx workbook."
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError):
        raise ImportFileError(corrupted) from None
    try:
        for sheet in workbook.worksheets:
            if getattr(sheet, "sheet_state", "visible") != "visible":
                continue
            table = [
                (number, [normalize_cell(v) for v in values])
                for number, values in enumerate(sheet.iter_rows(values_only=True), start=1)
            ]
            if any(any(cells) for _, cells in table):
                return table
        return []
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise ImportFileError(corrupted) from None
    finally:
        workbook.close()


def _to_rows(table: Table) -> ParsedFile:
    filled = [(number, cells) for number, cells in table if any(cells)]
    if not filled:
        raise ImportFileError("The file has no data.")
    header_row, header_cells = filled[0]
    headers = [normalize_header(cell) for cell in header_cells]
    duplicates = sorted({h for h in headers if h and headers.count(h) > 1})
    if duplicates:
        raise ImportFileError(f"Duplicate column(s) in row {header_row}: {', '.join(duplicates)}.")
    data = filled[1:]
    if len(data) > MAX_DATA_ROWS:
        raise ImportFileError(f"The file has more than {MAX_DATA_ROWS} data rows.")
    rows = []
    for number, cells in data:
        if any(value for i, value in enumerate(cells) if i >= len(headers) or not headers[i]):
            raise ImportFileError(f"Row {number} has values outside the named header columns.")
        rows.append(ParsedRow(number, {
            header: cells[i] if i < len(cells) else ""
            for i, header in enumerate(headers) if header
        }))
    return ParsedFile(tuple(h for h in headers if h), rows)
