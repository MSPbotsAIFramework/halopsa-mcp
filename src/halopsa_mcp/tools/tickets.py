# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Tickets and ticket actions (notes).

HaloPSA saves tickets and actions with ``POST /Tickets`` / ``POST /Actions`` and a JSON array;
an object that carries ``id`` updates the existing record.
"""

from datetime import datetime
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import api
from ..config import Settings
from ._common import (
    CREATE,
    FULL_RESPONSE_DESC,
    HALO_AGENT_ID_DESC,
    READ,
    UPDATE,
    Offset,
    TicketLimit,
    ToolInputError,
    cap,
    fetch_page,
    pick,
    run,
    seg,
    slim,
)

MAX_TICKET_PAGE = 100
ACTION_FIELDS = (
    "id",
    "ticket_id",
    "datetime",
    "who",
    "outcome",
    "note",
    "timetaken",
    "hiddenfromuser",
    "important",
    "new_status",
)
DEFAULT_ACTIONS = 20
MAX_ACTIONS = 100
# What a ticket returns by default. Halo's ticket has about 1,000 fields, most of them settings; with
# its custom field definitions a new ticket is about 70,000 characters.
TICKET_FIELDS = (
    "id",
    "summary",
    "details",
    "status_id",
    "status_name",
    "status",
    "tickettype_id",
    "tickettype_name",
    "tickettype",
    "priority_id",
    "priority",
    "impact",
    "urgency",
    "client_id",
    "client_name",
    "site_id",
    "site_name",
    "user_id",
    "user_name",
    "user_email",
    "reportedby",
    "agent_id",
    "agent_name",
    "team_id",
    "team",
    "category_1",
    "category_2",
    "category_3",
    "category_4",
    "sla_id",
    "onhold",
    "parent_id",
    "child_count",
    "dateoccurred",
    "datecreated",
    "lastactiondate",
    "targetdate",
    "deadlinedate",
    "respondbydate",
    "fixbydate",
    "dateclosed",
    "estimate",
    "timetaken",
    "emailtolist",
    "emailcclist",
    "workflow_stage",
    "customfields",
)

FullResponse = Annotated[bool | None, Field(description=FULL_RESPONSE_DESC)]


def _category_desc(n: int) -> str:
    return (
        f'Category {n} as its full path string, e.g. "Hardware>Laptop". Resolve one with halopsa_lookups_get '
        f'(kinds: ["categories"], category_type_id: {n}) and pass that row\'s `value` verbatim; '
        "this is not an id field."
    )


Category1 = Annotated[str | None, Field(description=_category_desc(1))]
Category2 = Annotated[str | None, Field(description=_category_desc(2))]
Category3 = Annotated[str | None, Field(description=_category_desc(3))]
Category4 = Annotated[str | None, Field(description=_category_desc(4))]
AgentId = Annotated[int | None, Field(description=HALO_AGENT_ID_DESC)]


class CustomField(BaseModel):
    id: Annotated[int | None, Field(description="Custom field id, e.g. 291.")] = None
    name: Annotated[
        str | None, Field(description="Custom field name, e.g. CFEscalated. Use when the id is unknown.")
    ] = None
    value: Annotated[str | int | float | bool | None, Field(description="New value; null clears the field.")]


def _iso(name: str, value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolInputError(f"{name} must be an ISO-8601 date, e.g. 2026-04-06T00:00:00Z.") from exc
    return value.strip()


def _ticket(raw: Any, full: bool | None) -> dict[str, Any]:
    record = api.first(raw)
    return record if full else slim(record, TICKET_FIELDS)


def _missing_ticket(ticket_id: int):
    """Halo answers a write to a missing ticket with 400; report it as not_found naming the ticket."""
    return api.ApiError("not_found", f"No ticket {ticket_id} in HaloPSA.", False, 404)


def _categories(values: dict[str, str | None]) -> dict[str, str]:
    return {k: v for k, v in values.items() if v is not None}


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="halopsa_tickets_list",
        description=(
            "List tickets with optional filters by client, status, agent, open/closed state, or date occurred range"
        ),
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_tickets_list(
        client_id: int | None = None,
        status_id: int | None = None,
        halo_agent_id: AgentId = None,
        open_only: bool | None = None,
        closed_only: bool | None = None,
        dateoccurred_start: Annotated[
            str | None, Field(description="ISO-8601 start date for tickets (e.g. 2026-04-06T00:00:00Z)")
        ] = None,
        dateoccurred_end: Annotated[str | None, Field(description="ISO-8601 end date for tickets")] = None,
        limit: TicketLimit = None,
        page_no: Annotated[
            int | None, Field(description="Page number (1-indexed). Prefer offset / next_offset, which never skip.")
        ] = None,
        team_id: Annotated[
            int | None, Field(description="Only tickets assigned to this team (halopsa_teams_list).")
        ] = None,
        search: Annotated[str | None, Field(description="Free-text search across tickets.")] = None,
        offset: Offset = None,
    ) -> str:
        size = cap(limit, 50, MAX_TICKET_PAGE)
        position = offset if offset is not None else (max(int(page_no or 1), 1) - 1) * size

        async def handler(client: api.HaloClient):
            if open_only and closed_only:
                raise ToolInputError("open_only and closed_only cannot both be true.")
            start = _iso("dateoccurred_start", dateoccurred_start)
            end = _iso("dateoccurred_end", dateoccurred_end)
            params: dict[str, Any] = {
                "client_id": client_id,
                "status_id": status_id,
                "agent_id": halo_agent_id,
                "team": team_id,
                "open_only": open_only or None,
                "closed_only": closed_only or None,
                "search": search,
            }
            if start or end:
                params.update({"datesearch": "dateoccurred", "startdate": start, "enddate": end})
            return await fetch_page(client, "/Tickets", "tickets", params, size, position)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_tickets_get",
        description="Get ticket details by ID",
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_tickets_get(
        ticket_id: int,
        include_actions: Annotated[bool | None, Field(description="Include actions/notes")] = None,
        full_response: FullResponse = None,
        actions_limit: Annotated[
            int | None, Field(description=f"Actions per call (default {DEFAULT_ACTIONS}, max {MAX_ACTIONS}).")
        ] = None,
        actions_offset: Annotated[
            int | None,
            Field(description="Action position to start from (0-based). Pass next_actions_offset.", ge=0),
        ] = None,
    ) -> str:
        size = cap(actions_limit, DEFAULT_ACTIONS, MAX_ACTIONS)
        start = actions_offset or 0

        async def handler(client: api.HaloClient):
            ticket = _ticket(await client.get(f"/Tickets/{seg(ticket_id)}", {"includedetails": True}), full_response)
            if not include_actions and actions_offset is None:
                return ticket
            # /Actions takes only count, so the actions before the offset are read and skipped.
            payload = await client.get("/Actions", {"ticket_id": seg(ticket_id), "count": start + size + 1})
            rows = api.rows(payload, "actions")
            actions = rows[start : start + size]
            result: dict[str, Any] = {
                "ticket": ticket,
                "actions": actions if full_response else [pick(a, ACTION_FIELDS) for a in actions],
                "actions_offset": start,
            }
            if len(rows) > start + size:
                result["next_actions_offset"] = start + size
            result["_resume"] = {"key": "next_actions_offset", "start": start}
            return result

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_tickets_create",
        description="Create ticket",
        annotations=CREATE,
        structured_output=False,
    )
    async def halopsa_tickets_create(
        summary: str,
        client_id: int,
        tickettype_id: int,
        details: str | None = None,
        priority_id: int | None = None,
        halo_agent_id: AgentId = None,
        site_id: int | None = None,
        category_1: Category1 = None,
        category_2: Category2 = None,
        category_3: Category3 = None,
        category_4: Category4 = None,
        full_response: FullResponse = None,
        team_id: Annotated[int | None, Field(description="Assigned team, by ID (halopsa_teams_list).")] = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            if not summary.strip():
                raise ToolInputError("summary must not be empty.")
            await _require(client, f"/Client/{seg(client_id)}", f"No client {client_id} in HaloPSA.")
            body: dict[str, Any] = {
                "summary": summary,
                "details": details,
                "client_id": client_id,
                "tickettype_id": tickettype_id,
                "priority_id": priority_id,
                "agent_id": halo_agent_id,
                "site_id": site_id,
                **_categories(
                    {
                        "category_1": category_1,
                        "category_2": category_2,
                        "category_3": category_3,
                        "category_4": category_4,
                    }
                ),
            }
            if team_id is not None:
                body.update(await _team_fields(client, team_id))
            body = {k: v for k, v in body.items() if v is not None}
            return _ticket(await client.post("/Tickets", [body]), full_response)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_tickets_update",
        description=(
            "Update ticket, including reassigning it to a different agent or team, changing its ticket type, "
            "categories or custom fields. Only the fields provided are changed."
        ),
        annotations=UPDATE,
        structured_output=False,
    )
    async def halopsa_tickets_update(
        ticket_id: int,
        summary: str | None = None,
        details: str | None = None,
        status_id: int | None = None,
        priority_id: int | None = None,
        tickettype_id: Annotated[
            int | None,
            Field(
                description=(
                    "New ticket type, by HaloPSA ticket type ID. Resolve a name to an ID with halopsa_lookups_get "
                    '(kinds: ["ticket_types"]). Halo records the change as a hidden action on the ticket. '
                    "Omit to leave the ticket type unchanged."
                )
            ),
        ] = None,
        halo_agent_id: Annotated[
            int | None,
            Field(
                description=(
                    "Assigned agent, by HaloPSA agent ID. Resolve a name to an ID with halopsa_agents_list. "
                    "Not an agent ID from the calling platform."
                )
            ),
        ] = None,
        team_id: Annotated[
            int | None, Field(description="Assigned team, by ID. Resolve a name to an ID with halopsa_teams_list.")
        ] = None,
        category_1: Category1 = None,
        category_2: Category2 = None,
        category_3: Category3 = None,
        category_4: Category4 = None,
        custom_fields: Annotated[
            list[CustomField] | None,
            Field(
                description=(
                    "Custom fields to write. Address each field by id or by name; match the value to the field "
                    "type (checkbox takes a boolean)."
                )
            ),
        ] = None,
        full_response: FullResponse = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            tid = int(seg(ticket_id))
            body: dict[str, Any] = {
                "summary": summary,
                "details": details,
                "status_id": status_id,
                "priority_id": priority_id,
                "agent_id": halo_agent_id,
                **_categories(
                    {
                        "category_1": category_1,
                        "category_2": category_2,
                        "category_3": category_3,
                        "category_4": category_4,
                    }
                ),
            }
            body = {k: v for k, v in body.items() if v is not None}
            if custom_fields:
                body["customfields"] = [_custom_field(cf) for cf in custom_fields]
            if team_id is not None:
                body.update(await _team_fields(client, team_id))
            if not body and tickettype_id is None:
                raise ToolInputError("Nothing to update: pass at least one field to change.")

            saved: Any = None
            if body:
                try:
                    saved = await client.post("/Tickets", [{"id": tid, **body}])
                except api.ApiError as exc:
                    if exc.code == "not_found":
                        raise _missing_ticket(tid) from exc
                    raise
            if tickettype_id is not None:
                if not body:
                    await _require(client, f"/Tickets/{tid}", f"No ticket {tid} in HaloPSA.")
                await _change_ticket_type(client, tid, tickettype_id)
                saved = await client.get(f"/Tickets/{tid}", {"includedetails": True})
                actual = api.first(saved).get("tickettype_id")
                if actual is not None and int(actual) != int(tickettype_id):
                    raise api.ApiError(
                        "upstream_error",
                        f"HaloPSA accepted the request but ticket {tid} still has ticket type {actual}, "
                        f"not {tickettype_id}. The type may not be allowed for this ticket or its status.",
                        False,
                    )
            if not api.first(saved):
                saved = await client.get(f"/Tickets/{tid}", {"includedetails": True})
            return _ticket(saved, full_response)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_tickets_add_action",
        description="Add note to ticket",
        annotations=CREATE,
        structured_output=False,
    )
    async def halopsa_tickets_add_action(
        ticket_id: int,
        note: str,
        outcome: Annotated[str | None, Field(description="Action outcome label (default: Note).")] = None,
        timetaken: Annotated[float | None, Field(description="Minutes")] = None,
        hidden_from_user: bool | None = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            if not note.strip():
                raise ToolInputError("note must not be empty.")
            body: dict[str, Any] = {
                "ticket_id": int(seg(ticket_id)),
                "note": note,
                "outcome": outcome or "Note",
            }
            if timetaken is not None:
                if timetaken < 0:
                    raise ToolInputError("timetaken must not be negative.")
                # Halo stores action time in hours.
                body["timetaken"] = round(timetaken / 60.0, 4)
            if hidden_from_user is not None:
                body["hiddenfromuser"] = hidden_from_user
            try:
                saved = await client.post("/Actions", [body])
            except api.ApiError as exc:
                if exc.code == "not_found":
                    raise _missing_ticket(body["ticket_id"]) from exc
                raise
            return pick(api.first(saved), ACTION_FIELDS)

        return await run(settings, handler)


async def _require(client: api.HaloClient, path: str, message: str) -> None:
    """Fail with not_found before a write that would otherwise fail with a misleading message."""
    try:
        await client.get(path)
    except api.ApiError as exc:
        if exc.code == "not_found":
            raise api.ApiError("not_found", message, False, 404) from exc
        raise


def _custom_field(cf: CustomField) -> dict[str, Any]:
    if cf.id is None and not (cf.name and cf.name.strip()):
        raise ToolInputError("Each custom field needs an id or a name.")
    out: dict[str, Any] = {"id": cf.id} if cf.id is not None else {"name": cf.name.strip()}
    out["value"] = cf.value
    return out


async def _team_fields(client: api.HaloClient, team_id: int) -> dict[str, Any]:
    """Halo tickets carry the team both as ``team_id`` and by name (``team``); send both so the assignment sticks."""
    try:
        team = api.first(await client.get(f"/Team/{seg(team_id)}"))
    except api.ApiError as exc:
        if exc.code == "not_found":
            raise ToolInputError(f"Team {team_id} not found. Use halopsa_teams_list to find the team ID.") from exc
        raise
    fields: dict[str, Any] = {"team_id": int(team_id)}
    if team.get("name"):
        fields["team"] = team["name"]
    return fields


async def _change_ticket_type(client: api.HaloClient, ticket_id: int, tickettype_id: int) -> None:
    """Halo changes a ticket's type through an action carrying ``new_tickettype``."""
    await client.post(
        "/Actions",
        [
            {
                "ticket_id": ticket_id,
                "new_tickettype": int(tickettype_id),
                "outcome": "Ticket Type Changed",
                "note": f"Ticket type changed to {tickettype_id}.",
                "hiddenfromuser": True,
            }
        ],
    )
