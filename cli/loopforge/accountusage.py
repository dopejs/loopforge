"""What the borrowed CLIs record about their own subscription limits.

A subscription account is not configured here. Kura reaches one by running a
CLI the user has already signed into, so Loopforge never holds that account's
credential and cannot ask the vendor how much of the subscription is left --
that request needs the OAuth token, and the token belongs to the other tool.

What it can do is read what the CLI itself wrote down. Codex records the limit
windows it was told about in its session rollouts, so a real quota figure is
available without touching a credential. Claude Code records consumption but
no window, so its balance is reported as unavailable with the reason rather
than substituted with a number that means something else.

Nothing here reads a credential store, and nothing here makes a network call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .oauth.usage import window_label

#: Naming shared with the vendor-queried route, so the same limit reads the
#: same whichever answered.
#:
#: Named by duration, never by the `primary`/`secondary` slot the payload
#: happens to use: real rollouts carry the seven-day window as `primary` in
#: some sessions and as `secondary` in others, so trusting the slot name
#: mislabels one of them.

#: How many session files to consider, newest first.
#:
#: The corpus is not small -- a developer's `~/.codex/sessions` runs to
#: gigabytes across hundreds of files -- so this bounds the work. It is set
#: well above the number of files usually needed because a run of sessions can
#: report no limits at all: on the machine this was written against, the
#: twenty newest files held 242 limit events and every one of them was empty.
#: The scan stops as soon as the answer cannot improve, so the ceiling costs
#: nothing in the common case.
MAX_SESSION_FILES = 64

#: How much of each file's tail to read.
#:
#: Individual rollouts reach hundreds of megabytes, and the events wanted here
#: are appended, so the end of the file is where they are. Reading whole files
#: would make opening a usage panel a disk-bound operation.
TAIL_BYTES = 256 * 1024


@dataclass(frozen=True)
class UsageWindow:
    """One rate-limit window as the vendor reported it."""

    label: str
    window_minutes: int
    used_percent: float
    #: When the window rolls over, UTC ISO-8601. Empty when not reported.
    resets_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "window_minutes": self.window_minutes,
            "used_percent": self.used_percent,
            "resets_at": self.resets_at,
        }


@dataclass(frozen=True)
class AccountUsage:
    """A subscription account's limit state, or why there is none."""

    provider_id: str
    available: bool
    #: Empty when available; otherwise why, in a sentence a user can act on.
    reason: str = ""
    #: When the CLI recorded this, UTC ISO-8601. The figure can be hours old,
    #: so it is reported rather than presented as current.
    observed_at: str = ""
    plan: str = ""
    #: The vendor's own name for the limit bucket these windows belong to.
    limit_id: str = ""
    windows: tuple[UsageWindow, ...] = field(default_factory=tuple)
    #: A prepaid balance alongside the windows, as the vendor formatted it.
    credit_balance: str = ""
    credits_unlimited: bool = False
    #: `vendor` when the account itself answered, `local` when this was read
    #: from what a CLI left on disk. The two differ in how current they are.
    source: str = "local"
    #: The vendor's own name, for accounts the surface has no preset for.
    display_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "available": self.available,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "plan": self.plan,
            "limit_id": self.limit_id,
            "windows": [window.as_dict() for window in self.windows],
            "credit_balance": self.credit_balance,
            "credits_unlimited": self.credits_unlimited,
            "source": self.source,
            "display_name": self.display_name,
        }


