DEFAULT_FUTURESEARCH_APP_URL = "https://futuresearch.ai"
DEFAULT_FUTURESEARCH_API_URL = "https://futuresearch.ai/api/v0"

# Backwards compatibility aliases
DEFAULT_EVERYROW_APP_URL = DEFAULT_FUTURESEARCH_APP_URL
DEFAULT_EVERYROW_API_URL = DEFAULT_FUTURESEARCH_API_URL


class FuturesearchError(Exception): ...


# Backwards compatibility alias
EveryrowError = FuturesearchError
