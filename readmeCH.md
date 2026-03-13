# DoiHarvest

一个用于从Sci-Hub,Crossref,Unpaywall批量下载学术论文PDF的工具。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
## 项目简介

DoiHarvest是一个自动化工具，旨在帮助研究人员和学者批量下载学术论文PDF文件。它支持从Sci-Hub,Crossref,Unpaywall API获取论文，具有多线程下载、重试机制和智能域名轮询等功能，以提高下载效率和成功率。此外，该工具还提供了Excel到Markdown的转换功能，方便用户管理和分享文献信息。


## 功能特点

- 支持从Excel、CSV或文本参考文件中读取文献DOI和标题信息
- 自动从Sci-Hub下载论文PDF
- 支持多线程下载以提高效率
- 支持重试机制和随机延迟以避免被封禁
- 自动更新Excel文件中的DOI链接
- 支持将Excel文件转换为Markdown格式方便手动下载
- 提供下载状态检查功能
- 支持通过Crossref API下载开放获取论文
- 支持通过Unpaywall API下载开放获取论文

## 文件说明

- `download.py`: 主要的下载脚本，从Sci-Hub下载论文
- `config.py`: 配置文件，包含Sci-Hub域名池和下载参数
- `convertxls.py`: 将.xls文件转换为.xlsx格式
- `creat_doi.py`: 为Excel文件生成DOI链接
- `convert_md.py`: 将Excel文件转换为Markdown格式
- `Crossref_download.py`: 使用Crossref API下载开放获取论文
- `Unpaywall_download.py`: 使用Unpaywall API下载开放获取论文
- `pyproject.toml`: `uv` 使用的项目元数据和依赖配置

## 配置说明

在`config.py`中可以调整以下参数：

- `SCI_HUB_DOMAINS`: Sci-Hub域名池，用于轮询避免封禁
- `MAX_THREADS`: 并发下载线程数
- `RETRY_COUNT`: 下载失败重试次数
- `TIMEOUT`: 请求超时时间
- `MIN_DELAY`和`MAX_DELAY`: 随机延迟范围

## 目录结构

```
.
├── references/           # 存放待处理的参考文献文件
├── data_md/              # 存放转换后的Markdown文件
├── logs/                 # 存放download.py日志
├── papers/               # 存放所有下载的PDF文件
├── download.py           # 从Sci-Hub下载论文（可能需要开代理）
├── config.py             # 配置文件
├── convertxls.py         # xls转xlsx工具
├── creat_doi.py          # 在Excel表格生成DOI链接
├── convert_md.py         # Excel转Markdown工具
├── Crossref_download.py  # Crossref下载工具（无需代理）
├── Unpaywall_download.py # Unpaywall下载工具（无需代理）
├── pyproject.toml        # uv 使用的项目元数据和依赖文件
└── README.md
```
## 使用 UV 运行

本仓库使用 `uv` 和 `pyproject.toml` 作为依赖来源。不要使用 `pip`，也不要手动创建虚拟环境。请在仓库根目录使用 `uv run` 运行命令，`uv` 会自动解析并安装所需依赖。

```
uv run python download.py --help
```

## 使用方法

1. 将包含文献信息的输入文件放入`references`目录
   - 输入文件至少应包含 `DOI` 列
2. 运行`download.py`开始下载文献
   ```
   uv run python download.py
   ```
   如果只想从命令行下载单篇论文：
   ```
   uv run python download.py --doi 10.1000/example --title "Example Paper"
   ```
3. 下载的PDF文件将保存在`papers`目录中
4. 如果输入文件是CSV而不是Excel，可以添加 `--input-format csv`
   ```
   uv run python download.py --input-format csv
   uv run python Crossref_download.py --input-format csv
   ```
   也可以使用文本参考文件（`--input-format txt`），格式为制表符分隔：
   ```
   doi:10.1080/03085140903020580	作者 2009 - 标题
   url:https://example.com/doc.pdf	文档名称
   isbn:9780674009691	作者 1998 - 书名
   # 注释行会被忽略
   ```
   仅处理 `doi:` 条目；`url:`、`isbn:` 和 `#` 行会被跳过。文本文件为只读输入（不会回写下载状态）。
5. 下载状态会自动更新到原始输入文件中（建议删除已经下载完成的行，减少`Crossref_download.py`和`Unpaywall_download.py`的下载量）
6. 运行`Crossref_download.py`或`Unpaywall_download.py`开始下载文献
   ```
   uv run python Crossref_download.py
   ```
   或
   ```
   uv run python Unpaywall_download.py
   ```
7. 如下载失败需要人工下载，可运行`creat_doi.py`生成DOI链接，并更新到输入文件中的`DOI Link`列
   ```
   uv run python creat_doi.py
   ```
9. 运行`convert_md.py`将输入文件转换为Markdown格式，方便手动下载
   ```
   uv run python convert_md.py
   ```

## 测试

在仓库根目录运行测试：

```
uv run --group dev pytest
```


## 注意事项

- 请在仓库根目录使用 `uv run`，依赖由 `pyproject.toml` 管理
- 请遵守相关法律法规和学术道德，仅用于个人学习和研究
- 下载过程中可能会遇到网络问题或Sci-Hub访问限制
- 建议适当调整并发数和延迟时间以避免被封禁


## 注意事项
- 所有下载脚本会自动跳过已经下载在papers的文件，不会重复下载
- 请遵守相关法律法规和学术道德，仅用于个人学习和研究
- 下载过程中可能会遇到网络问题或Sci-Hub访问限制
- 建议适当调整并发数和延迟时间以避免被封禁
- 部分文献可能因版权保护无法下载
- 请在仓库根目录使用 `uv run`，依赖由 `pyproject.toml` 管理
