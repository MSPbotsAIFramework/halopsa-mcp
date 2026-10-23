# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Reference tables used when writing tickets: statuses, priorities, ticket types and categories."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import _json, api
from ..config import Settings
from ._common import READ, cap, run

Kind = Literal["statuses", "priorities", "ticket_types", "categories"]
ALL_KINDS: tuple[Kind, ...] = ("statuses", "priorities", "ticket_types", "categories")
DEFAULT_ROWS = 200
INACTIVE_FLAGS = ("inactive", "isdisabled", "hidden", "disabled")

FIELDS: dict[str, tuple[str, ...]] = {
    "statuses": ("id", "name", "shortname", "type"),
    "priorities": ("id", "priorityid", "name", "slaid"),
    "ticket_types": ("id", "name", "group_id", "group_name"),
    "categories": ("id", "value", "type_id", "category_name"),
}
NOTES = {
    "priorities": (
        "A ticket's priority_id is the row's priorityid (shown as ticket_priority_id), which can differ from the "
        "row id when the tenant has several SLAs."
    ),
    "categories": "Pass a row's value verbatim as category_1..category_4 (matching its type_id).",
}


def _active(row: dict[str, Any]) -> bool:
    return not any(row.get(flag) is True for flag in INACTIVE_FLAGS)


def _project(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row[k] for k in FIELDS[kind] if row.get(k) not in (None, "")}
    if kind == "priorities":
        out["ticket_priority_id"] = row.get("priorityid", row.get("id"))
    return out


def _fit(result: dict[str, Any]) -> dict[str, Any]:
    """Keep the reply under the size limit by trimming the largest table first, flagging what was cut."""
    while len(_json.compact(result)) > _json.MAX_CHARS:
        tables = [v for v in result.values() if isinstance(v, dict) and v.get("items")]
        if not tables:
            break
        biggest = max(tables, key=lambda t: len(_json.compact(t["items"])))
        keep = max(len(biggest["items"]) * 3 // 4, 0) if len(biggest["items"]) > 1 else 0
        biggest["items"] = biggest["items"][:keep]
        biggest["count"] = keep
        biggest["has_more"] = True
        biggest["truncated"] = True
    return result


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="halopsa_lookups_get",
        description=(
            "Read HaloPSA's reference tables (ticket statuses, priorities, ticket types and the four "
            "categorisation trees, Category 1-4) so ids and category values come from the live tenant instead of "
            "being hardcoded. Returns every requested table in one call. Use it before halopsa_tickets_create or "
            "halopsa_tickets_update to resolve a name to the id or string those tools expect."
        ),
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_lookups_get(
        kinds: Annotated[
            list[Kind] | None,
            Field(
                description=(
                    "Which reference tables to read. Defaults to all four. Ask for only what you need; "
                    "categories is by far the largest."
                )
            ),
        ] = None,
        category_type_id: Annotated[
            Literal[1, 2, 3, 4] | None,
            Field(
                description=(
                    "Restrict categories to one of Halo's four categorisation trees: 1 = Category 1, "
                    "2 = Category 2, 3 = Category 3, 4 = Category 4. Omit to read all four; every row carries its "
                    "own type_id either way."
                )
            ),
        ] = None,
        tickettype_id: Annotated[
            int | None,
            Field(
                description=(
                    "Ask Halo to restrict statuses and categories to those valid for this ticket type. Whether it "
                    "narrows the list depends on how the tenant configured those restrictions."
                )
            ),
        ] = None,
        include_inactive: Annotated[
            bool | None, Field(description="Include inactive/hidden rows. Off by default.")
        ] = None,
        limit: Annotated[
            int | None,
            Field(
                description=(
                    f"Maximum rows per kind (default: {DEFAULT_ROWS}, max 200). Narrow with category_type_id or "
                    "tickettype_id rather than raising this."
                ),
            ),
        ] = None,
        full_response: Annotated[
            bool | None,
            Field(description="Return rows exactly as HaloPSA sends them instead of the identifying fields."),
        ] = None,
    ) -> str:
        size = cap(limit, DEFAULT_ROWS)
        wanted = list(dict.fromkeys(kinds or ALL_KINDS))

        async def fetch(client: api.HaloClient, kind: str) -> list[dict[str, Any]]:
            if kind == "statuses":
                return api.rows(await client.get("/Status", {"type": "ticket", "tickettype_id": tickettype_id}), "")
            if kind == "priorities":
                return api.rows(await client.get("/Priority"), "priorities")
            if kind == "ticket_types":
                params = {"showinactive": True if include_inactive else None}
                return api.rows(await client.get("/TicketType", params), "tickettypes")
            params = {"type_id": category_type_id, "tickettype_id": tickettype_id}
            return api.rows(await client.get("/Category", params), "categories")

        async def handler(client: api.HaloClient):
            result: dict[str, Any] = {}
            for kind in wanted:
                try:
                    found = await fetch(client, kind)
                except api.ApiError as exc:
                    if exc.code in ("unauthorized", "not_configured"):
                        raise
                    result[kind] = {"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}}
                    continue
                if kind == "categories" and category_type_id is not None:
                    found = [r for r in found if r.get("type_id") in (None, category_type_id)]
                if not include_inactive:
                    found = [r for r in found if _active(r)]
                rows = found if full_response else [_project(kind, r) for r in found]
                entry: dict[str, Any] = {"items": rows[:size], "count": len(rows[:size]), "has_more": len(rows) > size}
                if kind in NOTES:
                    entry["note"] = NOTES[kind]
                result[kind] = entry
            return _fit(result)

        return await run(settings, handler)
