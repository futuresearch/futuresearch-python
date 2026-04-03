"""Per-request context propagation via contextvars.

In stateless HTTP mode there is no MCP initialize handshake, so
ctx.session.client_params is always None. The HTTP middleware propagates
the User-Agent and X-Conversation-Id headers via context vars so that
tool functions can still distinguish clients.
"""

import contextvars
from collections.abc import Generator
from contextlib import contextmanager

_user_agent_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_agent", default=""
)

_conversation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "conversation_id", default=""
)


def get_user_agent() -> str:
    """Return the User-Agent of the current HTTP request (empty in stdio mode)."""
    return _user_agent_var.get()


def get_conversation_id() -> str:
    """Return the X-Conversation-Id of the current HTTP request (empty if absent)."""
    return _conversation_id_var.get()


@contextmanager
def request_context(
    user_agent: str,
    conversation_id: str,
) -> Generator[None]:
    """Set per-request context vars for the duration of the block."""
    ua_token = _user_agent_var.set(user_agent)
    cc_token = _conversation_id_var.set(conversation_id)
    try:
        yield
    finally:
        _user_agent_var.reset(ua_token)
        _conversation_id_var.reset(cc_token)
