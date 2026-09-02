"""How much the agent may do without asking.

Three modes over the three tiers a tool can be in. The mode is the only thing a
person configures; which tier a command is in is a property of the command.

    mode          read    evidence   claim
    ----------------------------------------
    ask           allow   ask        ask
    allow-edit    allow   allow      ask
    auto          allow   allow      allow

`ask` is the default and the safe one. `allow-edit` is the mode a person
actually works in: builds and captures run without interruption, and moving the
project to a new stage still stops for them -- which is the distinction that
matters, because being asked before every build is how someone stops reading the
questions, and someone who stops reading them will approve a claim without
looking.

`auto` leaves nothing to approve. It is offered because a person running an
unattended batch has a real use for it, and it is not the default and never
becomes the default on its own: with it set, a model can move a project through
its stages and record who approved that, and the record will name someone who
was not asked.
"""

from __future__ import annotations

from .mcp import TIER_CLAIM, TIER_EVIDENCE, TIER_READ

#: Ask before anything that changes the project.
MODE_ASK = "ask"
#: Let the work happen; ask before a claim.
MODE_ALLOW_EDIT = "allow-edit"
#: Ask nothing.
MODE_AUTO = "auto"

MODES = (MODE_ASK, MODE_ALLOW_EDIT, MODE_AUTO)

#: What a person is agreeing to, in one line each. Rendered by a surface that
#: offers the choice, so the wording lives with the behaviour rather than in the
#: UI where the two can drift.
MODE_SUMMARY = {
    MODE_ASK: "Ask before anything that changes the project.",
    MODE_ALLOW_EDIT: "Run builds and captures without asking. Ask before a stage changes.",
    MODE_AUTO: "Never ask. The agent can move the project through its stages on its own.",
}

DEFAULT_MODE = MODE_ASK

#: Which tiers each mode lets through without asking.
_ALLOWED: dict[str, frozenset[str]] = {
    MODE_ASK: frozenset({TIER_READ}),
    MODE_ALLOW_EDIT: frozenset({TIER_READ, TIER_EVIDENCE}),
    MODE_AUTO: frozenset({TIER_READ, TIER_EVIDENCE, TIER_CLAIM}),
}


def normalize(mode: str | None) -> str:
    """The mode to use, given what was stored or asked for.

    An unrecognized value becomes the default rather than an error: a mode read
    from a store written by a different build should narrow what the agent may
    do, not stop the daemon from starting.
    """
    candidate = str(mode or "").strip()
    return candidate if candidate in MODES else DEFAULT_MODE


def exposure_for(tier: str, mode: str) -> str:
    """The exposure rule a tool in `tier` is published under.

    Anything not explicitly allowed is `approval_required`, including a tier
    this build does not recognize. A tool whose kind cannot be placed is one
    nobody has decided about, and the answer to that is to ask.
    """
    allowed = _ALLOWED.get(normalize(mode), _ALLOWED[DEFAULT_MODE])
    return "allow" if tier in allowed else "approval_required"


def describe(mode: str) -> dict[str, str]:
    """The mode and what it means, for a surface offering the choice."""
    resolved = normalize(mode)
    return {"mode": resolved, "summary": MODE_SUMMARY[resolved]}
