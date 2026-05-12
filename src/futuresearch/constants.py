import warnings
from typing import Any

DEFAULT_FUTURESEARCH_APP_URL = "https://futuresearch.ai"
DEFAULT_FUTURESEARCH_API_URL = "https://futuresearch.ai/api/v0"

# Backwards compatibility aliases
DEFAULT_EVERYROW_APP_URL = DEFAULT_FUTURESEARCH_APP_URL
DEFAULT_EVERYROW_API_URL = DEFAULT_FUTURESEARCH_API_URL


_DEPRECATED_REEXPORTS = {"FuturesearchError", "EveryrowError"}


def __getattr__(name: str) -> Any:
    if name in _DEPRECATED_REEXPORTS:
        warnings.warn(
            f"Importing {name!r} from futuresearch.constants is deprecated; "
            "use 'from futuresearch import FuturesearchError' instead. "
            "This compatibility shim will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        from futuresearch.errors import FuturesearchError  # noqa: PLC0415

        return FuturesearchError
    raise AttributeError(f"module 'futuresearch.constants' has no attribute {name!r}")
