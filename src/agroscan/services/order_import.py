"""Order file import: read Excel/CSV, validate rows and build a preview (step 1, D-029).

Pure Python (standard library only) with no UI or storage dependency, so the
same checks can be reused by the Data Import page and, later, by whichever
Order Import backend is approved (see ``order_gateway.py``).

- ``.csv``  is read with :mod:`csv` (UTF-8, delimiter ``,`` ``;`` or tab).
- ``.xlsx`` is read with :mod:`zipfile` + :mod:`xml.etree` (first worksheet,
  cell values only). No third-party dependency is required; formulas are read
  from their cached values, exactly as Excel last saved them.

Row numbers reported to the user are spreadsheet row numbers (the header is
normally row 1), so they match what the user sees in Excel.
"""

import csv
import io
import math
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

SUPPORTED_EXTENSIONS = (".xlsx", ".csv")
MAX_FILE_BYTES       = 20 * 1024 * 1024     # 20 MB
MAX_DATA_ROWS        = 10_000
_MAX_XML_BYTES       = 100 * 1024 * 1024    # Uncompressed XML part (zip-bomb guard)

ORDER_CODE_PATTERN   = re.compile(r"^[A-Z0-9]{1,20}$")   # Must fit the box QR (D-019)
MAX_SUPPLIER_LENGTH  = 200
TOTAL_BOXES_RANGE    = (1, 9999)                         # BoxCode allows up to 4 digits
MIN_EXPECTED_QTY     = 1


class ImportFileError(Exception):
    """The file cannot be used at all (wrong type, unreadable, empty, too large)."""


@dataclass(frozen=True)
class ColumnSpec:
    key:   str
    label: str


ORDER_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("order_code",        "Order Code"),
    ColumnSpec("product_code",      "Product Code"),
    ColumnSpec("supplier",          "Supplier"),
    ColumnSpec("total_boxes",       "Total Boxes"),
    ColumnSpec("expected_quantity", "Expected Quantity"),
)
_COLUMN_KEYS = {c.key for c in ORDER_COLUMNS}
_COLUMN_LABELS = {c.key: c.label for c in ORDER_COLUMNS}

_TEMPLATE_EXAMPLE = ("DH00200", "BANANA", "Green Valley Farm", "10", "240")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileInfo:
    path:        Path
    name:        str
    extension:   str
    size_bytes:  int
    modified_at: datetime

    @property
    def type_label(self) -> str:
        return "Excel workbook (.xlsx)" if self.extension == ".xlsx" else "CSV text file (.csv)"

    @property
    def size_label(self) -> str:
        size = float(self.size_bytes)
        for unit in ("bytes", "KB", "MB"):
            if size < 1024 or unit == "MB":
                return f"{int(size)} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{self.size_bytes} bytes"


@dataclass(frozen=True)
class RowIssue:
    row_number: int
    column:     Optional[str]   # Column key, or None for a whole-row problem
    message:    str

    @property
    def column_label(self) -> str:
        if self.column is None:
            return "—"
        return _COLUMN_LABELS.get(self.column, self.column)


