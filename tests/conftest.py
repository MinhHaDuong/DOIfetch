from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_DOIS = [
    ("10.1371/journal.pone.0001636", "Dunbar 2008 - Cognitive Constraints"),
    ("10.1038/d41586-019-02918-5", "Tollefson 2019 - Tracking Emissions"),
]


@pytest.fixture()
def sample_data_dir(tmp_path):
    """Create data dir with 2 DOIs in a .txt list."""
    data_dir = tmp_path / "references"
    data_dir.mkdir()

    # TXT
    lines = [f"doi:{doi}\t{title}" for doi, title in SAMPLE_DOIS]
    (data_dir / "refs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return data_dir
