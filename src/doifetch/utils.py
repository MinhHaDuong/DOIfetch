import importlib
import os
import re

from doifetch.config import COL_DOI, COL_DOWNLOAD_STATUS, COL_TITLE, REFERENCES_DIR


def list_table_files(data_directory=REFERENCES_DIR):
    """The `.txt` reference lists in a directory, sorted."""
    if not os.path.isdir(data_directory):
        return []

    return sorted(
        os.path.join(data_directory, name)
        for name in os.listdir(data_directory)
        if name.lower().endswith(".txt")
    )


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
            elif validate_doi(identifier):  # a bare DOI, as in the Crossref UI
                rows.append({COL_DOI: identifier, COL_TITLE: title})
            else:
                print(f"Skipping unrecognized line: {line}")
    return rows


def read_table(file_path):
    """Read a `.txt` reference list as a list of dicts, one per row."""
    if not file_path.lower().endswith(".txt"):
        raise ValueError(f"Cannot read {file_path}: only .txt reference lists")
    return _read_txt(file_path)


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

    except Exception as e:  # noqa: BLE001 - unreadable input file is reported
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


def normalize_isbn(isbn):
    """Return the ISBN-10/13 without hyphens or spaces, or None if invalid.

    Accepts an optional `isbn:` prefix. Check digits are verified.
    """
    text = str(isbn or "").strip()
    if text.lower().startswith("isbn:"):
        text = text[len("isbn:") :]
    text = re.sub(r"[-\s]", "", text).upper()
    if re.fullmatch(r"\d{9}[\dX]", text):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(text))
        return text if total % 11 == 0 else None
    if re.fullmatch(r"\d{13}", text):
        total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(text))
        return text if total % 10 == 0 else None
    return None


def write_table(rows, file_path):
    """Rewrite a `.txt` list to the rows not yet fetched (identifier TAB title)."""
    if not file_path.lower().endswith(".txt"):
        raise ValueError(f"Cannot write {file_path}: only .txt reference lists")
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
