# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Thin async client for the HaloPSA REST API.

Reference: HaloPSA API documentation (https://halo.halopsa.com/apidoc/ and each instance's /apidoc/).
- OAuth2 client credentials: ``POST <root>/auth/token`` with ``grant_type=client_credentials``,
  ``client_id``, ``client_secret`` and ``scope=all``; hosted instances may also need ``?tenant=``.
- Resource server ``<root>/api``; ``Authorization: Bearer <token>``.
- Creates and updates are ``POST /<Resource>`` with a JSON array; an object with ``id`` is an update.
- Lists accept ``pageinate``/``page_size``/``page_no`` or ``count``; many wrap rows as
  ``{"record_count": n, "<resource>": [...]}`` while some return a bare array.

A token is fetched once per tool call and never kept beyond it.
"""

import asyncio
import email.utils
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .credentials import Credentials, Endpoints, resolve_endpoints

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF = 20.0
USER_AGENT = "mspbots-halopsa-mcp/1.0"


@dataclass
class ApiError(Exception):
    code: str
    message: str
    retryable: bool = False
    status: int | None = None

    def __str__(self) -> str:
        return self.message


def _status_to_error(status: int, detail: str) -> ApiError:
    if status in (401, 403):
        return ApiError(
            "unauthorized",
            f"HaloPSA refused the request ({status}). Check the API application's permissions. {detail}".strip(),
            False,
            status,
        )
    if status == 404:
        return ApiError("not_found", f"Not found in HaloPSA. {detail}".strip(), False, status)
    if status == 400 and "not found" in detail.lower():
        # Halo answers a write to a missing record with 400 "Record not found" / "Ticket not found."
        return ApiError("not_found", f"Not found in HaloPSA. {detail}".strip(), False, status)
    if status in (400, 405, 409, 415, 422):
        return ApiError("invalid_argument", f"HaloPSA refused the request ({status}). {detail}".strip(), False, status)
    if status == 429:
        return ApiError("rate_limited", "HaloPSA rate limit reached. Try again shortly.", True, status)
    return ApiError("upstream_error", f"HaloPSA returned {status}. {detail}".strip(), status >= 500, status)


def error_detail(response: httpx.Response) -> str:
    """HaloPSA's own explanation, from a JSON or plain-text error body."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:500]
    if isinstance(body, dict):
        for key in ("error_description", "message", "Message", "detail", "title", "error", "ClassName"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    if isinstance(body, str):
        return body.strip()[:500]
    return str(body)[:500]


def _retry_after(response: httpx.Response, attempt: int) -> float:
    value = response.headers.get("retry-after")
    if value:
        try:
            return min(float(value), MAX_BACKOFF)
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(value)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                return max(0.0, min(parsed.timestamp() - time.time(), MAX_BACKOFF))
    return min(2.0**attempt, MAX_BACKOFF)


class HaloClient:
    """One instance per tool call; wraps a single httpx client and one access token for that call."""

    def __init__(self, creds: Credentials, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._creds = creds
        self.endpoints: Endpoints = resolve_endpoints(creds)
        self._token: str | None = None
        self._deadline = time.monotonic() + settings.call_budget_seconds
        self._http = httpx.AsyncClient(
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout),
            transport=transport,
        )

    async def __aenter__(self) -> "HaloClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send with retries on 429/5xx/timeouts, honouring Retry-After and the per-call budget."""
        attempt = 0
        while True:
            try:
                response = await self._http.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                if attempt < self._settings.max_retries and time.monotonic() + 1 < self._deadline:
                    attempt += 1
                    await asyncio.sleep(min(2.0**attempt, MAX_BACKOFF))
                    continue
                raise ApiError("upstream_error", "HaloPSA did not respond in time.", True) from exc
            except httpx.HTTPError as exc:
                raise ApiError("upstream_error", f"Could not reach HaloPSA: {type(exc).__name__}.", True) from exc

            if response.status_code in RETRY_STATUSES and attempt < self._settings.max_retries:
                wait = _retry_after(response, attempt + 1)
                if time.monotonic() + wait < self._deadline:
                    attempt += 1
                    await asyncio.sleep(wait)
                    continue
            return response

    async def token(self) -> str:
        if self._token:
            return self._token
        params = {"tenant": self.endpoints.tenant} if self.endpoints.tenant else None
        response = await self._send(
            "POST",
            self.endpoints.token_url,
            params=params,
            data={
                "grant_type": "client_credentials",
                "client_id": self._creds.client_id,
                "client_secret": self._creds.client_secret,
                "scope": "all",
            },
        )
        if response.status_code in (400, 401, 403):
            raise ApiError(
                "unauthorized",
                "HaloPSA did not accept the client ID / secret "
                f"({response.status_code}). {error_detail(response)}".strip(),
                False,
                response.status_code,
            )
        if response.status_code == 404:
            raise ApiError(
                "not_configured",
                f"No HaloPSA authorisation server at {self.endpoints.token_url}. Check the tenant or base URL.",
                False,
                404,
            )
        if response.status_code >= 400:
            raise _status_to_error(response.status_code, error_detail(response))
        try:
            token = response.json().get("access_token")
        except (ValueError, AttributeError):
            token = None
        if not token:
            raise ApiError("upstream_error", "HaloPSA token response had no access_token.", True)
        self._token = token
        return token

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> Any:
        token = await self.token()
        clean = {k: _param(v) for k, v in (params or {}).items() if v is not None and v != ""}
        response = await self._send(
            method,
            f"{self.endpoints.api_url}{path}",
            params=clean,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code >= 400:
            raise _status_to_error(response.status_code, error_detail(response))
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError("upstream_error", "HaloPSA returned a response that is not JSON.", True) from exc

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: Any, params: dict[str, Any] | None = None) -> Any:
        return await self.request("POST", path, body=body, params=params)


def _param(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


# ---- response helpers -------------------------------------------------------


def rows(payload: Any, key: str) -> list[dict[str, Any]]:
    """Rows of a list response, whether Halo wraps them (``{"<key>": [...]}``) or not (``[...]``)."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        value = payload.get(key)
        if not isinstance(value, list):
            # Some endpoints use a different wrapper key; take the first list of objects.
            value = next((v for v in payload.values() if isinstance(v, list)), [])
        return [r for r in value if isinstance(r, dict)]
    return []


def record_count(payload: Any) -> int | None:
    if isinstance(payload, dict) and isinstance(payload.get("record_count"), int):
        return payload["record_count"]
    return None


def first(payload: Any) -> dict[str, Any]:
    """The object returned by a POST (Halo returns the first saved object, sometimes in a list)."""
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    return payload if isinstance(payload, dict) else {}
