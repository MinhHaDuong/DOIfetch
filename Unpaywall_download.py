import argparse
import requests
import os
import warnings
from tqdm import tqdm
import urllib3

from config import (
    COL_DOWNLOAD_STATUS,
    PAPERS_DIR,
    REFERENCES_DIR,
    STATUS_SUCCESS,
    UNPAYWALL_EMAIL,
)
from table_utils import (
    SUPPORTED_INPUT_FORMATS,
    list_table_files,
    read_doi_from_table,
    read_table,
    write_table,
)

# Ignore xlwt deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")
# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def download_papers_from_dois(doi_data, output_dir=PAPERS_DIR):
    """Download paper PDFs from a DOI list and update the table status."""
    os.makedirs(output_dir, exist_ok=True)

    # doi_data is a list of tuples, each containing (doi, file_path, row_index)
    for doi, file_path, row_index in tqdm(doi_data, desc="Download progress", unit="paper"):
        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
            response = requests.get(url).json()

            if "best_oa_location" in response and response["best_oa_location"]:
                pdf_url = response["best_oa_location"]["url_for_pdf"]
                if pdf_url:
                    paper = requests.get(pdf_url, verify=False)
                    pdf_path = os.path.join(output_dir, f"{doi.replace('/', '_')}.pdf")
                    with open(pdf_path, "wb") as f:
                        f.write(paper.content)
                    print(f"Downloaded: {doi}")

                    # Update download status in the table file
                    df = read_table(file_path)
                    if COL_DOWNLOAD_STATUS not in df.columns:
                        df[COL_DOWNLOAD_STATUS] = ""
                    df.at[row_index, COL_DOWNLOAD_STATUS] = STATUS_SUCCESS
                    write_table(df, file_path)
                else:
                    print(f"No PDF found for {doi}")
            else:
                print(f"No open access version for {doi}")
        except Exception as e:
            print(f"Error downloading {doi}: {str(e)}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download open-access papers via Unpaywall"
    )
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
    args = parse_args()
    input_files = list_table_files(args.data_dir, args.input_format)

    all_doi_data = []

    for file_path in input_files:
        dois, df = read_doi_from_table(file_path)
        if df is not None:  # Ensure the DataFrame was read successfully
            doi_data = [(doi, file_path, row_index) for doi, row_index in dois]
            all_doi_data.extend(doi_data)

    # Download paper PDFs
    download_papers_from_dois(all_doi_data)


if __name__ == "__main__":
    main()
