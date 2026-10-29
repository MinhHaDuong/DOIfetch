"""Adapter from the legacy ``fetch_pdf(doi, title, output_dir)`` functions.

Temporary: each source rewrite drops its use of this helper.
"""

import os
from collections.abc import Callable

from doifetch.sources.contract import Request, Result


def run_legacy(name: str, legacy: Callable[..., dict], req: Request) -> Result:
    """Call ``legacy`` for ``req`` and map its dict onto a ``Result``."""
    output_dir, file_name = os.path.split(req.path)
    title = file_name[: -len(".pdf")] if file_name.endswith(".pdf") else file_name
    slot = f"isbn:{req.identifier}" if req.kind == "isbn" else req.identifier
    try:
        out = legacy(slot, title, output_dir or ".")
    except Exception as exc:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", name, error=str(exc))
    written = out.get("file_name")
    return Result(
        out["status"],
        name,
        path=os.path.join(output_dir, written) if written else None,
        error=out.get("error"),
    )
