"""Which accounts can be signed into, and on what terms.

Each entry describes a vendor's own first-party client -- the same client id
its official CLI uses -- so signing in here produces a credential of exactly
the kind that CLI would have produced. That is what makes a subscription
usable without borrowing another application's session, and it is a deliberate
posture rather than an implementation detail: Loopforge presents itself as that
client.

The values are wire contracts. A wrong client id, scope or redirect port does
not degrade gracefully -- the vendor rejects the exchange outright -- so
nothing here is guessed. Anything unverified belongs absent rather than
approximated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

FlowKind = Literal["callback", "device_code"]


@dataclass(frozen=True)
class OAuthProvider:
    """One signable account."""

    id: str
    #: Shown in the UI. A proper noun, so it is not translated.
    name: str
    #: Empty where the value is supplied by the environment instead. See
    #: `client_id_env`.
    client_id: str = ""
    authorize_url: str = ""
    token_url: str = ""
    scopes: str = ""
    flow: FlowKind = "callback"
    #: Where a device-code flow asks for its code. Required when `flow` is
    #: `device_code`.
    device_code_url: str = ""
    #: Sent alongside the client id where the vendor's "installed application"
    #: registration carries one.
    #:
    #: Not a secret in any meaningful sense: it ships inside a desktop client
    #: that anyone can read, and the OAuth specification says as much about
    #: public clients. It is here because the vendor's token endpoint refuses
    #: the exchange without it, not because it protects anything.
    client_secret: str = ""
    #: Where to read the client credentials from when they are not in source.
    #:
    #: Google registers its CLI clients as "installed applications", whose
    #: secret is not confidential -- it ships inside every copy of the tool and
    #: RFC 8252 says as much. It is still Google's credential for Google's
    #: application rather than ours, and this repository is public, so it is
    #: read from the environment rather than published here. Anyone who wants
    #: these accounts supplies the pair from their own installation.
    client_id_env: str = ""
    client_secret_env: str = ""
    #: The port the redirect URI is registered against.
    #:
    #: Not a preference. Several of these vendors register an exact
    #: `http://localhost:<port>/callback`, and an exchange whose `redirect_uri`
    #: differs by even the port is refused -- so when the port is taken, the
    #: honest outcome is an error telling the user what holds it, not a
    #: silent rebind that fails later with an opaque 403.
    callback_port: int = 0
    callback_path: str = "/callback"
    #: Extra fixed parameters on the authorization request.
    extra_authorize_params: dict[str, str] = field(default_factory=dict)
    #: Sent as `Content-Type: application/json` rather than form encoding.
    token_json_body: bool = False
    #: Fixed extra fields on every token request.
    token_extra_params: dict[str, str] = field(default_factory=dict)
    #: Standard fields this vendor refuses. Named rather than inferred: an
    #: exchange carrying a parameter the endpoint does not expect fails with
    #: the same opaque 400 as one that is missing a required field.
    token_omit_params: tuple[str, ...] = ()
    #: Whether the authorization request carries a PKCE challenge.
    #:
    #: On by default and only turned off for vendors that reject it. A public
    #: client without PKCE has nothing binding the code to this process.
    use_pkce: bool = True
    #: Absolute lifetime of the grant family, in days, where the vendor caps it
    #: regardless of refresh rotation. Zero when there is no such cap.
    grant_ttl_days: int = 0
    #: Where usage is queried, when this account can report it.
    usage_url: str = ""

    @property
    def resolved_client_id(self) -> str:
        """The client id, from source or from the environment."""
        if self.client_id:
            return self.client_id
        return os.environ.get(self.client_id_env, "").strip()

    @property
    def resolved_client_secret(self) -> str:
        if self.client_secret:
            return self.client_secret
        return os.environ.get(self.client_secret_env, "").strip()

    @property
    def configured(self) -> bool:
        """Whether this account can be signed into on this machine."""
        return bool(self.resolved_client_id)

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.callback_port}{self.callback_path}"


#: Anthropic, via the client Claude Code itself uses.
#:
#: The authorization host matters: `platform.claude.com` issues console tokens
#: carrying only `org:create_api_key` and will not grant `user:inference`, so a
#: credential minted there cannot run a model. `claude.ai` is the one that can.
ANTHROPIC = OAuthProvider(
    id="anthropic",
    name="Claude",
    client_id="9d1c250a-e61b-44d9-88ed-5944d1962f5e",
    authorize_url="https://claude.ai/oauth/authorize",
    token_url="https://api.anthropic.com/v1/oauth/token",
    scopes=(
        "org:create_api_key user:profile user:inference "
        "user:sessions:claude_code user:mcp_servers user:file_upload"
    ),
    callback_port=54545,
    token_json_body=True,
    # The refresh family dies about thirty days after the interactive login no
    # matter how healthily it has rotated, so a re-login deadline is a real
    # thing to warn about rather than an edge case.
    grant_ttl_days=30,
    usage_url="https://api.anthropic.com/api/oauth/usage",
)

#: OpenAI, via the client Codex uses.
#:
#: The callback port is load-bearing: the redirect URI is registered as exactly
#: `http://localhost:1455/callback`, and binding elsewhere fails the exchange
#: with a 403 that says nothing about the port.
OPENAI_CODEX = OAuthProvider(
    id="openai_codex",
    name="Codex",
    client_id="app_EMoamEEZ73f0CkXaXp7hrann",
    authorize_url="https://auth.openai.com/oauth/authorize",
    token_url="https://auth.openai.com/oauth/token",
    scopes="openid profile email offline_access api.connectors.read api.connectors.invoke",
    callback_port=1455,
    # The account endpoint lives on the ChatGPT origin, not on the `/responses`
    # surface a proxy would forward -- pointing it at one 404s.
    usage_url="https://chatgpt.com/backend-api/wham/usage",
)

#: Google, via the client the Gemini CLI ships.
#:
#: The callback path is `/oauth2callback` rather than `/callback`: Google
#: matches the whole redirect URI, so the path is as fixed as the port.
GOOGLE_GEMINI = OAuthProvider(
    id="google_gemini",
    name="Gemini",
    client_id_env="LOOPFORGE_GOOGLE_GEMINI_CLIENT_ID",
    client_secret_env="LOOPFORGE_GOOGLE_GEMINI_CLIENT_SECRET",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=(
        "https://www.googleapis.com/auth/cloud-platform "
        "https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile"
    ),
    callback_port=8085,
    callback_path="/oauth2callback",
    # Without these Google issues an access token and no refresh token, so the
    # account silently stops working an hour after it is added.
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
)

#: GitHub Copilot. No redirect at all -- the user is given a code to type.
GITHUB_COPILOT = OAuthProvider(
    id="github_copilot",
    name="GitHub Copilot",
    client_id="Ov23li8tweQw6odWQebz",
    authorize_url="https://github.com/login/device",
    token_url="https://github.com/login/oauth/access_token",
    device_code_url="https://github.com/login/device/code",
    scopes="read:user",
    flow="device_code",
)

KIMI = OAuthProvider(
    id="kimi",
    name="Kimi",
    client_id="17e5f671-d194-4dfb-9706-5516cb48c098",
    authorize_url="https://auth.kimi.com/oauth/device",
    token_url="https://auth.kimi.com/api/oauth/token",
    device_code_url="https://auth.kimi.com/api/oauth/device_authorization",
    scopes="",
    flow="device_code",
    usage_url="https://api.kimi.com/coding/v1/usages",
)

XAI = OAuthProvider(
    id="xai",
    name="xAI",
    client_id="b1a00492-073a-47ea-816f-4c329264a828",
    authorize_url="https://auth.x.ai/oauth2/device",
    token_url="https://auth.x.ai/oauth2/token",
    device_code_url="https://auth.x.ai/oauth2/device/code",
    scopes="openid profile email offline_access grok-cli:access api:access",
    flow="device_code",
    usage_url="https://cli-chat-proxy.grok.com/v1/billing",
)

#: Z.ai. Its token endpoint takes a shape of its own: the account is named in
#: the body and the client id and verifier it does not expect are refused.
ZAI = OAuthProvider(
    id="zai",
    name="Z.ai",
    client_id="client_P8X5CMWmlaRO9gyO-KSqtg",
    authorize_url="https://chat.z.ai/api/oauth/authorize",
    token_url="https://zcode.z.ai/api/v1/oauth/token",
    scopes="",
    callback_port=54548,
    token_json_body=True,
    token_extra_params={"provider": "zai"},
    token_omit_params=("client_id", "code_verifier"),
    use_pkce=False,
    usage_url="https://api.z.ai/api/monitor/usage/quota/limit",
)

#: Google Antigravity, a second Google client with its own registration.
#:
#: Separate from Gemini rather than a variant of it: different client, port,
#: callback path and scopes, and signing into one says nothing about the other.
GOOGLE_ANTIGRAVITY = OAuthProvider(
    id="google_antigravity",
    name="Antigravity",
    client_id_env="LOOPFORGE_ANTIGRAVITY_CLIENT_ID",
    client_secret_env="LOOPFORGE_ANTIGRAVITY_CLIENT_SECRET",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=(
        "https://www.googleapis.com/auth/cloud-platform "
        "https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile "
        "https://www.googleapis.com/auth/cclog "
        "https://www.googleapis.com/auth/experimentsandconfigs"
    ),
    callback_port=51121,
    callback_path="/oauth-callback",
    extra_authorize_params={"access_type": "offline", "prompt": "consent"},
)

GITLAB_DUO = OAuthProvider(
    id="gitlab_duo",
    name="GitLab Duo",
    client_id="da4edff2e6ebd2bc3208611e2768bc1c1dd7be791dc5ff26ca34ca9ee44f7d4b",
    authorize_url="https://gitlab.com/oauth/authorize",
    token_url="https://gitlab.com/oauth/token",
    scopes="api",
    callback_port=8080,
)

PROVIDERS: tuple[OAuthProvider, ...] = (
    ANTHROPIC,
    OPENAI_CODEX,
    GOOGLE_GEMINI,
    GOOGLE_ANTIGRAVITY,
    GITHUB_COPILOT,
    KIMI,
    XAI,
    ZAI,
    GITLAB_DUO,
)


def providers() -> tuple[OAuthProvider, ...]:
    """Every signable account.

    A function rather than the tuple itself, so callers read the list at the
    moment they need it. Re-exporting the value gave two sources that could
    disagree -- a lookup resolving against one and a listing against the
    other -- which is exactly the kind of split that shows up as a provider
    that can be signed into but never appears in the UI.
    """
    return PROVIDERS


def provider(provider_id: str) -> OAuthProvider:
    """The provider with this id.

    Raises rather than returning None: every caller here is acting on a user's
    explicit choice from a list this module produced, so an unknown id is a
    bug in the caller and not a state to render.
    """
    for candidate in PROVIDERS:
        if candidate.id == provider_id:
            return candidate
    known = ", ".join(item.id for item in PROVIDERS)
    raise KeyError(f"Unknown OAuth provider {provider_id!r}. Known: {known}")