@dataclass
class OrderImportRow:
    """One data row: raw cells as read, normalized values and its problems."""

    row_number: int
    cells:      list[str]                       # Raw values, aligned with ImportPreview.headers
    values:     dict[str, str] = field(default_factory=dict)   # Normalized text per column key
    issues:     list[RowIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def order_code(self) -> str:
        return self.values.get("order_code", "")

    @property
    def product_code(self) -> str:
        return self.values.get("product_code", "")

    @property
    def supplier(self) -> str:
        return self.values.get("supplier", "")

    @property
    def total_boxes(self) -> Optional[int]:
        return _to_int_or_none(self.values.get("total_boxes", ""))

    @property
    def expected_quantity(self) -> Optional[int]:
        return _to_int_or_none(self.values.get("expected_quantity", ""))


@dataclass
class ImportPreview:
    file:              FileInfo
    headers:           list[str]                 # Header labels as written in the file
    column_keys:       list[Optional[str]]       # Recognized column key per header (None = ignored)
    rows:              list[OrderImportRow]
    structure_errors:  list[str] = field(default_factory=list)   # Block the import
    warnings:          list[str] = field(default_factory=list)   # Informational only

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def valid_rows(self) -> int:
        return sum(1 for r in self.rows if r.is_valid)

    @property
    def invalid_rows(self) -> int:
        return self.total_rows - self.valid_rows

    @property
    def issues(self) -> list[RowIssue]:
        return [issue for row in self.rows for issue in row.issues]

    @property
    def can_import(self) -> bool:
        """All-or-nothing rule: import only when the structure and every row are valid."""
        return not self.structure_errors and self.total_rows > 0 and self.invalid_rows == 0

    @property
    def status_text(self) -> str:
        if self.structure_errors:
            return "Invalid file structure"
        if self.total_rows == 0:
            return "No data rows"
        if self.invalid_rows:
            return f"{self.invalid_rows} row(s) need fixing"
        return "Ready to import"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def inspect_file(path: str | Path) -> FileInfo:
    """Check that ``path`` is an existing, supported and not oversized file.

    Raises:
        ImportFileError: With a message suitable for the UI.
    """
    file_path = Path(path)
    extension = file_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        if extension == ".xls":
            raise ImportFileError(
                "Legacy Excel 97–2003 (.xls) files are not supported. "
                "Open the file in Excel and save it as .xlsx or CSV UTF-8."
            )
        raise ImportFileError(
            f"Unsupported file type '{extension or 'no extension'}'. "
            "Select an Excel (.xlsx) or CSV (.csv) file."
        )
    try:
        stat = file_path.stat()
    except FileNotFoundError:
        raise ImportFileError(f"File not found: {file_path}") from None
    except OSError as exc:
        raise ImportFileError(f"Cannot access the file — {exc.strerror or exc}") from None
    if not file_path.is_file():
        raise ImportFileError(f"{file_path.name} is not a file.")
    if stat.st_size == 0:
        raise ImportFileError(f"{file_path.name} is empty.")
    if stat.st_size > MAX_FILE_BYTES:
        raise ImportFileError(
            f"{file_path.name} is {stat.st_size / 1024 / 1024:.1f} MB; "
            f"the maximum is {MAX_FILE_BYTES // 1024 // 1024} MB."
        )
    return FileInfo(
        path=file_path,
        name=file_path.name,
        extension=extension,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime),
    )


def read_records(info: FileInfo) -> list[tuple[int, list[str]]]:
    """Return ``(row_number, cells)`` for every row of the file, empty rows included.

    Raises:
        ImportFileError: The file cannot be parsed.
    """
    if info.extension == ".csv":
        return _read_csv(info.path)
    return _read_xlsx(info.path)


def build_preview(
    path: str | Path,
    known_product_codes: Optional[Iterable[str]] = None,
    existing_order_codes: Iterable[str] = (),
) -> ImportPreview:
    """Read and validate an order file. Blocking — run it off the UI thread.

    Args:
        path: ``.xlsx`` or ``.csv`` file.
        known_product_codes: Product codes from the catalog. ``None`` skips the check.
        existing_order_codes: Order codes already stored in the system (uniqueness).

    Raises:
        ImportFileError: The file cannot be used at all.
    """
    info = inspect_file(path)
    records = read_records(info)
    headers, data = _split_header(records)
    if not headers:
        raise ImportFileError("The file contains no data. The first row must contain column headers.")
    if len(data) > MAX_DATA_ROWS:
        raise ImportFileError(
            f"The file has {len(data):,} data rows; the maximum per import is {MAX_DATA_ROWS:,}. "
            "Split it into smaller files."
        )

    column_keys, structure_errors, warnings = _map_columns(headers)
    rows = [OrderImportRow(number, _fit(cells, len(headers))) for number, cells in data]
    _validate_rows(
        rows, headers, data, column_keys,
        None if known_product_codes is None else {c.strip().upper() for c in known_product_codes},
        {c.strip().upper() for c in existing_order_codes},
    )
    return ImportPreview(info, headers, column_keys, rows, structure_errors, warnings)


