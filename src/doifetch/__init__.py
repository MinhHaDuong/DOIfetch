"""DOIfetch: batch academic paper downloader."""

from doifetch.api import DEFAULT_ORDER, fetch
from doifetch.sources.contract import Request, Result

__all__ = ["DEFAULT_ORDER", "Request", "Result", "fetch"]
