import argparse
import pandas as pd
import os

from config import COL_DOI_LINK, COL_DOWNLOAD_STATUS, COL_TITLE, MARKDOWN_DIR, REFERENCES_DIR
from table_utils import SUPPORTED_INPUT_FORMATS, list_table_files, read_table


def convert_table_to_markdown(table_file_path, markdown_file_path):
    """Convert a single table file to the specified Markdown format."""
    try:
        df = read_table(table_file_path)

        # Create new Markdown content
        markdown_lines = []

        # Iterate over each row
        for index, row in df.iterrows():
            title = row.get(COL_TITLE, "")
            doi_link = row.get(COL_DOI_LINK, "")
            download_status = row.get(
                COL_DOWNLOAD_STATUS, ""
            )  # Get download status, default to empty string

            # Ensure both title and link are present
            if pd.notna(title) and pd.notna(doi_link) and title and doi_link:
                # Generate line in the specified format, including download status
                markdown_line = f"- **{title}** ([link]({doi_link}))-{download_status}"
                markdown_lines.append(markdown_line)

        # Join all lines into a single string
        markdown_content = "\n".join(markdown_lines)

        # Write to Markdown file
        with open(markdown_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"Converted: {table_file_path} -> {markdown_file_path}")
        return True
    except Exception as e:
        print(f"Conversion failed: {table_file_path} - {str(e)}")
        return False


def convert_all_files(data_directory=REFERENCES_DIR, input_format="auto"):
    """Convert all table files in the data directory to the specified Markdown format."""
    os.makedirs(MARKDOWN_DIR, exist_ok=True)
    input_files = list_table_files(data_directory, input_format)

    if not input_files:
        print("No table files found")
        return

    print(f"Found {len(input_files)} table file(s)")

    for input_file in input_files:
        filename = os.path.basename(input_file)
        name, ext = os.path.splitext(filename)
        markdown_file = os.path.join(MARKDOWN_DIR, f"{name}.md")
        convert_table_to_markdown(input_file, markdown_file)

    print("Conversion complete!")


def parse_args():
    parser = argparse.ArgumentParser(description="Convert data files to markdown")
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
    convert_all_files(arguments.data_dir, arguments.input_format)
