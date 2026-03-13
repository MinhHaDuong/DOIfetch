import pandas as pd
import os

from config import REFERENCES_DIR


def main():
    data_dir = REFERENCES_DIR
    for file_name in os.listdir(data_dir):
        if file_name.endswith(".xls"):
            # Read the .xls file
            xls_path = os.path.join(data_dir, file_name)
            df = pd.read_excel(xls_path)

            # Save as .xlsx file
            xlsx_file_name = file_name.replace(".xls", ".xlsx")
            xlsx_path = os.path.join(data_dir, xlsx_file_name)
            df.to_excel(xlsx_path, index=False)

            # Delete the original .xls file
            os.remove(xls_path)
            print(f"Converted {file_name} to {xlsx_file_name}")


if __name__ == "__main__":
    main()
