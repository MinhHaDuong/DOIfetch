import csv
import importlib
import os
import re

from config import COL_DOI, COL_DOWNLOAD_STATUS, COL_TITLE, REFERENCES_DIR

SUPPORTED_INPUT_FORMATS = ("auto", "excel", "csv", "txt")


def list_table_files(data_directory=REFERENCES_DIR, input_format="auto"):
    if input_format not in SUPPORTED_INPUT_FORMATS:
        raise ValueError(f"Unsupported input format: {input_format}")

    if not os.path.isdir(data_directory):
        return []

    file_paths = []
    for file_name in os.listdir(data_directory):
        lower_name = file_name.lower()
        if input_format in ("auto", "excel") and lower_name.endswith((".xls", ".xlsx")):
            file_paths.append(os.path.join(data_directory, file_name))
        elif input_format in ("auto", "csv") and lower_name.endswith(".csv"):
            file_paths.append(os.path.join(data_directory, file_name))
        elif input_format in ("auto", "txt") and lower_name.endswith(".txt"):
            file_paths.append(os.path.join(data_directory, file_name))

    return sorted(file_paths)


EXTRA_INSTALL = (
    "uv tool install 'doifetch[{extra}] @ git+https://github.com/MinhHaDuong/DOIfetch'"
)


def require(module, extra):
    """Import an optional dependency, or fail naming the extra that provides it."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(
            f"{module} is not installed; it comes with the '{extra}' extra: "
            + EXTRA_INSTALL.format(extra=extra)
        ) from exc


def _read_txt(file_path):
    rows = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t", 1)
            identifier = parts[0]
            title = parts[1] if len(parts) > 1 else ""
            if identifier.startswith("doi:"):
                rows.append({COL_DOI: identifier[len("doi:") :], COL_TITLE: title})
            elif identifier.startswith("url:"):
                rows.append({COL_DOI: identifier, COL_TITLE: title})
            elif identifier.startswith("isbn:"):
                rows.append({COL_DOI: identifier, COL_TITLE: title})
            else:
                print(f"Skipping unrecognized line: {line}")
    return rows


def _rows_from_cells(cells):
    """Turn a header row plus data rows into dicts.

    Empty and missing cells become "", cells beyond the header are dropped,
    and blank rows are skipped.
    """
    cells = list(cells)
    if not cells:
        return []
    header = [str(name) if name is not None else "" for name in cells[0]]
    rows = []
    for row in cells[1:]:
        values = list(row)[: len(header)]
        values += [""] * (len(header) - len(values))
        if any(value not in (None, "") for value in values):
            rows.append(
                {
                    name: "" if value is None else value
                    for name, value in zip(header, values)
                }
            )
    return rows


def _read_excel(file_path):
    if file_path.lower().endswith(".xls"):
        xlrd = require("xlrd", "excel")
        sheet = xlrd.open_workbook(file_path).sheet_by_index(0)
        return _rows_from_cells(sheet.row_values(i) for i in range(sheet.nrows))
    openpyxl = require("openpyxl", "excel")
    workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    try:
        return _rows_from_cells(workbook.active.iter_rows(values_only=True))
    finally:
        workbook.close()


def read_table(file_path):
    """Read a reference file as a list of dicts, one per row, keyed by column name."""
    lower_path = file_path.lower()
    if lower_path.endswith(".txt"):
        return _read_txt(file_path)
    if lower_path.endswith(".csv"):
        # utf-8-sig: spreadsheet apps prefix "CSV UTF-8" exports with a BOM.
        with open(file_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            return _rows_from_cells(reader)
    return _read_excel(file_path)


def table_columns(rows):
    """Column names in first-seen order across all rows."""
    columns = {}
    for row in rows:
        columns.update(dict.fromkeys(row))
    return list(columns)


def read_doi_from_table(file_path):
    """Read DOI list from a table file.

    Returns (dois_list, rows) where dois_list is a list of (doi, row_index) tuples,
    or ([], None) on error.
    """
    dois = []
    try:
        rows = read_table(file_path)
        print(f"Successfully read file: {file_path}, {len(rows)} rows")

        for index, row in enumerate(rows):
            # Add download status column if missing
            row.setdefault(COL_DOWNLOAD_STATUS, "")
            doi = row.get(COL_DOI, "")
            if doi:
                dois.append((doi, index))

    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        return [], None

    print(f"Extracted {len(dois)} DOIs")
    return dois, rows


def validate_doi(doi):
    """Validate whether the DOI format is correct."""
    doi = doi.strip()
    if not doi:
        return False
    doi = doi.replace("doi:", "").replace("DOI:", "").strip()
    return re.match(r"^10\.\d+\/.+$", doi) is not None


def write_table(rows, file_path):
    lower_path = file_path.lower()
    if lower_path.endswith(".txt"):
        # Write as tab-separated DOI<TAB>Title, dropping successfully downloaded rows
        with open(file_path, "w", encoding="utf-8") as f:
            for row in rows:
                if row.get(COL_DOWNLOAD_STATUS) == "success":
                    continue
                identifier = str(row.get(COL_DOI, "")).strip()
                title = str(row.get(COL_TITLE, "")).strip()
                if not identifier and not title:
                    continue
                if identifier.startswith(("url:", "isbn:")):
                    f.write(f"{identifier}\t{title}\n")
                elif identifier:
                    f.write(f"doi:{identifier}\t{title}\n")
                else:
                    f.write(f"{title}\n")
        return

    columns = table_columns(rows)
    if lower_path.endswith(".csv"):
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, restval="")
            writer.writeheader()
            writer.writerows(rows)
        return

    if lower_path.endswith(".xlsx"):
        openpyxl = require("openpyxl", "excel")
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(columns)
        for row in rows:
            sheet.append([row.get(name, "") for name in columns])
        workbook.save(file_path)
        return

    raise ValueError(
        f"Cannot write {file_path}: only .txt, .csv and .xlsx are writable"
    )
