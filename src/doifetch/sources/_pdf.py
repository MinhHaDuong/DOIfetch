"""Shared file steps of the contract for sources that download a PDF body."""

import os

from doifetch.pdf_utils import is_valid_pdf
from doifetch.sources.contract import Request, Result


def already_there(req: Request, source: str) -> Result | None:
    """``skipped`` when ``req.path`` holds a valid PDF; drop a broken leftover."""
    if not os.path.exists(req.path):
        return None
    if is_valid_pdf(req.path):
        return Result("skipped", source, path=req.path)
    os.remove(req.path)
    return None


def save_pdf(req: Request, source: str, content: bytes, broken: str) -> Result:
    """Write ``content`` to ``req.path``; ``success`` only if it is a valid PDF.

    A file that fails the check is removed, so no partial file is left behind.
    """
    try:
        with open(req.path, "wb") as f:
            f.write(content)
    except BaseException:
        if os.path.exists(req.path):
            os.remove(req.path)  # a write that died midway leaves nothing
        raise
    if not is_valid_pdf(req.path):
        os.remove(req.path)
        return Result("failed", source, error=broken)
    return Result("success", source, path=req.path)
