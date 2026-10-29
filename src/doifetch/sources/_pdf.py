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

    The one place a source writes its file: the bytes are staged in
    ``req.path + ".part"``, checked, then moved into place atomically. Whatever
    happens (a bad body, a full disk, an exception), no ``.part`` and no partial
    ``req.path`` is left behind.
    """
    partial = req.path + ".part"
    try:
        with open(partial, "wb") as f:
            f.write(content)
        if not is_valid_pdf(partial):
            return Result("failed", source, error=broken)
        os.replace(partial, req.path)
        return Result("success", source, path=req.path)
    finally:
        if os.path.exists(partial):
            os.remove(partial)
