"""Signing into an account, and keeping the resulting grant alive.

The browser half of this runs on the user's machine and comes back to a
loopback listener. Two properties are load-bearing and easy to lose:

* the listener binds the exact port the provider's redirect URI is registered
  against, because an exchange whose `redirect_uri` differs at all is refused;
* the `state` returned by the browser is compared against the one that was
  sent, because without that check any page the user visits could drive a code
  of its own choosing into this listener.

Nothing here writes to the credential store. The caller decides what to keep,
so a failed or abandoned login leaves no partial account behind.
"""

from __future__ import annotations

import json
import socket
import socketserver
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .pkce import Pkce, generate_pkce, generate_state
from .registry import OAuthProvider

#: How long a browser login may take before the listener gives up.
LOGIN_TIMEOUT_SECONDS = 300.0

#: How long to wait on the vendor's token endpoint.
TOKEN_TIMEOUT_SECONDS = 30.0

#: Refresh this long before the access token actually expires.
#:
#: A token that is valid "now" can still be rejected by the time the request
#: reaches the vendor, and a refresh is cheap compared to a failed dispatch.
REFRESH_SKEW = timedelta(minutes=5)


class OAuthError(RuntimeError):
    """A login or refresh that cannot be completed."""

    def __init__(self, message: str, code: str = "OAUTH_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Grant:
    """What a completed login yields."""

    provider_id: str
    access_token: str
    refresh_token: str
    #: UTC ISO-8601, or empty when the vendor did not say.
    expires_at: str
    scope: str = ""
    account_label: str = ""
    account_id: str = ""
    org_id: str = ""
    plan: str = ""
    api_endpoint: str = ""
    #: The interactive login this grant descends from, preserved across
    #: refreshes because some vendors cap the whole family from that moment.
    authorized_at: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


class _LoopbackServer(HTTPServer):
    """An HTTP server that does not look its own name up.

    `HTTPServer.server_bind` calls `socket.getfqdn`, a reverse DNS lookup that
    on a machine with no reverse record for the loopback address blocks for
    roughly half a second. It serves nothing here -- the value is only used to
    fill in CGI variables -- and it sits directly in the path of starting a
    sign-in.
    """

    # SO_REUSEADDR, because the port is fixed by the provider and cannot be
    # swapped for a free one. Without it a completed sign-in leaves the socket
    # in TIME_WAIT and the next attempt -- a retry, the commonest case --
    # fails to bind for a minute or more. It does not let a second live
    # listener share the port, so a genuinely occupied port is still reported.
    allow_reuse_address = True

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class _LoopbackServerV6(_LoopbackServer):
    address_family = socket.AF_INET6


@dataclass
class PendingLogin:
    """A login waiting on the browser."""

    provider: OAuthProvider
    url: str
    state: str
    pkce: Pkce
    _servers: list[HTTPServer]
    _threads: list[threading.Thread]
    _result: dict[str, str]
    _done: threading.Event

    @property
    def redirect_uri(self) -> str:
        return self.provider.redirect_uri

    def wait(self, timeout: float = LOGIN_TIMEOUT_SECONDS) -> str:
        """Block until the browser comes back, returning the authorization code."""
        try:
            if not self._done.wait(timeout):
                raise OAuthError(
                    "Timed out waiting for the browser to complete sign-in.",
                    "OAUTH_TIMEOUT",
                )
            error = self._result.get("error")
            if error:
                raise OAuthError(f"The provider refused the sign-in: {error}", "OAUTH_DENIED")
            code = self._result.get("code", "")
            if not code:
                raise OAuthError("The provider returned no authorization code.", "OAUTH_NO_CODE")
            return code
        finally:
            self.close()

    def close(self) -> None:
        for server in self._servers:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                # Releasing a listener must never be what fails a login that
                # has already produced a code.
                pass
        self._servers = []


_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Loopforge</title>"
    "<body style=\"font:14px system-ui;padding:3rem;text-align:center\">"
    "<p>{message}</p><p style=\"color:#888\">You can close this tab.</p>"
)


