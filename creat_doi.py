import argparse
import pandas as pd
import os

from table_utils import (
    SUPPORTED_INPUT_FORMATS,
    list_table_files,
    read_table,
    write_table,
)


def generate_doi_link(doi):
    """根据DOI生成论文链接"""
    if doi and str(doi).strip() != "":
        # 清理DOI，移除可能的前缀
        doi = str(doi).strip().replace("doi:", "").replace("DOI:", "")
        return f"https://doi.org/{doi}"
    return "No DOI"


def update_excel_doi_column(excel_file_path):
    """更新单个Excel文件的DOI Link列"""
    try:
        df = read_table(excel_file_path)

        # 确保有DOI列
        if "DOI" not in df.columns:
            print(f"警告: 文件 {excel_file_path} 中没有找到DOI列")
            return False

        # 确保有Article Title列
        if "Article Title" not in df.columns:
            print(f"警告: 文件 {excel_file_path} 中没有找到Article Title列")
            return False

        # 确保有DOI Link列（第三列）
        if len(df.columns) < 3:
            # 如果列数少于3列，添加DOI Link列
            df.insert(2, "DOI Link", "")
        elif df.columns[2] != "DOI Link":
            # 如果第三列不是DOI Link，添加新的DOI Link列
            df.insert(2, "DOI Link", "")

        # 为每一行生成DOI链接
        for index, row in df.iterrows():
            doi = row.get("DOI", "")
            doi_link = generate_doi_link(doi)
            df.at[index, "DOI Link"] = doi_link

        write_table(df, excel_file_path)
        print(f"已更新文件: {excel_file_path}")
        return True

    except Exception as e:
        print(f"处理文件 {excel_file_path} 时出错: {str(e)}")
        return False


def update_multiple_excel_files(data_directory="data", input_format="auto"):
    """批量更新目录下所有表格文件的DOI Link列"""
    excel_files = list_table_files(data_directory, input_format)

    if not excel_files:
        print(f"在目录 {data_directory} 中没有找到Excel文件")
        return

    print(f"找到 {len(excel_files)} 个Excel文件")

    # 处理每个Excel文件
    success_count = 0
    for excel_file in excel_files:
        if update_excel_doi_column(excel_file):
            success_count += 1

    print(f"\n处理完成: {success_count}/{len(excel_files)} 个文件成功更新")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate DOI links for input files")
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


if __name__ == "__main__":
    arguments = parse_args()
    update_multiple_excel_files(arguments.data_dir, arguments.input_format)
