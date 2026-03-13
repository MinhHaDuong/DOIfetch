import argparse
import requests
import os
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
            doi = row.get("DOI", "")
            if doi:
                dois.append((doi, index))

    except Exception as e:
        print(f"读取Excel文件 {file_path} 时出错: {str(e)}")
        return [], None

    print(f"共提取到 {len(dois)} 个DOI")
    return dois, df  # 返回DOI列表和DataFrame


def get_pdf_url_from_crossref(doi):
    """使用Crossref API获取PDF下载链接"""
    try:
        # Crossref API请求
        api_url = f"https://api.crossref.org/works/{doi}"
        response = requests.get(api_url, verify=False)

        if response.status_code != 200:
            print(f"Crossref API请求失败，状态码: {response.status_code}")
            return None

        data = response.json()
        message = data.get("message", {})

        # 查找PDF链接
        links = message.get("link", [])
        pdf_links = [
            link["URL"]
            for link in links
            if link.get("content-type") == "application/pdf"
            and link.get("content-version") == "vor"
        ]

        return pdf_links[0] if pdf_links else None

    except Exception as e:
        print(f"获取 {doi} 的PDF链接时出错: {str(e)}")
        return None


def download_papers_from_dois(doi_data, output_dir="papers"):
    """根据DOI列表下载论文PDF并更新Excel状态"""
    os.makedirs(output_dir, exist_ok=True)

    # doi_data 是一个元组列表，每个元组包含 (doi, file_path, row_index)
    for doi, file_path, row_index in tqdm(doi_data, desc="下载进度", unit="paper"):
        try:
            # 使用Crossref获取PDF链接
            pdf_url = get_pdf_url_from_crossref(doi)

            if pdf_url:
                paper = requests.get(pdf_url, verify=False)

                # 检查是否成功获取PDF
                if (
                    paper.status_code == 200
                    and paper.headers["Content-Type"] == "application/pdf"
                ):
                    # 生成安全文件名（替换特殊字符）
                    safe_doi = doi.replace("/", "_").replace(":", "_")
                    pdf_path = os.path.join(output_dir, f"{safe_doi}.pdf")

                    with open(pdf_path, "wb") as f:
                        f.write(paper.content)
                    print(f"成功下载: {doi}")

                    # 更新Excel文件中的下载状态
                    df = read_table(file_path)
                    if "Download Status" not in df.columns:
                        df["Download Status"] = ""
                    df.at[row_index, "Download Status"] = "成功"
                    write_table(df, file_path)
                else:
                    print(f"无效的PDF响应: {doi}")
            else:
                print(f"未找到开放获取PDF: {doi}")
        except Exception as e:
            print(f"下载 {doi} 时出错: {str(e)}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download open-access papers via Crossref"
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

    # 用于存储所有DOI数据的列表 (doi, file_path, row_index)
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