def begin_login(provider: OAuthProvider) -> PendingLogin:
    """Start a browser login: bind the listener, then build the URL.

    In that order deliberately. If the port cannot be bound there is no point
    sending the user to a browser, and a URL handed out before the listener
    exists is a race the user experiences as a dead redirect.
    """
    if not provider.configured:
        raise OAuthError(
            f"{provider.name} needs its client credentials supplied. Set "
            f"{provider.client_id_env} and {provider.client_secret_env} to the "
            "pair from your own installation of that tool.",
            "OAUTH_CLIENT_UNCONFIGURED",
        )
    state = generate_state()
    pkce = generate_pkce()
    result: dict[str, str] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != provider.callback_path:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            query = urllib.parse.parse_qs(parsed.query)
            returned_state = (query.get("state") or [""])[0]
            # Compared before the code is taken: an unsolicited callback must
            # not be able to plant one, and reporting the mismatch to the page
            # would only tell an attacker what to fix.
            if returned_state != state:
                result["error"] = "state mismatch"
                message = "Sign-in could not be verified."
            elif query.get("error"):
                result["error"] = (query.get("error") or [""])[0]
                message = "Sign-in was refused."
            else:
                result["code"] = (query.get("code") or [""])[0]
                message = "Signed in." if result["code"] else "No authorization code was returned."
            body = _PAGE.format(message=message).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

    try:
        servers: list[HTTPServer] = [
            _LoopbackServer(("127.0.0.1", provider.callback_port), Handler)
        ]
    except OSError as exc:
        raise OAuthError(
            f"Cannot listen on port {provider.callback_port} for the {provider.name} "
            f"sign-in redirect: {exc}. That port is fixed by the provider, so close "
            "whatever is holding it and try again.",
            "OAUTH_PORT_UNAVAILABLE",
        ) from exc

    # `localhost` resolves to ::1 before 127.0.0.1 on a default macOS or Linux
    # install, so the browser's first connection goes to the address this has
    # not bound. Most browsers then fall back, but a filtered rather than
    # refused ::1 leaves the user watching a redirect that never completes --
    # and the failure looks like the provider's, not ours.
    #
    # Best effort: a machine with IPv6 disabled cannot bind it at all, and that
    # is not a reason to refuse a sign-in that will work over IPv4.
    try:
        servers.append(_LoopbackServerV6(("::1", provider.callback_port), Handler))
    except OSError:
        pass

    # A short poll interval because `shutdown` waits for the serving loop to
    # notice it: at the default half a second, releasing two listeners stalls
    # the end of a sign-in for about a second for no reason.
    threads = [
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        for server in servers
    ]
    for thread in threads:
        thread.start()

    params = {
        "response_type": "code",
        "client_id": provider.resolved_client_id,
        "redirect_uri": provider.redirect_uri,
        "state": state,
    }
    if provider.scopes:
        params["scope"] = provider.scopes
    if provider.use_pkce:
        params["code_challenge"] = pkce.challenge
        params["code_challenge_method"] = pkce.method
    params.update(provider.extra_authorize_params)
    url = f"{provider.authorize_url}?{urllib.parse.urlencode(params)}"
    return PendingLogin(
        provider=provider,
        url=url,
        state=state,
        pkce=pkce,
        _servers=servers,
        _threads=threads,
        _result=result,
        _done=done,
    )


def _token_payload(provider: OAuthProvider, payload: dict[str, str]) -> dict[str, str]:
    """The body this vendor expects, from the standard one.

    Vendors differ in both directions -- some require a field the standard does
    not define, some refuse one it does -- and either mistake comes back as the
    same unhelpful 400, so both are stated per provider rather than guessed.
    """
    body = {name: value for name, value in payload.items() if value}
    secret = provider.resolved_client_secret
    if secret:
        body["client_secret"] = secret
    body.update(provider.token_extra_params)
    for name in provider.token_omit_params:
        body.pop(name, None)
    return body


def _post_token(provider: OAuthProvider, payload: dict[str, str], what: str) -> dict[str, Any]:
    """One call to the vendor's token endpoint."""
    payload = _token_payload(provider, payload)
    if provider.token_json_body:
        body = json.dumps(payload).encode("utf-8")
        content_type = "application/json"
    else:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    request = urllib.request.Request(
        provider.token_url,
        data=body,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TOKEN_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # The body is the only thing that distinguishes a stale refresh token
        # from a wrong redirect URI, and both arrive as a 4xx.
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        raise OAuthError(
            f"{provider.name} {what} failed: HTTP {exc.code}{': ' + detail if detail else ''}",
            "OAUTH_TOKEN_REJECTED",
        ) from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"{provider.name} {what} could not reach the endpoint: {exc.reason}",
                         "OAUTH_UNREACHABLE") from exc
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise OAuthError(f"{provider.name} {what} returned a non-JSON response.",
                         "OAUTH_BAD_RESPONSE") from exc
    if not isinstance(parsed, dict):
        raise OAuthError(f"{provider.name} {what} returned an unexpected response.",
                         "OAUTH_BAD_RESPONSE")
    return parsed


