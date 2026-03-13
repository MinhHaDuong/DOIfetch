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
    """根据Download Status列对表格文件进行排序，空值排在前面，值为111的排在最后"""
    excel_files = list_table_files(data_directory, input_format)

    if not excel_files:
        print("未找到Excel文件")
        return

    print(f"找到 {len(excel_files)} 个Excel文件")

    # 处理每个Excel文件
    for excel_file in excel_files:
        try:
            df = read_table(excel_file)

            # 检查是否存在Download Status列
            if COL_DOWNLOAD_STATUS not in df.columns:
                print(f"文件 {excel_file} 中没有找到'{COL_DOWNLOAD_STATUS}'列")
                continue

            def create_sort_key(value):
                if pd.isna(value) or str(value).strip() == "":
                    return 0
                elif str(value).strip() == STATUS_SUCCESS:
                    return 2
                else:
                    return 1

            df["sort_key"] = df[COL_DOWNLOAD_STATUS].apply(create_sort_key)

            # 根据排序键进行排序
            df_sorted = df.sort_values("sort_key", ascending=True)

            # 删除辅助排序列
            df_sorted = df_sorted.drop("sort_key", axis=1)

            write_table(df_sorted, excel_file)
            print(f"已排序文件: {excel_file}")

        except Exception as e:
            print(f"处理文件 {excel_file} 时出错: {str(e)}")

    print("排序完成!")


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
