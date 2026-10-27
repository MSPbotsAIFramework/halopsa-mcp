# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Shared plumbing for tool handlers."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .. import _json
from ..api import ApiError, HaloClient, record_count
from ..api import rows as api_rows
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


Offset = Annotated[
    int | None,
    Field(description="Record position to start from (0-based). Pass next_offset from the previous result.", ge=0),
]


def _result(items: list[Any], size: int, start: int, has_more: bool, total: int | None) -> dict[str, Any]:
    """Standard list result. ``next_offset`` continues right after the last record returned,
    also when the shared size cap cuts the page (``_resume``)."""
    out: dict[str, Any] = {"items": items, "count": len(items), "limit": size, "offset": start, "has_more": has_more}
    if total is not None:
        out["total_count"] = total
    if has_more:
        out["next_offset"] = start + len(items)
    out["_resume"] = {"key": "next_offset", "start": start}
    return out


def window(rows: list[dict[str, Any]], size: int, offset: int | None) -> dict[str, Any]:
    """List result for an endpoint read whole: ``rows`` is the full list, sliced here."""
    start = max(int(offset or 0), 0)
    return _result(rows[start : start + size], size, start, len(rows) > start + size, len(rows))


async def fetch_page(
    client: HaloClient, path: str, key: str, params: dict[str, Any], size: int, offset: int | None
) -> dict[str, Any]:
    """List result for an endpoint Halo pages (``pageinate``/``page_size``/``page_no``).

    The page holding ``offset`` is fetched and the records before ``offset`` are skipped, so a result
    may hold fewer than ``size`` records; ``next_offset`` then starts at the next page.
    """
    start = max(int(offset or 0), 0)
    number = start // size + 1
    first = (number - 1) * size
    payload = await client.get(path, {**params, "pageinate": True, "page_size": size, "page_no": number})
    rows = api_rows(payload, key)
    total = record_count(payload)
    has_more = total > first + len(rows) if total is not None else len(rows) >= size
    return _result(rows[start - first :], size, start, has_more, total)


# Halo writes "no date" as 1899-12-30 / 1900-01-01.
NO_DATE_BEFORE = "1901-01-01"
CUSTOM_FIELD_KEYS = ("id", "name", "label", "value", "display")


def _empty(value: Any) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return True
    return isinstance(value, str) and value[:4].isdigit() and value[4:5] == "-" and value[:10] < NO_DATE_BEFORE


def custom_fields(values: Any) -> list[dict[str, Any]]:
    """Custom fields that hold a value, each as id / name / label / value / display.

    Halo sends every custom field with its whole definition (about 70 properties) whether it is set or not.
    """
    out = []
    for cf in values if isinstance(values, list) else []:
        if isinstance(cf, dict) and not _empty(cf.get("value")):
            out.append({k: cf[k] for k in CUSTOM_FIELD_KEYS if not _empty(cf.get(k))})
    return out


def slim(record: dict[str, Any], fields: tuple[str, ...] | None = None) -> dict[str, Any]:
    """A record as agents need it: related records reduced to id and name, empty values and "no date"
    dates dropped, custom fields reduced to the ones set, and, when ``fields`` is given, only those fields."""
    out: dict[str, Any] = {}
    for key, value in collapse(record).items():
        if fields is not None and key not in fields:
            continue
        if key == "customfields":
            value = custom_fields(value)
        if not _empty(value):
            out[key] = value
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
