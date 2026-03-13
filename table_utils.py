import os

import pandas as pd


SUPPORTED_INPUT_FORMATS = ("auto", "excel", "csv", "txt")


def list_table_files(data_directory="data", input_format="auto"):
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
                doi = identifier[len("doi:") :]
                rows.append({"DOI": doi, "Article Title": title})
            elif identifier.startswith("url:"):
                print(f"Skipping URL entry: {title or identifier}")
            elif identifier.startswith("isbn:"):
                print(f"Skipping ISBN entry: {title or identifier}")
            else:
                print(f"Skipping unrecognized line: {line}")
    return pd.DataFrame(rows, columns=["DOI", "Article Title"])


def read_table(file_path):
    lower_path = file_path.lower()
    if lower_path.endswith(".txt"):
        return _read_txt(file_path)
    if lower_path.endswith(".csv"):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)


def write_table(dataframe, file_path):
    lower_path = file_path.lower()
    if lower_path.endswith(".txt"):
        return

    if lower_path.endswith(".csv"):
        dataframe.to_csv(file_path, index=False)
        return

    if lower_path.endswith(".xlsx"):
        dataframe.to_excel(file_path, index=False, engine="openpyxl")
        return

    dataframe.to_excel(file_path, index=False)