def _grant_from(provider: OAuthProvider, payload: dict[str, Any], authorized_at: str) -> Grant:
    access = str(payload.get("access_token") or "")
    if not access:
        raise OAuthError(f"{provider.name} returned no access token.", "OAUTH_NO_TOKEN")
    expires_in = payload.get("expires_in")
    expires_at = ""
    if isinstance(expires_in, (int, float)) and not isinstance(expires_in, bool):
        expires_at = _iso(_utc_now() + timedelta(seconds=float(expires_in)))
    return Grant(
        provider_id=provider.id,
        access_token=access,
        refresh_token=str(payload.get("refresh_token") or ""),
        expires_at=expires_at,
        scope=str(payload.get("scope") or ""),
        account_id=str(payload.get("account_id") or ""),
        org_id=str(payload.get("organization_id") or ""),
        authorized_at=authorized_at,
    )


def complete_login(pending: PendingLogin, code: str) -> Grant:
    """Exchange an authorization code for a grant."""
    provider = pending.provider
    # Some vendors append the state to the code with a `#` separator; the
    # exchange rejects the combined form.
    bare_code = code.split("#", 1)[0]
    payload = {
        "grant_type": "authorization_code",
        "client_id": provider.resolved_client_id,
        "code": bare_code,
        "redirect_uri": provider.redirect_uri,
        "code_verifier": pending.pkce.verifier if provider.use_pkce else "",
        "state": pending.state,
    }
    parsed = _post_token(provider, payload, "token exchange")
    return _grant_from(provider, parsed, authorized_at=_iso(_utc_now()))


def refresh_grant(provider: OAuthProvider, grant: Grant) -> Grant:
    """Renew an access token, keeping what a refresh does not return.

    Vendors omit fields they consider unchanged -- most rotate the refresh
    token but some return none, and the account identity captured at login is
    generally absent. Treating an omission as a deletion would quietly strip
    the account of its identity on the first renewal.
    """
    if not grant.refresh_token:
        raise OAuthError(
            f"The {provider.name} account has no refresh token; sign in again.",
            "OAUTH_NO_REFRESH_TOKEN",
        )
    payload = {
        "grant_type": "refresh_token",
        "client_id": provider.resolved_client_id,
        "refresh_token": grant.refresh_token,
    }
    parsed = _post_token(provider, payload, "token refresh")
    renewed = _grant_from(provider, parsed, authorized_at=grant.authorized_at)
    return replace(
        renewed,
        refresh_token=renewed.refresh_token or grant.refresh_token,
        scope=renewed.scope or grant.scope,
        account_label=renewed.account_label or grant.account_label,
        account_id=renewed.account_id or grant.account_id,
        org_id=renewed.org_id or grant.org_id,
        plan=renewed.plan or grant.plan,
        api_endpoint=renewed.api_endpoint or grant.api_endpoint,
    )


@dataclass(frozen=True)
class DeviceLogin:
    """A sign-in the user completes by typing a code on the vendor's site."""

    provider_id: str
    device_code: str
    user_code: str
    verification_uri: str
    #: Seconds the vendor asked to be waited between polls.
    interval: int
    expires_in: int


#: Slowest a vendor may ask us to poll before it is treated as unusable.
MAX_POLL_INTERVAL_SECONDS = 60

#: Fallback when the vendor states no interval, as the specification allows.
DEFAULT_POLL_INTERVAL_SECONDS = 5


