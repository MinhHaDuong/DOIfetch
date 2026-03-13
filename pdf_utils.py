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
    except Exception:
        return False
