import os
import re

import pandas as pd

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
    return pd.DataFrame(rows, columns=[COL_DOI, COL_TITLE])


def read_table(file_path):
    lower_path = file_path.lower()
    if lower_path.endswith(".txt"):
        return _read_txt(file_path)
    if lower_path.endswith(".csv"):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)


def read_doi_from_table(file_path):
    """Read DOI list from a table file.

    Returns (dois_list, dataframe) where dois_list is a list of (doi, row_index) tuples,
    or ([], None) on error.
    """
    dois = []
    try:
        df = read_table(file_path)
        print(f"Successfully read file: {file_path}, {len(df)} rows")

        # Add download status column if missing
        if COL_DOWNLOAD_STATUS not in df.columns:
            df[COL_DOWNLOAD_STATUS] = ""

        # Extract DOIs from each row
        for index, row in df.iterrows():
            doi = row.get(COL_DOI, "")
            if doi:
                dois.append((doi, index))

    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        return [], None

    print(f"Extracted {len(dois)} DOIs")
    return dois, df


def validate_doi(doi):
    """Validate whether the DOI format is correct."""
    doi = doi.strip()
    if not doi:
        return False
    doi = doi.replace("doi:", "").replace("DOI:", "").strip()
    return re.match(r"^10\.\d+\/.+$", doi) is not None


def write_table(dataframe, file_path):
    lower_path = file_path.lower()
    if lower_path.endswith(".txt"):
        # Write as tab-separated DOI<TAB>Title, dropping successfully downloaded rows
        with open(file_path, "w", encoding="utf-8") as f:
            for _, row in dataframe.iterrows():
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

    if lower_path.endswith(".csv"):
        dataframe.to_csv(file_path, index=False)
        return

    if lower_path.endswith(".xlsx"):
        dataframe.to_excel(file_path, index=False, engine="openpyxl")
        return

    dataframe.to_excel(file_path, index=False)