def normalize_header(text: str) -> str:
    """``" Order Code "`` / ``"order-code"`` → ``"order_code"``."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def template_csv_text() -> str:
    """CSV template (header + one example row) offered by the Data Import page (D-029)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([c.key for c in ORDER_COLUMNS])
    writer.writerow(_TEMPLATE_EXAMPLE)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _map_columns(headers: list[str]) -> tuple[list[Optional[str]], list[str], list[str]]:
    keys: list[Optional[str]] = []
    errors: list[str] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}
    ignored: list[str] = []
    for index, header in enumerate(headers):
        key = normalize_header(header)
        if key in _COLUMN_KEYS:
            if key in seen:
                errors.append(
                    f"Column '{_COLUMN_LABELS[key]}' appears more than once "
                    f"(columns {_column_letter(seen[key])} and {_column_letter(index)})."
                )
                keys.append(None)
                continue
            seen[key] = index
            keys.append(key)
        else:
            keys.append(None)
            ignored.append(header.strip() or f"(blank header, column {_column_letter(index)})")
    missing = [c.label for c in ORDER_COLUMNS if c.key not in seen]
    if missing:
        errors.append(
            "Missing required column(s): " + ", ".join(missing) + ". "
            "Expected headers: " + ", ".join(c.key for c in ORDER_COLUMNS) + "."
        )
    if ignored:
        warnings.append("Ignored column(s) not used for orders: " + ", ".join(ignored) + ".")
    return keys, errors, warnings


def _validate_rows(
    rows: list[OrderImportRow],
    headers: list[str],
    data: list[tuple[int, list[str]]],
    column_keys: list[Optional[str]],
    known_products: Optional[set[str]],
    existing_orders: set[str],
) -> None:
    width = len(headers)
    index_of = {key: i for i, key in enumerate(column_keys) if key is not None}
    code_rows: dict[str, list[OrderImportRow]] = defaultdict(list)

    for row, (_, raw_cells) in zip(rows, data):
        n = row.row_number
        extra = [c for c in raw_cells[width:] if c.strip()]
        if extra:
            row.issues.append(RowIssue(n, None, "Row has values outside the header columns."))

        def cell(key: str) -> Optional[str]:
            i = index_of.get(key)
            return None if i is None else row.cells[i].strip()

        code = cell("order_code")
        if code is not None:
            code = code.upper()
            row.values["order_code"] = code
            if not code:
                row.issues.append(RowIssue(n, "order_code", "Order code is required."))
            elif not ORDER_CODE_PATTERN.match(code):
                row.issues.append(RowIssue(
                    n, "order_code",
                    f"Order code '{code}' is invalid: use 1–20 uppercase letters or digits, no spaces or symbols.",
                ))
            else:
                code_rows[code].append(row)
                if code in existing_orders:
                    row.issues.append(RowIssue(n, "order_code", f"Order {code} already exists in the system."))

        product = cell("product_code")
        if product is not None:
            product = product.upper()
            row.values["product_code"] = product
            if not product:
                row.issues.append(RowIssue(n, "product_code", "Product code is required."))
            elif known_products is not None and product not in known_products:
                row.issues.append(RowIssue(
                    n, "product_code",
                    f"Product '{product}' is not in Catalog & Criteria. Add it there first or fix the code.",
                ))

        supplier = cell("supplier")
        if supplier is not None:
            supplier = " ".join(supplier.split())
            row.values["supplier"] = supplier
            if not supplier:
                row.issues.append(RowIssue(n, "supplier", "Supplier is required."))
            elif len(supplier) > MAX_SUPPLIER_LENGTH:
                row.issues.append(RowIssue(
                    n, "supplier", f"Supplier must be at most {MAX_SUPPLIER_LENGTH} characters."
                ))

        low, high = TOTAL_BOXES_RANGE
        _check_int(row, "total_boxes", cell("total_boxes"), "Total boxes", low, high)
        _check_int(row, "expected_quantity", cell("expected_quantity"), "Expected quantity", MIN_EXPECTED_QTY, None)

    for code, dupes in code_rows.items():
        if len(dupes) < 2:
            continue
        numbers = ", ".join(str(r.row_number) for r in dupes)
        for row in dupes:
            row.issues.append(RowIssue(
                row.row_number, "order_code", f"Order code {code} is duplicated in this file (rows {numbers})."
            ))


