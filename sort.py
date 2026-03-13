import argparse
import pandas as pd

from config import COL_DOWNLOAD_STATUS, REFERENCES_DIR, STATUS_SUCCESS
from table_utils import (
    SUPPORTED_INPUT_FORMATS,
    list_table_files,
    read_table,
    write_table,
)


def sort_excel_by_download_status(data_directory=REFERENCES_DIR, input_format="auto"):
    """Sort table files by Download Status column: empty values first, STATUS_SUCCESS last."""
    excel_files = list_table_files(data_directory, input_format)

    if not excel_files:
        print("No table files found")
        return

    print(f"Found {len(excel_files)} table file(s)")

    # Process each table file
    for excel_file in excel_files:
        try:
            df = read_table(excel_file)

            # Check whether the Download Status column exists
            if COL_DOWNLOAD_STATUS not in df.columns:
                print(f"File {excel_file} has no '{COL_DOWNLOAD_STATUS}' column")
                continue

            def create_sort_key(value):
                if pd.isna(value) or str(value).strip() == "":
                    return 0
                elif str(value).strip() == STATUS_SUCCESS:
                    return 2
                else:
                    return 1

            df["sort_key"] = df[COL_DOWNLOAD_STATUS].apply(create_sort_key)

            # Sort by the sort key
            df_sorted = df.sort_values("sort_key", ascending=True)

            # Drop the auxiliary sort column
            df_sorted = df_sorted.drop("sort_key", axis=1)

            write_table(df_sorted, excel_file)
            print(f"Sorted file: {excel_file}")

        except Exception as e:
            print(f"Error processing file {excel_file}: {str(e)}")

    print("Sorting complete!")


def parse_args():
    parser = argparse.ArgumentParser(description="Sort input files by download status")
    parser.add_argument(
        "--input-format",
        choices=SUPPORTED_INPUT_FORMATS,
        default="auto",
        help="Choose input files from references/: excel, csv, or auto",
    )
    parser.add_argument(
        "--data-dir", default=REFERENCES_DIR, help="Directory containing input files"
    )
    return parser.parse_args()


def main():
    arguments = parse_args()
    sort_excel_by_download_status(arguments.data_dir, arguments.input_format)


if __name__ == "__main__":
    main()
