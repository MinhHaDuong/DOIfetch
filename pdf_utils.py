import re

MAX_NAME_LENGTH = 120


def clean_filename(title):
    """Remove illegal filename characters and truncate."""
    illegal_chars = r'[\\/:*?"<>|]'
    return re.sub(illegal_chars, "", title)[:MAX_NAME_LENGTH]


def is_valid_pdf(file_path):
    """Check if a file is a valid PDF by magic number and minimal size."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                return False
            f.seek(0, 2)
            size = f.tell()
            if size < 1000:
                return False
        return True
    except OSError:
        return False
