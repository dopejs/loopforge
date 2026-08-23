"""Using a stored grant, and keeping it usable.

An access token outlives its usefulness quickly -- hours, not days -- so almost
every use of one has to be prepared to renew it first. Doing that here rather
than at each call site means a rotated refresh token is always written back:
vendors that rotate invalidate the old one immediately, so a renewal that is
not persisted costs the account its next sign-in.
"""

from __future__ import annotations

from typing import Any

from ..userstore import UserStore
from .flow import Grant, OAuthError, needs_refresh, refresh_grant
from .registry import OAuthProvider


def grant_from_row(row: dict[str, Any]) -> Grant:
    return Grant(
        provider_id=str(row.get("provider_id") or ""),
        access_token=str(row.get("access_token") or ""),
        refresh_token=str(row.get("refresh_token") or ""),
        expires_at=str(row.get("expires_at") or ""),
        scope=str(row.get("scope") or ""),
        account_label=str(row.get("account_label") or ""),
        account_id=str(row.get("account_id") or ""),
        org_id=str(row.get("org_id") or ""),
        plan=str(row.get("plan") or ""),
        api_endpoint=str(row.get("api_endpoint") or ""),
        authorized_at=str(row.get("authorized_at") or ""),
    )


def grant_as_row(grant: Grant) -> dict[str, Any]:
    return {
        "provider_id": grant.provider_id,
        "access_token": grant.access_token,
        "refresh_token": grant.refresh_token,
        "expires_at": grant.expires_at,
        "scope": grant.scope,
        "account_label": grant.account_label,
        "account_id": grant.account_id,
        "org_id": grant.org_id,
        "plan": grant.plan,
        "api_endpoint": grant.api_endpoint,
        "authorized_at": grant.authorized_at,
    }


def active_grant(
    store: UserStore, provider: OAuthProvider, account_key: str = ""
) -> Grant | None:
    """The usable grant for an account, renewed first if it is due.

    Returns None when the account has never been signed into. A renewal that
    fails raises rather than returning the stale grant: a caller told "here is
    a token" will use it, and the resulting 401 is a worse error than the one
    that explains the account needs signing in again.
    """
    row = store.oauth_grant(provider.id, account_key)
    if not row:
        return None
    grant = grant_from_row(row)
    if not needs_refresh(grant):
        return grant
    renewed = refresh_grant(provider, grant)
    # Written back before use: a rotated refresh token invalidates the old one
    # immediately, so losing the new one here costs the account its next login.
    store.save_oauth_grant(grant_as_row(renewed), account_key)
    return renewed


def signed_in_providers(store: UserStore) -> set[str]:
    """Which provider ids currently hold a grant."""
    try:
        return {str(row.get("provider_id") or "") for row in store.oauth_grants()}
    except Exception:
        # An unreadable store means "cannot tell", and every caller here
        # degrades to the route that needs no credential.
        return set()


__all__ = [
    "OAuthError",
    "active_grant",
    "grant_as_row",
    "grant_from_row",
    "signed_in_providers",
]
