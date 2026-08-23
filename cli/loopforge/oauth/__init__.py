"""Signing into subscription accounts directly, rather than borrowing a CLI.

Loopforge presents itself as each vendor's own first-party client -- the same
client id its official CLI uses -- and holds the resulting grant itself. That
is what makes a subscription usable without requiring the vendor's CLI to be
installed and signed in on this machine, and what makes usage figures readable
from the vendor rather than scavenged from whatever that CLI left on disk.

The credential is stored in `~/.loopforge`, plaintext behind 0600, exactly as
the API keys already there are. See `docs/decisions/0007-user-level-state.md`.
"""

from .flow import (
    DeviceLogin,
    Grant,
    OAuthError,
    PendingLogin,
    begin_device_login,
    begin_login,
    complete_login,
    grant_deadline,
    poll_device_login,
    needs_refresh,
    refresh_grant,
)
from .registry import OAuthProvider, provider, providers

__all__ = [
    "DeviceLogin",
    "Grant",
    "OAuthError",
    "OAuthProvider",
    "PendingLogin",
    "begin_device_login",
    "begin_login",
    "complete_login",
    "grant_deadline",
    "needs_refresh",
    "poll_device_login",
    "provider",
    "providers",
    "refresh_grant",
]
