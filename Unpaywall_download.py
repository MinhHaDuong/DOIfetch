import argparse
import requests
import os
import pandas as pd
import warnings
from tqdm import tqdm
import urllib3

from table_utils import (
    SUPPORTED_INPUT_FORMATS,
    list_table_files,
    read_table,
    write_table,
)

# 忽略xlwt弃用警告
warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")
# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def read_doi_from_excel(file_path):
    """从Excel文件中读取DOI列表"""
    dois = []
    try:
        df = read_table(file_path)
        print(f"成功读取Excel文件: {file_path}, 共 {len(df)} 行数据")

        # 添加下载状态列（如果不存在）
        if "Download Status" not in df.columns:
            df["Download Status"] = ""

        # 遍历每一行，提取DOI
        for index, row in df.iterrows():
            # 假设DOI在'DOI Link'列中，如果没有这一列，请根据实际情况调整
            doi = row.get("DOI", "")
            if doi:
                dois.append((doi, index))

    except Exception as e:
        print(f"读取Excel文件 {file_path} 时出错: {str(e)}")
        return [], None

    print(f"共提取到 {len(dois)} 个DOI")
    return dois, df  # 返回DOI列表和DataFrame


def download_papers_from_dois(doi_data, output_dir="papers"):
    """根据DOI列表下载论文PDF并更新Excel状态"""
    os.makedirs(output_dir, exist_ok=True)

    # doi_data 是一个元组列表，每个元组包含 (doi, file_path, row_index)
    for doi, file_path, row_index in tqdm(doi_data, desc="下载进度", unit="paper"):
        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email=email@163.com"
            response = requests.get(url).json()

            if "best_oa_location" in response and response["best_oa_location"]:
                pdf_url = response["best_oa_location"]["url_for_pdf"]
                if pdf_url:
                    paper = requests.get(pdf_url, verify=False)
                    with open(f"{output_dir}/{doi.replace('/', '_')}.pdf", "wb") as f:
                        f.write(paper.content)
                    print(f"Downloaded: {doi}")

                    # 更新Excel文件中的下载状态
                    df = read_table(file_path)
                    if "Download Status" not in df.columns:
                        df["Download Status"] = ""
                    df.at[row_index, "Download Status"] = "111"
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
        help="Choose input files from data/: excel, csv, or auto",
    )
    parser.add_argument(
        "--data-dir", default="data", help="Directory containing input files"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_files = list_table_files(args.data_dir, args.input_format)

    all_doi_data = []

    for file_path in input_files:
        dois, df = read_doi_from_excel(file_path)
        if df is not None:  # 确保DataFrame读取成功
            doi_data = [(doi, file_path, row_index) for doi, row_index in dois]
            all_doi_data.extend(doi_data)

    # 下载论文PDF
    download_papers_from_dois(all_doi_data)


if __name__ == "__main__":
    main()
