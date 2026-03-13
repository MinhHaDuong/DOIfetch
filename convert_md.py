import argparse
import pandas as pd
import os

from table_utils import SUPPORTED_INPUT_FORMATS, list_table_files, read_table


def convert_excel_to_markdown(excel_file_path, markdown_file_path):
    """将单个Excel文件转换为指定格式的Markdown"""
    try:
        df = read_table(excel_file_path)

        # 创建新的Markdown内容
        markdown_lines = []

        # 遍历每一行数据
        for index, row in df.iterrows():
            title = row.get("Article Title", "")
            doi_link = row.get("DOI Link", "")
            download_status = row.get(
                "下载状态", "未下载"
            )  # 获取下载状态，默认为'未下载'

            # 确保标题和链接都存在
            if pd.notna(title) and pd.notna(doi_link) and title and doi_link:
                # 按照指定格式生成行，包含下载状态
                markdown_line = f"- **{title}** ([link]({doi_link}))-{download_status}"
                markdown_lines.append(markdown_line)

        # 将所有行连接成一个字符串
        markdown_content = "\n".join(markdown_lines)

        # 写入Markdown文件
        with open(markdown_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"已转换: {excel_file_path} -> {markdown_file_path}")
        return True
    except Exception as e:
        print(f"转换失败: {excel_file_path} - {str(e)}")
        return False


def convert_all_excel_files(data_directory="references", input_format="auto"):
    """将data目录下所有表格文件转换为指定格式的Markdown"""
    os.makedirs("data_md", exist_ok=True)
    input_files = list_table_files(data_directory, input_format)

    if not input_files:
        print("未找到表格文件")
        return

    print(f"找到 {len(input_files)} 个表格文件")

    for input_file in input_files:
        filename = os.path.basename(input_file)
        name, ext = os.path.splitext(filename)
        markdown_file = os.path.join("data_md", f"{name}.md")
        convert_excel_to_markdown(input_file, markdown_file)

    print("转换完成!")


def parse_args():
    parser = argparse.ArgumentParser(description="Convert data files to markdown")
    parser.add_argument(
        "--input-format",
        choices=SUPPORTED_INPUT_FORMATS,
        default="auto",
        help="Choose input files from references/: excel, csv, or auto",
    )
    parser.add_argument(
        "--data-dir", default="references", help="Directory containing input files"
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    convert_all_excel_files(arguments.data_dir, arguments.input_format)
