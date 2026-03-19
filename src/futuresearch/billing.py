"""Billing utilities for futuresearch SDK."""

from dataclasses import dataclass

from futuresearch.api_utils import create_client
from futuresearch.generated.api.billing import get_billing_balance_billing_get


@dataclass
class BillingResponse:
    """Response containing the user's current billing balance."""

    current_balance_dollars: float


async def get_billing_balance() -> BillingResponse:
    """Get the current billing balance for the authenticated user.

    Returns:
        BillingResponse containing the user's current balance.

    Raises:
        RuntimeError: If the request fails
    """
    client = create_client()
    response = await get_billing_balance_billing_get.asyncio(client=client)
    if response is None:
        raise RuntimeError("Failed to get billing balance")
    return BillingResponse(current_balance_dollars=response.current_balance_dollars)
