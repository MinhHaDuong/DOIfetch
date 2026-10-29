"""The public library API: ``from doifetch import Request, Result, fetch``.

Importing this module has no side effects: sources are imported lazily, one at
a time, when ``fetch`` reaches them.
"""

import importlib

from doifetch.sources.contract import Request, Result

# When --source all (the default), try sources in this order until one succeeds.
# Open and institutional sources only: Crossref/Unpaywall/HAL (open access),
# ISTEX (licensed national archive) and EZproxy (institutional subscription;
# fails fast unless EZPROXY_BASE + EZPROXY_COOKIES are configured). Shadow
# libraries (scihub, libgen) are opt-in: pass --source scihub / --source libgen.
DEFAULT_ORDER = ["crossref", "unpaywall", "hal", "istex", "ezproxy"]


def fetch(req: Request) -> Result:
    """Run the default cascade for ``req`` and return the deciding result.

    Sources that do not accept ``req.kind`` are skipped. The cascade stops at
    the first ``"success"`` or ``"skipped"``; otherwise the last failure is
    returned. Like a source, it never raises.
    """
    result = Result("failed", "", error=f"no default source accepts {req.kind}")
    for name in DEFAULT_ORDER:
        try:
            module = importlib.import_module(f"doifetch.sources.{name}")
            if req.kind not in module.ACCEPTS:
                continue
            result = module.fetch(req)
        except Exception as exc:  # noqa: BLE001 - never raise into the caller
            result = Result("failed", name, error=str(exc))
        if result.status != "failed":
            break
    return result