def _check_int(
    row: OrderImportRow, key: str, raw: Optional[str], label: str, low: int, high: Optional[int]
) -> None:
    if raw is None:
        return
    text = raw.replace(",", "").replace(" ", "") if _looks_grouped(raw) else raw.strip()
    if not text:
        row.issues.append(RowIssue(row.row_number, key, f"{label} is required."))
        return
    value = _to_int_or_none(text)
    if value is None:
        row.issues.append(RowIssue(row.row_number, key, f"{label} must be a whole number (got '{raw}')."))
        return
    row.values[key] = str(value)
    if value < low or (high is not None and value > high):
        bound = f"between {low} and {high}" if high is not None else f"at least {low}"
        row.issues.append(RowIssue(row.row_number, key, f"{label} must be {bound} (got {value})."))


def _looks_grouped(text: str) -> bool:
    """``"1,250"`` or ``"1 250"`` thousands grouping, not a decimal."""
    return bool(re.fullmatch(r"\s*-?\d{1,3}([, ]\d{3})+\s*", text))


def _to_int_or_none(text: str) -> Optional[int]:
    text = text.strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    if re.fullmatch(r"[+-]?\d+\.0+", text):       # Excel numeric cell like "10.0"
        return int(float(text))
    return None


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _split_header(
    records: list[tuple[int, list[str]]],
) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """First non-empty row is the header; later empty rows are skipped."""
    non_empty = [(n, cells) for n, cells in records if any(c.strip() for c in cells)]
    if not non_empty:
        return [], []
    _, header_cells = non_empty[0]
    last = max(i for i, c in enumerate(header_cells) if c.strip())
    headers = [c.strip() for c in header_cells[: last + 1]]
    return headers, non_empty[1:]


def _fit(cells: list[str], width: int) -> list[str]:
    return (cells + [""] * width)[:width]


