from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterator
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class KuraAgentError(RuntimeError):
    """A structured local daemon communication failure."""

    def __init__(self, message: str, code: str = "KURA_UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code


class KuraClient:
    def __init__(
        self, base_url: str, timeout: float = 2.0, token: str | None = None
    ) -> None:
        self.base_url = self._validate_base_url(base_url)
        self.timeout = timeout
        # Kura protects every /v1 route with a bearer token; only /healthz is
        # open. A client without one can check liveness but nothing else.
        self.token = token or None

    @staticmethod
    def _validate_base_url(base_url: str) -> str:
        try:
            parsed = urllib.parse.urlsplit(base_url.strip())
            port = parsed.port
        except ValueError as exc:
            raise KuraAgentError("Kura URL is invalid", "KURA_INVALID_URL") from exc
        try:
            host_is_loopback = (
                parsed.hostname == "localhost"
                or ipaddress.ip_address(parsed.hostname or "").is_loopback
            )
        except ValueError:
            host_is_loopback = False
        if (
            parsed.scheme != "http"
            or not host_is_loopback
            or parsed.username is not None
            or parsed.password is not None
            or port is None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise KuraAgentError(
                "Kura URL must be a loopback HTTP origin with an explicit port",
                "KURA_INVALID_URL",
            )
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    def _url(self, path: str, query: dict[str, str] | None = None) -> str:
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "?" in path
            or "#" in path
        ):
            raise KuraAgentError(
                "Kura request path must be absolute",
                "KURA_INVALID_URL",
            )
        url = f"{self.base_url}{path}"
        if not query:
            return url
        # Query values are encoded here rather than interpolated into `path`,
        # so the path stays subject to the checks above and a caller cannot
        # smuggle a fragment or a second query through a parameter.
        return f"{url}?{urllib.parse.urlencode(query)}"

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            self._url(path, query), headers=self._headers(), method="GET"
        )
        return self._request(request, "GET", path)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=payload,
            headers=self._headers({"Content-Type": "application/json"}),
            method="POST",
        )
        return self._request(request, "POST", path)

    def put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=payload,
            headers=self._headers({"Content-Type": "application/json"}),
            method="PUT",
        )
        return self._request(request, "PUT", path)

    def delete(self, path: str) -> dict[str, Any]:
        """Delete a resource. A 204 with no body yields an empty mapping."""
        request = urllib.request.Request(
            self._url(path), headers=self._headers(), method="DELETE"
        )
        return self._request(request, "DELETE", path, allow_empty=True)

    def stream(
        self, path: str, body: dict[str, Any], timeout: float | None = None
    ) -> Iterator[tuple[str, str]]:
        """Yield `(event, data)` pairs from a Server-Sent Events response.

        Consumed lazily so a caller sees the first token without waiting for
        the run to finish -- the entire reason for using the streaming route.
        The socket timeout applies per read rather than to the whole stream, so
        a long generation does not trip it while a stalled one still does.
        """
        payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=payload,
            headers=self._headers(
                {"Content-Type": "application/json", "Accept": "text/event-stream"}
            ),
            method="POST",
        )
        try:
            response = urllib.request.urlopen(
                request, timeout=timeout if timeout is not None else self.timeout
            )
        except urllib.error.HTTPError as exc:
            raise KuraAgentError(
                f"Kura request failed: POST {path} returned HTTP {exc.code}",
                "KURA_REQUEST_FAILED",
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise KuraAgentError(f"Kura request failed: POST {path}") from exc

        with response:
            event = ""
            data: list[str] = []
            for raw in response:
                line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                if not line:
                    # A blank line terminates one event; SSE allows an event to
                    # carry several data lines, which are joined with newlines.
                    if data:
                        yield event or "message", "\n".join(data)
                    event, data = "", []
                    continue
                if line.startswith(":"):
                    continue  # comment/keepalive
                field, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if field == "event":
                    event = value
                elif field == "data":
                    data.append(value)
            if data:
                yield event or "message", "\n".join(data)

    def _request(
        self,
        request: urllib.request.Request,
        method: str,
        path: str,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw.strip() and allow_empty:
                    return {}
                payload = json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise KuraAgentError(
                f"Kura request failed: {method} {path} returned HTTP {exc.code}",
                "KURA_REQUEST_FAILED",
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise KuraAgentError(f"Kura request failed: {method} {path}") from exc
        if not isinstance(payload, dict):
            raise KuraAgentError(
                f"Kura returned a non-object response for {path}",
                "KURA_INVALID_RESPONSE",
            )
        return payload


# Compatibility aliases for clients written before the Kura rename.
DopeAgentClient = KuraClient
DopeAgentError = KuraAgentError
