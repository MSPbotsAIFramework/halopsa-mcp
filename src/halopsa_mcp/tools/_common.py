# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Shared plumbing for tool handlers."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .. import _json
from ..api import ApiError, HaloClient
from ..config import BASE_URL_HEADER, CLIENT_ID_HEADER, CLIENT_SECRET_HEADER, TENANT_HEADER, Settings
from ..credentials import CredentialError, current

log = logging.getLogger("halopsa_mcp")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
CREATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
UPDATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

HALO_AGENT_ID_DESC = (
    "ID of an agent in HaloPSA, as returned by halopsa_agents_list. Not an agent ID from the calling platform."
)
FULL_RESPONSE_DESC = (
    "Return the ticket exactly as HaloPSA sends it, with related records (ticket type, priority, user) "
    "expanded in full. Off by default: that reply can be very large, mostly the ticket type definition."
)
INCLUDE_INACTIVE_DESC = "Include inactive"


def _limit(default: int, maximum: int = MAX_LIMIT) -> Any:
    return Annotated[int | None, Field(description=f"Maximum number of results (default: {default}, max {maximum}).")]


Limit25 = _limit(25)
Limit50 = _limit(50)
Limit100 = _limit(100)
TicketLimit = _limit(50, 100)  # Halo caps ticket pages at 100.


def cap(limit: int | None, default: int = DEFAULT_LIMIT, maximum: int = MAX_LIMIT) -> int:
    return min(max(int(limit or default), 1), maximum)


def listing(
    items: list[dict[str, Any]], limit: int, *, total: int | None = None, offset: int = 0, **extra: Any
) -> dict[str, Any]:
    """Standard list result. ``items`` may hold one row more than ``limit``, which signals more results."""
    shown = items[:limit]
    has_more = len(items) > limit or (total is not None and total > offset + len(shown))
    out: dict[str, Any] = {"items": shown, "count": len(shown), "limit": limit, "has_more": has_more}
    if total is not None:
        out["total_count"] = total
    out.update(extra)
    return out


Handler = Callable[[HaloClient], Awaitable[Any]]


async def run(settings: Settings, handler: Handler) -> str:
    """Execute ``handler`` with a client bound to this request's credentials.

    Always returns a string: the JSON result, or an error envelope.
    """
    creds = current()
    if creds is None:
        return _json.error(
            "not_configured",
            f"No HaloPSA credentials. Send {CLIENT_ID_HEADER}, {CLIENT_SECRET_HEADER} and "
            f"{TENANT_HEADER} or {BASE_URL_HEADER}.",
        )
    try:
        async with HaloClient(creds, settings) as client:
            result = await handler(client)
    except CredentialError as exc:
        return _json.error("not_configured", str(exc))
    except ApiError as exc:
        return _json.error(exc.code, exc.message, exc.retryable)
    except ToolInputError as exc:
        return _json.error("invalid_argument", str(exc))
    except Exception:  # noqa: BLE001 - tools must never raise
        log.exception("unexpected error in tool handler")
        return _json.error("upstream_error", "Unexpected error while calling HaloPSA.", True)
    return result if isinstance(result, str) else _json.dump(result)


class ToolInputError(ValueError):
    """Raised by handlers for arguments HaloPSA would reject anyway."""


def seg(value: object) -> str:
    """Path segment for an ID. Only plain positive integers are accepted, so IDs cannot alter the URL path."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if not text.isdigit():
        raise ToolInputError(f"Expected a numeric ID, got {text!r}.")
    return text


def collapse(record: dict[str, Any]) -> dict[str, Any]:
    """Replace related records Halo expands in full (``{"id": .., ...}``) with ``{"id", "name"}``."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, dict) and "id" in value:
            ref = {"id": value.get("id")}
            for name_key in ("name", "value", "summary", "emailaddress"):
                if value.get(name_key) not in (None, ""):
                    ref[name_key] = value[name_key]
                    break
            out[key] = ref
        else:
            out[key] = value
    return out


def pick(record: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {k: record[k] for k in fields if k in record and record[k] is not None}