def _read_csv(path: Path) -> list[tuple[int, list[str]]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ImportFileError(f"Cannot read the file — {exc.strerror or exc}") from None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError(
            "The CSV file is not UTF-8 encoded. In Excel use "
            "'Save As → CSV UTF-8 (Comma delimited) (*.csv)' and try again."
        ) from None
    if "\x00" in text:
        raise ImportFileError("The file does not look like a CSV text file.")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    records: list[tuple[int, list[str]]] = []
    try:
        for number, cells in enumerate(csv.reader(io.StringIO(text, newline=""), dialect), start=1):
            records.append((number, [c.strip() for c in cells]))
    except csv.Error as exc:
        raise ImportFileError(f"The CSV file is malformed near row {len(records) + 1} — {exc}") from None
    return records


_NS_MAIN    = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_ATTR_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_CELL_REF   = re.compile(r"^([A-Z]+)(\d+)$")


def _read_xlsx(path: Path) -> list[tuple[int, list[str]]]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            sheet_name = _first_sheet_name(archive, names)
            shared = _shared_strings(archive, names)
            sheet = _parse_part(archive, sheet_name)
    except zipfile.BadZipFile:
        raise ImportFileError(
            "The file is not a valid Excel workbook (.xlsx). It may be corrupted, "
            "password-protected or renamed from another format."
        ) from None
    except ET.ParseError as exc:
        raise ImportFileError(f"The Excel workbook is corrupted — {exc}") from None
    except OSError as exc:
        raise ImportFileError(f"Cannot read the file — {exc.strerror or exc}") from None

    rows: dict[int, dict[int, str]] = {}
    next_row = 1
    for row_el in sheet.iter(f"{_NS_MAIN}row"):
        number = int(row_el.get("r") or next_row)
        next_row = number + 1
        cells: dict[int, str] = {}
        next_col = 0
        for cell_el in row_el.findall(f"{_NS_MAIN}c"):
            col = next_col
            match = _CELL_REF.match(cell_el.get("r", ""))
            if match:
                col = _column_index(match.group(1))
            next_col = col + 1
            value = _cell_text(cell_el, shared)
            if value != "":
                cells[col] = value
        rows[number] = cells

    records: list[tuple[int, list[str]]] = []
    for number in sorted(rows):
        cells = rows[number]
        width = max(cells) + 1 if cells else 0
        records.append((number, [cells.get(i, "").strip() for i in range(width)]))
    return records


def _parse_part(archive: zipfile.ZipFile, name: str) -> ET.Element:
    if archive.getinfo(name).file_size > _MAX_XML_BYTES:
        raise ImportFileError("The Excel workbook is too large to import.")
    return ET.fromstring(archive.read(name))


def _first_sheet_name(archive: zipfile.ZipFile, names: set[str]) -> str:
    """Resolve the first worksheet through workbook.xml and its relationships."""
    fallback = "xl/worksheets/sheet1.xml"
    if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
        workbook = _parse_part(archive, "xl/workbook.xml")
        rels = _parse_part(archive, "xl/_rels/workbook.xml.rels")
        targets = {r.get("Id"): r.get("Target", "") for r in rels.iter(f"{_NS_PKG_REL}Relationship")}
        first = workbook.find(f"{_NS_MAIN}sheets/{_NS_MAIN}sheet")
        if first is not None:
            target = targets.get(first.get(_ATTR_REL_ID), "")
            if target:
                resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
                    posixpath.join("xl", target)
                )
                if resolved in names:
                    return resolved
    if fallback in names:
        return fallback
    raise ImportFileError("The Excel workbook does not contain any worksheet.")


def _shared_strings(archive: zipfile.ZipFile, names: set[str]) -> list[str]:
    if "xl/sharedStrings.xml" not in names:
        return []
    root = _parse_part(archive, "xl/sharedStrings.xml")
    return [_rich_text(si) for si in root.findall(f"{_NS_MAIN}si")]


def _rich_text(element: ET.Element) -> str:
    """Text of an ``<si>`` / ``<is>`` element: plain ``<t>`` or rich-text runs ``<r><t>``.

    Phonetic hints (``<rPh>``) are excluded on purpose.
    """
    parts: list[str] = []
    for child in element:
        if child.tag == f"{_NS_MAIN}t":
            parts.append(child.text or "")
        elif child.tag == f"{_NS_MAIN}r":
            t = child.find(f"{_NS_MAIN}t")
            if t is not None:
                parts.append(t.text or "")
    return "".join(parts)


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        inline = cell.find(f"{_NS_MAIN}is")
        return _rich_text(inline) if inline is not None else ""
    value_el = cell.find(f"{_NS_MAIN}v")
    raw = value_el.text if value_el is not None and value_el.text else ""
    if kind == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""
    if kind == "b":
        return "TRUE" if raw == "1" else "FALSE" if raw == "0" else raw
    if kind in ("str", "e", "d"):
        return raw
    return _format_number(raw)


def _format_number(raw: str) -> str:
    """Excel stores ``10`` as ``"10"`` or ``"10.0"``/``"1E1"``; show whole numbers without decimals."""
    try:
        number = float(raw)
    except ValueError:
        return raw
    if math.isfinite(number) and number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return raw


def _column_index(letters: str) -> int:
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters
