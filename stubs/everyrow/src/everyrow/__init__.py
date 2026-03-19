import warnings

from futuresearch import (
    BillingResponse,
    Session,
    SessionInfo,
    SessionListResult,
    __version__,
    create_client,
    create_session,
    fetch_task_data,
    get_billing_balance,
    list_sessions,
    print_progress,
)

warnings.warn(
    "The 'everyrow' package has been renamed to 'futuresearch'. "
    "Please update your dependencies: pip install futuresearch",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "BillingResponse",
    "Session",
    "SessionInfo",
    "SessionListResult",
    "__version__",
    "create_client",
    "create_session",
    "fetch_task_data",
    "get_billing_balance",
    "list_sessions",
    "print_progress",
]