def _epoch_to_iso(value: Any) -> str:
    """A unix timestamp as UTC ISO-8601, or empty if it is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    try:
        moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return ""
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _windows_from(payload: dict[str, Any]) -> tuple[UsageWindow, ...]:
    """The populated windows in one `rate_limits` payload.

    Both slots are examined and sorted by duration so the shorter window is
    always first, whichever slot carried it.
    """
    found: list[UsageWindow] = []
    for slot in ("primary", "secondary"):
        window = payload.get(slot)
        if not isinstance(window, dict):
            continue
        minutes = window.get("window_minutes")
        used = window.get("used_percent")
        if not isinstance(minutes, int) or isinstance(minutes, bool):
            continue
        if isinstance(used, bool) or not isinstance(used, (int, float)):
            continue
        found.append(
            UsageWindow(
                label=window_label(minutes),
                window_minutes=minutes,
                used_percent=float(used),
                resets_at=_epoch_to_iso(window.get("resets_at")),
            )
        )
    return tuple(sorted(found, key=lambda window: window.window_minutes))


def _tail_lines(path: Path, limit: int = TAIL_BYTES) -> list[str]:
    """The last whole lines of a file, without reading the rest of it."""
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(0, size - limit)
            handle.seek(start)
            blob = handle.read()
    except OSError:
        return []
    text = blob.decode("utf-8", errors="replace")
    lines = text.splitlines()
    # The first line is a fragment whenever the read began mid-file.
    return lines[1:] if start > 0 and lines else lines


def _newest_rate_limits(path: Path) -> tuple[str, dict[str, Any]] | None:
    """The newest usable `rate_limits` event in one rollout's tail.

    Most of these events carry no window at all -- in a real corpus rather more
    than half of them -- because the CLI emits a token count whether or not the
    server said anything about limits. Taking the latest event rather than the
    latest *populated* one reports "no data" while the answer sits a few lines
    above.
    """
    newest: tuple[str, dict[str, Any]] | None = None
    for line in _tail_lines(path):
        if '"rate_limits"' not in line:
            continue
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        limits = payload.get("rate_limits")
        if not isinstance(limits, dict) or not _windows_from(limits):
            continue
        stamp = str(event.get("timestamp") or "")
        if newest is None or stamp > newest[0]:
            newest = (stamp, limits)
    return newest


def _parse_stamp(stamp: str) -> datetime | None:
    """A rollout timestamp as an aware datetime, or None if unparseable."""
    text = stamp.strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def _normalize_stamp(stamp: str) -> str:
    """A rollout timestamp as UTC ISO-8601, or empty if unparseable."""
    moment = _parse_stamp(stamp)
    if moment is None:
        return ""
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def codex_usage(home: Path) -> AccountUsage:
    """Codex's limit state, from the newest session that recorded one."""
    sessions = home / ".codex" / "sessions"
    try:
        dated = sorted(
            (
                (item.stat().st_mtime, item)
                for item in sessions.rglob("*.jsonl")
                if item.is_file()
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )[:MAX_SESSION_FILES]
    except OSError:
        dated = []
    if not dated:
        return AccountUsage(
            provider_id="codex_managed",
            available=False,
            reason="No Codex sessions found, so nothing has recorded a limit yet.",
        )

    # Every candidate is read rather than stopping at the first file with a
    # hit: a long session's last write is recent while the limit events inside
    # it can be days old, so file order is not event order. Cutting the scan
    # short on a file's mtime would be sound only while mtime never precedes
    # the contents, which a copied or restored directory breaks -- and reading
    # all of them costs tens of milliseconds against a multi-gigabyte corpus,
    # because only each file's tail is touched.
    best: tuple[str, dict[str, Any]] | None = None
    for _modified, path in dated:
        found = _newest_rate_limits(path)
        if found and (best is None or found[0] > best[0]):
            best = found
    if best is None:
        return AccountUsage(
            provider_id="codex_managed",
            available=False,
            reason="Recent Codex sessions recorded no limit information.",
        )

    stamp, limits = best
    # Reported as one snapshot rather than merged across events: the rollouts
    # carry several limit buckets (a plan's own windows, a model's separate
    # allowance), and combining them would describe a state that never existed.
    credits = limits.get("credits")
    balance = ""
    unlimited = False
    if isinstance(credits, dict):
        raw = credits.get("balance")
        balance = str(raw) if isinstance(raw, (str, int, float)) else ""
        unlimited = credits.get("unlimited") is True
    return AccountUsage(
        provider_id="codex_managed",
        available=True,
        observed_at=_normalize_stamp(stamp),
        plan=str(limits.get("plan_type") or ""),
        limit_id=str(limits.get("limit_id") or ""),
        windows=_windows_from(limits),
        credit_balance=balance,
        credits_unlimited=unlimited,
    )


def claude_usage(_home: Path) -> AccountUsage:
    """Why Claude's balance cannot be read without signing in.

    Claude Code writes no limit window to disk and keeps its own token in the
    system keychain, so there is nothing here to scavenge. The figure exists,
    but only behind an authenticated request -- which is exactly what signing
    this account in provides.
    """
    return AccountUsage(
        provider_id="claude_managed",
        available=False,
        reason=(
            "Claude records no limit windows on this machine. Sign the account "
            "in to read its balance from the vendor."
        ),
    )


#: The OAuth account behind each runtime provider id.
#:
#: Two vocabularies meet here: the runtime names a provider by how it is
#: reached, and a grant is held per vendor account. Mapping them explicitly
#: keeps a rename on either side from silently matching nothing.
OAUTH_PROVIDER_FOR: dict[str, str] = {
    "claude_managed": "anthropic",
    "codex_managed": "openai_codex",
}


def _from_vendor(runtime_id: str, store: Any, oauth_id: str = "") -> AccountUsage | None:
    """The account's own answer, when it has been signed in.

    Returns None whenever the vendor route is not available -- not signed in,
    no fetcher for that vendor, a stale grant, an endpoint that has moved --
    so the caller falls back to reading what a local CLI left behind. A
    degraded but honest figure beats no panel at all.
    """
    from .oauth.registry import provider as oauth_provider
    from .oauth.session import active_grant
    from .oauth.usage import FETCHERS, UsageUnavailable

    oauth_id = oauth_id or OAUTH_PROVIDER_FOR.get(runtime_id, "")
    fetcher = FETCHERS.get(oauth_id)
    if not fetcher:
        return None
    try:
        target = oauth_provider(oauth_id)
        grant = active_grant(store, target)
    except Exception:
        return None
    if grant is None or not grant.access_token:
        return None
    try:
        payload = fetcher(target, grant.access_token)
    except (UsageUnavailable, OSError, ValueError):
        return None
    return AccountUsage(
        provider_id=runtime_id,
        available=True,
        observed_at=str(payload.get("observed_at") or ""),
        plan=str(payload.get("plan") or grant.plan or ""),
        limit_id=str(payload.get("limit_id") or ""),
        windows=tuple(
            UsageWindow(
                label=str(item.get("label") or ""),
                window_minutes=int(item.get("window_minutes") or 0),
                used_percent=float(item.get("used_percent") or 0.0),
                resets_at=str(item.get("resets_at") or ""),
            )
            for item in payload.get("windows") or []
        ),
        credit_balance=str(payload.get("credit_balance") or ""),
        credits_unlimited=bool(payload.get("credits_unlimited")),
        source="vendor",
        display_name=target.name,
    )


def account_usage(home: Path | None = None, store: Any = None) -> list[AccountUsage]:
    """Limit state for every subscription account, reported or explained.

    The vendor is asked first where the account has been signed in, because
    that answer is current; what a local CLI wrote to disk is the fallback and
    can be hours old. Which route answered is carried on the record rather than
    hidden, so a surface can say how much to trust the number.
    """
    root = home if home is not None else Path.home()
    if store is None:
        from .userstore import UserStore

        store = UserStore()

    reported: list[AccountUsage] = []
    for runtime_id, on_disk in (
        ("codex_managed", codex_usage),
        ("claude_managed", claude_usage),
    ):
        vendor = _from_vendor(runtime_id, store)
        reported.append(vendor if vendor is not None else on_disk(root))

    # Every other account that has been signed into and can be asked.
    #
    # Listing only the two the runtime reaches through a CLI would mean an
    # account the user signed in here, whose balance is readable, silently
    # absent from the one surface that exists to show balances.
    from .oauth.usage import FETCHERS

    already = set(OAUTH_PROVIDER_FOR.values())
    try:
        signed_in = [str(row.get("provider_id") or "") for row in store.oauth_grants()]
    except Exception:
        signed_in = []
    for oauth_id in signed_in:
        if oauth_id in already or oauth_id not in FETCHERS:
            continue
        already.add(oauth_id)
        extra = _from_vendor(oauth_id, store, oauth_id=oauth_id)
        if extra is not None:
            reported.append(extra)
    return reported