def begin_device_login(provider: OAuthProvider) -> DeviceLogin:
    """Ask a vendor for a device code.

    For accounts with no redirect: the user is shown a short code and a URL,
    types the code there, and this polls until it is approved. It needs no
    listener, so it also works where a browser cannot reach this machine.
    """
    if provider.flow != "device_code" or not provider.device_code_url:
        raise OAuthError(
            f"{provider.name} does not use a device code sign-in.", "OAUTH_FLOW_MISMATCH"
        )
    payload = {"client_id": provider.resolved_client_id}
    if provider.scopes:
        payload["scope"] = provider.scopes
    request = urllib.request.Request(
        provider.device_code_url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TOKEN_TIMEOUT_SECONDS) as response:
            parsed = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise OAuthError(
            f"{provider.name} refused a device code: HTTP {exc.code}"
            f"{': ' + detail if detail else ''}",
            "OAUTH_DEVICE_CODE_REFUSED",
        ) from exc
    except urllib.error.URLError as exc:
        raise OAuthError(
            f"{provider.name} could not be reached: {exc.reason}", "OAUTH_UNREACHABLE"
        ) from exc
    except ValueError as exc:
        raise OAuthError(
            f"{provider.name} returned a non-JSON device code response.",
            "OAUTH_BAD_RESPONSE",
        ) from exc

    device_code = str(parsed.get("device_code") or "")
    user_code = str(parsed.get("user_code") or "")
    if not device_code or not user_code:
        raise OAuthError(
            f"{provider.name} returned no device code.", "OAUTH_BAD_RESPONSE"
        )
    interval = parsed.get("interval")
    return DeviceLogin(
        provider_id=provider.id,
        device_code=device_code,
        user_code=user_code,
        verification_uri=str(
            parsed.get("verification_uri_complete")
            or parsed.get("verification_uri")
            or provider.authorize_url
        ),
        interval=(
            int(interval)
            if isinstance(interval, (int, float)) and not isinstance(interval, bool)
            else DEFAULT_POLL_INTERVAL_SECONDS
        ),
        expires_in=int(parsed.get("expires_in") or 900),
    )


def poll_device_login(
    provider: OAuthProvider, device: DeviceLogin, timeout: float | None = None
) -> Grant:
    """Wait for the user to approve a device code.

    `authorization_pending` and `slow_down` are the vendor saying "not yet",
    not failures -- treating them as errors would abandon a sign-in the user
    is part-way through. `slow_down` also has to actually slow the polling
    down, or the vendor starts refusing outright.
    """
    deadline = time.monotonic() + (timeout if timeout is not None else device.expires_in)
    interval = min(max(device.interval, 1), MAX_POLL_INTERVAL_SECONDS)
    payload = {
        "client_id": provider.resolved_client_id,
        "device_code": device.device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    while True:
        if time.monotonic() >= deadline:
            raise OAuthError(
                f"The {provider.name} sign-in expired before it was approved.",
                "OAUTH_TIMEOUT",
            )
        try:
            parsed = _post_token(provider, payload, "device sign-in")
        except OAuthError as exc:
            # A pending approval arrives as a 4xx carrying the reason.
            text = str(exc)
            if "authorization_pending" in text:
                pass
            elif "slow_down" in text:
                interval = min(interval + 5, MAX_POLL_INTERVAL_SECONDS)
            elif "access_denied" in text:
                # The user pressed cancel. A distinct state from a malformed
                # request, and the only one they can act on by trying again.
                raise OAuthError(
                    f"The {provider.name} sign-in was declined.", "OAUTH_DENIED"
                ) from exc
            elif "expired_token" in text:
                raise OAuthError(
                    f"The {provider.name} sign-in code expired before it was approved.",
                    "OAUTH_TIMEOUT",
                ) from exc
            else:
                raise
        else:
            error = str(parsed.get("error") or "")
            if not error:
                return _grant_from(provider, parsed, authorized_at=_iso(_utc_now()))
            if error == "slow_down":
                interval = min(interval + 5, MAX_POLL_INTERVAL_SECONDS)
            elif error != "authorization_pending":
                raise OAuthError(
                    f"{provider.name} refused the sign-in: "
                    f"{parsed.get('error_description') or error}",
                    "OAUTH_DENIED",
                )
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


def needs_refresh(grant: Grant, now: datetime | None = None) -> bool:
    """Whether the access token should be renewed before being used."""
    expiry = _parse_iso(grant.expires_at)
    if expiry is None:
        # No stated expiry: nothing says it is stale, and refreshing on every
        # use would burn the rotation budget for no reason.
        return False
    return (now or _utc_now()) + REFRESH_SKEW >= expiry


def grant_deadline(provider: OAuthProvider, grant: Grant) -> str:
    """When the whole grant family dies, for vendors that cap it. Empty if not."""
    if not provider.grant_ttl_days:
        return ""
    authorized = _parse_iso(grant.authorized_at)
    if authorized is None:
        return ""
    return _iso(authorized + timedelta(days=provider.grant_ttl_days))
