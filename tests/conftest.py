from pathlib import Path
import sys

import pandas as pd
import pytest


from utils import write_table

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_DOIS = [
    ("10.1371/journal.pone.0001636", "Dunbar 2008 - Cognitive Constraints"),
    ("10.1038/d41586-019-02918-5", "Tollefson 2019 - Tracking Emissions"),
]


@pytest.fixture()
def sample_data_dir(tmp_path):
    """Create data dir with 2 DOIs in 3 formats: csv, xlsx, txt."""
    data_dir = tmp_path / "references"
    data_dir.mkdir()

    df = pd.DataFrame(
        [{"DOI": doi, "Article Title": title} for doi, title in SAMPLE_DOIS]
    )

    # CSV
    write_table(df, str(data_dir / "refs.csv"))

    # XLSX
    write_table(df, str(data_dir / "refs.xlsx"))

    # TXT
    lines = [f"doi:{doi}\t{title}" for doi, title in SAMPLE_DOIS]
    (data_dir / "refs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return data_dir
