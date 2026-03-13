import argparse

from config import COL_DOI, COL_DOI_LINK, COL_TITLE, DOI_URL_BASE, REFERENCES_DIR
from table_utils import (
    SUPPORTED_INPUT_FORMATS,
    list_table_files,
    read_table,
    write_table,
)


def generate_doi_link(doi):
    """Generate a paper link from a DOI."""
    if doi and str(doi).strip() != "":
        # Clean DOI, remove possible prefix
        doi = str(doi).strip().replace("doi:", "").replace("DOI:", "")
        return f"{DOI_URL_BASE}{doi}"
    return "No DOI"


def update_excel_doi_column(excel_file_path):
    """Update the DOI Link column for a single table file."""
    try:
        df = read_table(excel_file_path)

        # Ensure DOI column exists
        if COL_DOI not in df.columns:
            print(f"Warning: DOI column not found in {excel_file_path}")
            return False

        # Ensure Article Title column exists
        if COL_TITLE not in df.columns:
            print(f"Warning: Article Title column not found in {excel_file_path}")
            return False

        # Ensure DOI Link column exists (third column)
        if len(df.columns) < 3:
            # If fewer than 3 columns, add DOI Link column
            df.insert(2, COL_DOI_LINK, "")
        elif df.columns[2] != COL_DOI_LINK:
            # If third column is not DOI Link, add a new DOI Link column
            df.insert(2, COL_DOI_LINK, "")

        # Generate DOI link for each row
        for index, row in df.iterrows():
            doi = row.get(COL_DOI, "")
            doi_link = generate_doi_link(doi)
            df.at[index, COL_DOI_LINK] = doi_link

        write_table(df, excel_file_path)
        print(f"Updated file: {excel_file_path}")
        return True

    except Exception as e:
        print(f"Error processing file {excel_file_path}: {str(e)}")
        return False


def update_multiple_excel_files(data_directory=REFERENCES_DIR, input_format="auto"):
    """Batch update the DOI Link column for all table files in a directory."""
    excel_files = list_table_files(data_directory, input_format)

    if not excel_files:
        print(f"No table files found in directory {data_directory}")
        return

    print(f"Found {len(excel_files)} table file(s)")

    # Process each file
    success_count = 0
    for excel_file in excel_files:
        if update_excel_doi_column(excel_file):
            success_count += 1

    print(f"\nDone: {success_count}/{len(excel_files)} file(s) successfully updated")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate DOI links for input files")
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


if __name__ == "__main__":
    arguments = parse_args()
    update_multiple_excel_files(arguments.data_dir, arguments.input_format)
