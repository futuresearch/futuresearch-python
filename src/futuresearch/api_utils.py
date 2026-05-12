import os
from importlib.metadata import version

from futuresearch.constants import DEFAULT_FUTURESEARCH_API_URL
from futuresearch.generated.client import AuthenticatedClient


def create_client() -> AuthenticatedClient:
    """Create an AuthenticatedClient from environment variables.

    Reads FUTURESEARCH_API_KEY (or legacy EVERYROW_API_KEY) and
    FUTURESEARCH_API_URL (or legacy EVERYROW_API_URL) from environment variables.

    Returns:
        AuthenticatedClient: A configured client instance

    Raises:
        ValueError: If no API key is set in environment
    """
    api_key = os.environ.get("FUTURESEARCH_API_KEY") or os.environ.get(
        "EVERYROW_API_KEY"
    )
    if not api_key:
        raise ValueError("FUTURESEARCH_API_KEY is not set; cannot initialize client")
    api_url = (
        os.environ.get("FUTURESEARCH_API_URL")
        or os.environ.get("EVERYROW_API_URL")
        or DEFAULT_FUTURESEARCH_API_URL
    )
    sdk_version = version("futuresearch")
    return AuthenticatedClient(
        base_url=api_url,
        token=api_key,
        headers={"X-SDK-Version": f"futuresearch-python/{sdk_version}"},
        raise_on_unexpected_status=True,
        follow_redirects=True,
    )
