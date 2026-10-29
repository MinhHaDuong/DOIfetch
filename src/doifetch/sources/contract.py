"""The fetcher contract: data plus one function signature, no base class.

A source is a plain module exposing three names:

- ``NAME: str``: the registry key and the ``--source`` choice;
- ``ACCEPTS: frozenset[Kind]``: the identifier kinds it can fetch;
- ``fetch(req: Request) -> Result``.

Rules a ``fetch`` follows:

- it never raises into the fetch loop: errors become ``status="failed"`` with a
  reason in ``error``;
- it writes only ``req.path``, whose name the caller decided, and never leaves a
  partial file behind;
- it returns ``"success"`` only for a file that passed the PDF check;
- it returns ``"skipped"`` when ``req.path`` already holds a valid PDF.

Enforcement is by the type checker and the conformance tests, not inheritance.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Kind = Literal["doi", "isbn", "url", "title"]
Status = Literal["success", "failed", "skipped"]


@dataclass(frozen=True)
class Request:
    """What to fetch (a bare DOI, ISBN, URL or title to search for) and where to put it."""

    kind: Kind
    identifier: str
    path: str


@dataclass(frozen=True)
class Result:
    """Outcome of one fetch; ``path`` is the file written when there is one."""

    status: Status
    source: str
    path: str | None = None
    error: str | None = None


Fetch = Callable[[Request], Result]
