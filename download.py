import argparse
import os
import random
import re
import threading
import time
from queue import Queue
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import *
from table_utils import (
    SUPPORTED_INPUT_FORMATS,
    list_table_files,
    read_table,
    write_table,
)


# 清理非法文件名字符
def clean_filename(title):
    illegal_chars = r'[\\/:*?"<>|]'
    return re.sub(illegal_chars, "", title)[:120]  # 限制文件名长度


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download papers from Sci-Hub using DOI/title or batch input files"
    )
    parser.add_argument("--doi", help="Download a single paper by DOI")
    parser.add_argument(
        "--title", help="Title for a single-paper download or title-only search"
    )
    parser.add_argument(
        "--input-format",
        choices=SUPPORTED_INPUT_FORMATS,
        default="auto",
        help="Choose input files from data/: excel, csv, or auto",
    )
    parser.add_argument(
        "--data-dir", default="data", help="Directory containing batch input files"
    )
    return parser.parse_args()


def download_paper(doi, title, output_dir="output"):
    doi_link = f"https://doi.org/{doi}" if doi else "No DOI"
    safe_title = title if title else f"Unknown_{int(time.time())}"
    file_name = f"{clean_filename(safe_title)}.pdf"
    file_path = os.path.join(output_dir, file_name)

    if os.path.exists(file_path):
        return {
            "status": "skipped",
            "doi": doi,
            "title": safe_title,
            "doi_link": doi_link,
            "file_name": file_name,
        }

    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    last_error = ""

    for _ in range(RETRY_COUNT):
        domain = random.choice(SCI_HUB_DOMAINS)
        try:
            if doi:
                response = requests.get(
                    f"{domain}{doi}", headers=HEADERS, timeout=TIMEOUT
                )
            else:
                search_url = f"{domain}?s={quote(safe_title)}"
                response = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT)

            soup = BeautifulSoup(response.content, "html.parser")
            iframe = soup.find("iframe") or soup.find("embed")
            pdf_url = iframe["src"] if iframe else None

            if not pdf_url or not pdf_url.startswith("http"):
                last_error = (
                    f"{doi or safe_title} | 错误: 未找到PDF链接 | 域名: {domain}"
                )
                continue

            pdf_response = requests.get(
                pdf_url, headers=HEADERS, stream=True, timeout=TIMEOUT
            )
            with open(file_path, "wb") as file_handle:
                for chunk in pdf_response.iter_content(chunk_size=1024):
                    if chunk:
                        file_handle.write(chunk)

            return {
                "status": "success",
                "doi": doi,
                "title": safe_title,
                "doi_link": doi_link,
                "file_name": file_name,
            }
        except Exception as exc:
            last_error = f"{doi or safe_title} | 错误: {str(exc)[:50]} | 域名: {domain}"

    return {
        "status": "failed",
        "doi": doi,
        "title": safe_title,
        "doi_link": doi_link,
        "file_name": file_name,
        "error": last_error or f"{doi or safe_title} | 错误: 未知错误",
    }


def load_download_tasks(file_paths):
    download_tasks = []
    skipped_count = 0

    for file_path in file_paths:
        print(f"正在读取文件: {file_path}")
        try:
            dataframe = read_table(file_path)
            for _, row in dataframe.iterrows():
                doi = row.get("DOI", "")
                title = row.get("Article Title", f"Unknown_{int(time.time())}")

                if pd.isna(doi) or not str(doi).strip():
                    if pd.isna(title) or not str(title).strip():
                        print("跳过无效记录: DOI和标题都为空")
                        skipped_count += 1
                        continue

                    print(f"添加无DOI记录: {title}")
                    download_tasks.append(("", title))
                    continue

                doi = str(doi).strip()
                if not validate_doi(doi):
                    print(f"跳过格式无效的DOI: {doi} | {title}")
                    skipped_count += 1
                    continue

                download_tasks.append((doi, title))
        except Exception as exc:
            print(f"读取文件 {file_path} 失败: {str(exc)}")

    return download_tasks, skipped_count


def update_source_files(file_paths, successful_records):
    for file_path in file_paths:
        try:
            dataframe = read_table(file_path)

            if "DOI Link" not in dataframe.columns:
                dataframe.insert(2, "DOI Link", "")

            if "Download Status" not in dataframe.columns:
                dataframe["Download Status"] = ""

            for title, doi_link in successful_records:
                if not doi_link or doi_link == "No DOI":
                    continue

                mask = dataframe["Article Title"] == title
                dataframe.loc[mask, "DOI Link"] = doi_link
                dataframe.loc[mask, "Download Status"] = 111

            write_table(dataframe, file_path)
            print(f"已更新文件: {file_path}")
        except Exception as exc:
            print(f"更新文件 {file_path} 失败: {str(exc)}")


