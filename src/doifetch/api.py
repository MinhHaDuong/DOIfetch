"""The public library API: ``from doifetch import Request, Result, fetch``.

Importing this module has no side effects: sources are imported lazily, one at
a time, when ``fetch`` reaches them.
"""

import importlib
from collections.abc import Callable, Iterable

from doifetch.sources.contract import Fetch, Kind, Request, Result

# When --source all (the default), try sources in this order until one succeeds.
# Open and institutional sources only: Crossref/Unpaywall/HAL (open access),
# ISTEX (licensed national archive) and EZproxy (institutional subscription;
# fails fast unless EZPROXY_BASE + EZPROXY_COOKIES are configured). Shadow
# libraries (scihub, libgen) are opt-in: pass --source scihub / --source libgen.
# "isbn" turns an ISBN into book DOIs and runs the sources above on them.
DEFAULT_ORDER = [
    "crossref",
    "unpaywall",
    "hal",
    "istex",
    "ezproxy",
    "isbn",
]


def _load(name: str) -> tuple[frozenset[Kind], Fetch]:
    """Import source ``name`` on demand: its ACCEPTS and its fetch."""
    module = importlib.import_module(f"doifetch.sources.{name}")
    return module.ACCEPTS, module.fetch


def cascade(
    req: Request,
    names: Iterable[str],
    load: Callable[[str], tuple[frozenset[Kind], Fetch]] = _load,
) -> Result:
    """Try the sources ``names`` in order and return the deciding result.

    The one cascade of the package (the library and the command line share it).
    Sources that do not accept ``req.kind`` are passed over. It stops at the
    first ``"success"`` or ``"skipped"`` (a valid file is already there);
    otherwise the last failure is returned, its error listing every tried
    source's reason when more than one was tried. Like a source, it never
    raises: a source that cannot be loaded or that raises counts as a failure.
    """
    result = Result("failed", "", error=f"no source accepts {req.kind}")
    failures = []
    for name in names:
        try:
            accepts, source_fetch = load(name)
            if req.kind not in accepts:
                continue
            result = source_fetch(req)
        except Exception as exc:  # noqa: BLE001 - never raise into the caller
            result = Result("failed", name, error=str(exc))
        if result.status != "failed":
            return result
        failures.append(f"{name}: {result.error or 'failed'}")
    if len(failures) > 1:
        return Result("failed", result.source, error="; ".join(failures))
    return result


def fetch(req: Request) -> Result:
    """Run the default cascade (``DEFAULT_ORDER``) for ``req``."""
    return cascade(req, DEFAULT_ORDER)
