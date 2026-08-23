"""Asking a vendor how much of a subscription is left.

This is the half that borrowing a CLI could never do. With a grant of our own
the question can be put to the vendor directly, so the answer is current rather
than whatever the other tool last happened to write to disk.

The shapes below are the vendors' undocumented account endpoints -- the ones
their own clients use. They change without notice, so every field is read
defensively and a payload that has moved on degrades to "no figure" rather than
to a wrong number.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from .registry import OAuthProvider

USAGE_TIMEOUT_SECONDS = 20.0

#: Sent so the account endpoint sees the client it expects.
#:
#: This is the same posture as using the vendor's client id: the grant was
#: minted as that client, so the request identifies itself as that client.
CLAUDE_CODE_VERSION = "2.0.0"

ANTHROPIC_BETA = (
    "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,"
    "context-management-2025-06-27"
)


class UsageUnavailable(RuntimeError):
    """The vendor could not be asked, or did not answer usefully."""


def _percent(value: Any) -> float | None:
    """A utilization figure, or None when the payload does not carry one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _iso(value: Any) -> str:
    """A vendor timestamp normalised to UTC ISO-8601, or empty."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=USAGE_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        # 401 means the grant is stale, which the caller can fix by refreshing;
        # everything else it cannot, so the distinction is kept.
        raise UsageUnavailable(
            f"HTTP {exc.code}{': ' + detail if detail else ''}"
        ) from exc
    except urllib.error.URLError as exc:
        raise UsageUnavailable(f"could not reach the endpoint: {exc.reason}") from exc
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise UsageUnavailable("the endpoint did not return JSON") from exc
    if not isinstance(payload, dict):
        raise UsageUnavailable("the endpoint returned an unexpected payload")
    return payload


def _window(label: str, minutes: int, bucket: Any) -> dict[str, Any] | None:
    if not isinstance(bucket, dict):
        return None
    used = _percent(bucket.get("utilization"))
    resets_at = _iso(bucket.get("resets_at"))
    if used is None and not resets_at:
        return None
    return {
        "label": label,
        "window_minutes": minutes,
        "used_percent": used if used is not None else 0.0,
        "resets_at": resets_at,
    }


def anthropic_usage(provider: OAuthProvider, access_token: str) -> dict[str, Any]:
    """Claude's limit windows, asked of the account endpoint.

    Returns the same shape the on-disk reader produces, so a surface does not
    need to know which route answered -- only how current it is.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "anthropic-beta": ANTHROPIC_BETA,
        "User-Agent": f"claude-cli/{CLAUDE_CODE_VERSION} (external, cli)",
    }
    payload = _get_json(provider.usage_url, headers)

    windows: list[dict[str, Any]] = []
    for label, minutes, key in (
        ("5h", 300, "five_hour"),
        ("7d", 10080, "seven_day"),
    ):
        found = _window(label, minutes, payload.get(key))
        if found:
            windows.append(found)

    # Model-scoped weekly caps arrive only through the generic `limits` array
    # now; the old per-model buckets have been permanently null since mid-2026.
    #
    # `is_active` is deliberately not filtered on: the vendor marks only the
    # currently binding limit active, so an account pinned at one cap reports
    # its other real, non-zero limits as inactive. Filtering on it hides
    # utilization that is genuinely being consumed.
    for entry in payload.get("limits") or []:
        if not isinstance(entry, dict):
            continue
        used = _percent(entry.get("percent"))
        resets_at = _iso(entry.get("resets_at"))
        if used is None and not resets_at:
            continue
        scope = entry.get("scope")
        model = scope.get("model") if isinstance(scope, dict) else None
        name = model.get("display_name") if isinstance(model, dict) else None
        kind = str(entry.get("kind") or "limit")
        label = str(name).strip() if isinstance(name, str) and name.strip() else kind
        windows.append(
            {
                "label": label,
                # Scoped entries do not state a duration; the kind names it.
                "window_minutes": 10080 if "weekly" in kind else 0,
                "used_percent": used if used is not None else 0.0,
                "resets_at": resets_at,
            }
        )

    if not windows:
        raise UsageUnavailable("the account endpoint reported no limits")

    balance = ""
    extra = payload.get("extra_usage")
    if isinstance(extra, dict):
        used_credits = extra.get("used_credits")
        monthly_limit = extra.get("monthly_limit")
        if isinstance(used_credits, (int, float)) and not isinstance(used_credits, bool):
            currency = str(extra.get("currency") or "").strip()
            balance = f"{used_credits} used" + (f" {currency}" if currency else "")
            if isinstance(monthly_limit, (int, float)) and not isinstance(monthly_limit, bool):
                balance = f"{used_credits} / {monthly_limit}" + (
                    f" {currency}" if currency else ""
                )

    return {
        "provider_id": provider.id,
        "available": True,
        "reason": "",
        # Asked of the vendor just now, which is the point of holding a grant.
        "observed_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "plan": "",
        "limit_id": "",
        "windows": windows,
        "credit_balance": balance,
        "credits_unlimited": False,
        "source": "vendor",
    }


