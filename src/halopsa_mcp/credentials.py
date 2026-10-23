# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Per-request credentials, taken only from request headers.

The gateway sends each tenant's credentials on every request. They live in a
ContextVar for the duration of that request and are never stored anywhere else.

The middleware only checks that the headers are present. The platform probes
``tools/list`` with placeholder values, so formats (tenant name, base URL) are
validated later, inside the tools, by :func:`resolve_endpoints`.
"""

import contextvars
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import (
    BASE_URL_HEADER,
    CLIENT_ID_HEADER,
    CLIENT_SECRET_HEADER,
    HOSTED_DOMAIN,
    LOCATION_HEADERS,
    REQUIRED_HEADERS,
    TENANT_HEADER,
)


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str
    tenant: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class Endpoints:
    """Where to get a token and where the REST API lives."""

    root: str
    token_url: str
    api_url: str
    # Sent as ``?tenant=`` on the token request (hosted instances on a custom URL).
    tenant: str | None = None


_current: contextvars.ContextVar[Credentials | None] = contextvars.ContextVar("halopsa_credentials", default=None)


def current() -> Credentials | None:
    return _current.get()


class CredentialError(ValueError):
    pass


_TENANT_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def _clean(value: str | None) -> str | None:
    """Treat empty values and unresolved template placeholders (``${...}``, ``{{...}}``) as absent."""
    if value is None:
        return None
    text = value.strip()
    if not text or (text.startswith("${") and text.endswith("}")) or (text.startswith("{{") and text.endswith("}}")):
        return None
    return text


def _tenant_name(tenant: str) -> str:
    """Accept ``acme``, ``acme.halopsa.com`` or ``https://acme.halopsa.com`` and return ``acme``."""
    text = tenant.strip().lower()
    if "://" in text:
        text = urlparse(text).hostname or ""
    text = text.strip("/")
    suffix = "." + HOSTED_DOMAIN
    if text.endswith(suffix):
        text = text[: -len(suffix)]
    if not _TENANT_RE.match(text):
        raise CredentialError(
            f"{TENANT_HEADER} must be your HaloPSA tenant name (the part before .{HOSTED_DOMAIN}), "
            f"or send the instance URL in {BASE_URL_HEADER}."
        )
    return text


def resolve_endpoints(creds: Credentials) -> Endpoints:
    """The base URL wins over the tenant. ``https://<tenant>.halopsa.com`` is used when only a tenant is given."""
    base_url = _clean(creds.base_url)
    tenant = _clean(creds.tenant)
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise CredentialError(f"{BASE_URL_HEADER} must be an https URL, e.g. https://yourcompany.halopsa.com.")
        path = parsed.path.rstrip("/")
        # Accept the URL with or without the /api or /auth suffix copied from Halo's settings page.
        for suffix in ("/api", "/auth"):
            if path.lower().endswith(suffix):
                path = path[: -len(suffix)]
        root = f"https://{parsed.netloc}{path}"
        return Endpoints(root=root, token_url=f"{root}/auth/token", api_url=f"{root}/api", tenant=tenant)
    if tenant:
        root = f"https://{_tenant_name(tenant)}.{HOSTED_DOMAIN}"
        return Endpoints(root=root, token_url=f"{root}/auth/token", api_url=f"{root}/api")
    raise CredentialError(f"Send {TENANT_HEADER} or {BASE_URL_HEADER} so the server knows which HaloPSA to call.")


def _reject(message: str) -> JSONResponse:
    return JSONResponse(
        {
            "error": "Missing credentials",
            "message": message,
            "required_headers": REQUIRED_HEADERS,
            "one_of_headers": LOCATION_HEADERS,
        },
        status_code=401,
    )


class CredentialMiddleware:
    """Reads the HaloPSA headers on /mcp requests and binds them to the request context."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        headers = Request(scope).headers
        values = {name: (headers.get(name) or "").strip() for name in REQUIRED_HEADERS + LOCATION_HEADERS}
        missing = [name for name in REQUIRED_HEADERS if not values[name]]
        if not any(values[name] for name in LOCATION_HEADERS):
            missing.append(f"{TENANT_HEADER} or {BASE_URL_HEADER}")
        if missing:
            await _reject(f"Missing HaloPSA headers: {', '.join(missing)}.")(scope, receive, send)
            return

        token = _current.set(
            Credentials(
                client_id=values[CLIENT_ID_HEADER],
                client_secret=values[CLIENT_SECRET_HEADER],
                tenant=values[TENANT_HEADER] or None,
                base_url=values[BASE_URL_HEADER] or None,
            )
        )
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)