def write_logs(success_log, error_log, failed_dois):
    timestamp = int(time.time())
    with (
        open(f"logs/success_{timestamp}.log", "w", encoding="utf-8") as success_file,
        open(f"logs/error_{timestamp}.log", "w", encoding="utf-8") as error_file,
        open(
            "logs/failed_dois.csv", "w", encoding="utf-8", errors="ignore"
        ) as failed_file,
    ):
        success_file.writelines(success_log)
        error_file.writelines(error_log)
        failed_file.write("DOI,Title\n")
        for doi, title in failed_dois:
            failed_file.write(f"{doi},{title}\n")


def handle_single_download(args):
    if args.doi:
        doi = str(args.doi).strip()
        if not validate_doi(doi):
            raise ValueError(f"无效的DOI格式: {args.doi}")
    else:
        doi = ""

    title = args.title.strip() if args.title else f"Unknown_{int(time.time())}"
    result = download_paper(doi, title)

    if result["status"] == "failed":
        print(f"下载失败: {result['error']}")
        return 1

    if result["status"] == "skipped":
        print(f"已跳过已存在文件: {result['file_name']}")
    else:
        print(f"下载成功: {result['file_name']}")

    return 0


# 文献下载核心函数
def download_worker(queue, success_log, successful_records, error_log, failed_dois):
    while not queue.empty():
        doi, title = queue.get()
        try:
            result = download_paper(doi, title)
            if result["status"] == "failed":
                failed_dois.append((doi, title))
                error_log.append(f"[FAILED] {result['error']}\n")
            else:
                status_label = "SKIPPED" if result["status"] == "skipped" else "SUCCESS"
                success_log.append(f"[{status_label}] {doi} | {result['file_name']}\n")
                if doi:
                    successful_records.append((result["title"], result["doi_link"]))
        except Exception as exc:
            error_msg = f"下载失败: {doi} | 错误: {str(exc)}"
            error_log.append(f"[ERROR] {error_msg}\n")
            failed_dois.append((doi, title))
            print(error_msg)
        queue.task_done()


def validate_doi(doi):
    """验证DOI格式是否正确"""
    doi = doi.strip()
    if not doi:
        return False
    # 移除可能的DOI前缀
    doi = doi.replace("doi:", "").replace("DOI:", "").strip()
    # 检查基本格式
    # 当前验证正则表达式
    return re.match(r"^10\.\d+\/.+$", doi) is not None  # 允许路径中的特殊字符


# 主控流程
def main():
    args = parse_args()
    os.makedirs("output", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    if args.doi or args.title:
        return handle_single_download(args)

    success_log = []
    successful_records = []
    error_log = []
    failed_dois = []

    input_files = list_table_files(args.data_dir, args.input_format)
    doi_queue = Queue()

    download_tasks, skipped_count = load_download_tasks(input_files)
    for doi, title in download_tasks:
        doi_queue.put((doi, title))

    print(f"有效DOI数量: {doi_queue.qsize()} | 跳过记录数: {skipped_count}")

    # 启动线程池
    threads = []
    # 修改队列检查逻辑，确保在队列中有任务时才启动线程
    if doi_queue.qsize() > 0:
        for _ in range(min(MAX_THREADS, doi_queue.qsize())):
            t = threading.Thread(
                target=download_worker,
                args=(
                    doi_queue,
                    success_log,
                    successful_records,
                    error_log,
                    failed_dois,
                ),
            )
            t.daemon = True
            t.start()
            threads.append(t)

        # 进度监控
        print(f"▶️ 开始下载 {doi_queue.qsize()} 篇文献 | 线程数: {MAX_THREADS}")
        while any(t.is_alive() for t in threads):
            print(
                f"⏳ 剩余任务: {doi_queue.qsize()} | 成功: {len(successful_records)} | 失败: {len(failed_dois)}"
            )
            time.sleep(10)
    else:
        print("没有找到需要处理的文献记录，程序退出")
        return 0

    write_logs(success_log, error_log, failed_dois)
    update_source_files(input_files, successful_records)

    success_count = len(successful_records)
    failed_count = len(failed_dois)
    total_count = success_count + failed_count

    if total_count > 0:
        success_rate = success_count * 100 / total_count
        print(f"✅ 任务完成! 成功率: {success_rate:.1f}%")
    else:
        print("✅ 任务完成! 没有可处理的任务")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