def window_label(minutes: int) -> str:
    """A duration in minutes, named the way a user reads it.

    Derived rather than looked up in a table of known windows: the vendors add
    windows without notice, and a lookup answers a new one with a blank label.
    The arithmetic gives the same names for the windows that do exist -- 300
    is `5h`, 10080 is `7d` -- and something sensible for any that appear.
    """
    if minutes <= 0:
        return ""
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def _seconds_to_window(payload: dict[str, Any]) -> tuple[str, int]:
    """A label and a duration in minutes from a window stated in seconds."""
    seconds = payload.get("limit_window_seconds")
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
        return "", 0
    minutes = int(round(float(seconds) / 60))
    return window_label(minutes), minutes


def _codex_window(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    used = _percent(payload.get("used_percent"))
    label, minutes = _seconds_to_window(payload)
    if used is None and not label:
        return None
    resets_at = ""
    reset_at = payload.get("reset_at")
    if isinstance(reset_at, (int, float)) and not isinstance(reset_at, bool):
        resets_at = (
            datetime.fromtimestamp(float(reset_at), tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    else:
        # Some payloads give only a relative offset.
        after = payload.get("reset_after_seconds")
        if isinstance(after, (int, float)) and not isinstance(after, bool):
            resets_at = (
                (datetime.now(timezone.utc) + timedelta(seconds=float(after)))
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
    return {
        "label": label or "limit",
        "window_minutes": minutes,
        "used_percent": used if used is not None else 0.0,
        "resets_at": resets_at,
    }


def codex_usage(provider: OAuthProvider, access_token: str) -> dict[str, Any]:
    """Codex's limit windows, asked of the ChatGPT account endpoint.

    The same figures the CLI records in its session rollouts, except current
    and without needing that CLI to have run recently.
    """
    payload = _get_json(
        provider.usage_url,
        {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    rate_limit = payload.get("rate_limit")
    windows: list[dict[str, Any]] = []
    if isinstance(rate_limit, dict):
        for key in ("primary_window", "secondary_window"):
            found = _codex_window(rate_limit.get(key))
            if found:
                windows.append(found)
    for extra in payload.get("additional_rate_limits") or []:
        if not isinstance(extra, dict):
            continue
        nested = extra.get("rate_limit")
        if not isinstance(nested, dict):
            continue
        for key in ("primary_window", "secondary_window"):
            found = _codex_window(nested.get(key))
            if found:
                name = str(extra.get("limit_name") or "").strip()
                if name:
                    found["label"] = f"{name} {found['label']}".strip()
                windows.append(found)
    if not windows:
        raise UsageUnavailable("the account endpoint reported no limits")

    windows.sort(key=lambda item: (item["window_minutes"] or 10**9))
    return {
        "provider_id": provider.id,
        "available": True,
        "reason": "",
        "observed_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "plan": str(payload.get("plan_type") or ""),
        "limit_id": "",
        "windows": windows,
        "credit_balance": "",
        "credits_unlimited": False,
        "source": "vendor",
    }


def _report(
    provider: OAuthProvider,
    windows: list[dict[str, Any]],
    *,
    plan: str = "",
    balance: str = "",
) -> dict[str, Any]:
    """One account's answer, in the shape every route here returns."""
    if not windows:
        raise UsageUnavailable("the account endpoint reported no limits")
    windows.sort(key=lambda item: (item["window_minutes"] or 10**9))
    return {
        "provider_id": provider.id,
        "available": True,
        "reason": "",
        "observed_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "plan": plan,
        "limit_id": "",
        "windows": windows,
        "credit_balance": balance,
        "credits_unlimited": False,
        "source": "vendor",
    }


def _epoch_iso(value: Any) -> str:
    """A vendor epoch, in seconds or milliseconds, as UTC ISO-8601.

    Both units appear in these payloads, sometimes from the same vendor, so
    the magnitude decides rather than the field name. Reading milliseconds as
    seconds puts a reset tens of thousands of years out, which renders as a
    limit that never resets.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    seconds = float(value)
    if seconds > 1_000_000_000_000:
        seconds /= 1000.0
    try:
        return (
            datetime.fromtimestamp(seconds, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return ""


def kimi_usage(provider: OAuthProvider, access_token: str) -> dict[str, Any]:
    """Kimi's coding-plan limits."""
    payload = _get_json(
        provider.usage_url,
        {"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    entries = payload.get("limits")
    if not isinstance(entries, list):
        usage = payload.get("usage")
        entries = usage if isinstance(usage, list) else []

    windows: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        used = _percent(entry.get("used"))
        limit = entry.get("limit")
        remaining = entry.get("remaining")
        # A count rather than a percentage: derive one, because a bar needs a
        # fraction and "1200 of 2000" is not one.
        if (
            used is not None
            and isinstance(limit, (int, float))
            and not isinstance(limit, bool)
            and limit > 0
        ):
            percent = 100.0 * used / float(limit)
        elif (
            isinstance(remaining, (int, float))
            and not isinstance(remaining, bool)
            and isinstance(limit, (int, float))
            and not isinstance(limit, bool)
            and limit > 0
        ):
            percent = 100.0 * (1.0 - float(remaining) / float(limit))
        else:
            continue
        window = entry.get("window")
        minutes = 0
        if isinstance(window, dict):
            duration = window.get("duration")
            unit = str(window.get("timeUnit") or "").upper()
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                minutes = int(duration) * (60 if "HOUR" in unit else 1)
        windows.append(
            {
                "label": window_label(minutes) or "limit",
                "window_minutes": minutes,
                "used_percent": round(percent, 1),
                "resets_at": _epoch_iso(entry.get("resetsAt") or entry.get("reset_at")),
            }
        )
    return _report(provider, windows)


def zai_usage(provider: OAuthProvider, access_token: str) -> dict[str, Any]:
    """Z.ai's quota limits."""
    payload = _get_json(
        provider.usage_url,
        {"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    data = payload.get("data")
    entries = data.get("limits") if isinstance(data, dict) else None
    windows: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        percent = _percent(entry.get("percentage"))
        if percent is None:
            used = entry.get("usage")
            total = entry.get("number")
            if (
                isinstance(used, (int, float))
                and not isinstance(used, bool)
                and isinstance(total, (int, float))
                and not isinstance(total, bool)
                and total > 0
            ):
                percent = 100.0 * float(used) / float(total)
        if percent is None:
            continue
        kind = str(entry.get("type") or "limit")
        windows.append(
            {
                "label": kind,
                "window_minutes": 0,
                "used_percent": round(percent, 1),
                "resets_at": _epoch_iso(entry.get("nextResetTime")),
            }
        )
    return _report(provider, windows)


def xai_usage(provider: OAuthProvider, access_token: str) -> dict[str, Any]:
    """xAI's CLI billing, which reports credits rather than windows."""
    payload = _get_json(
        provider.usage_url,
        {"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    windows: list[dict[str, Any]] = []
    used = _percent(payload.get("usagePercent"))
    if used is not None:
        windows.append(
            {
                "label": "plan",
                "window_minutes": 0,
                "used_percent": used,
                "resets_at": _epoch_iso(payload.get("resetsAt")),
            }
        )
    balance = ""
    limit = payload.get("monthlyLimit")
    spent = payload.get("used")
    if isinstance(limit, (int, float)) and not isinstance(limit, bool) and limit > 0:
        if isinstance(spent, (int, float)) and not isinstance(spent, bool):
            balance = f"{spent} / {limit}"
            if used is None:
                windows.append(
                    {
                        "label": "credits",
                        "window_minutes": 0,
                        "used_percent": round(100.0 * float(spent) / float(limit), 1),
                        "resets_at": _epoch_iso(payload.get("resetsAt")),
                    }
                )
    return _report(provider, windows, balance=balance)


#: Which provider ids can be asked directly, and how.
#:
#: An account absent here can still be signed in and used; it simply has no
#: endpoint this knows how to ask, so its usage falls back to whatever a local
#: CLI recorded.
FETCHERS = {
    "anthropic": anthropic_usage,
    "openai_codex": codex_usage,
    "kimi": kimi_usage,
    "zai": zai_usage,
    "xai": xai_usage,
}
