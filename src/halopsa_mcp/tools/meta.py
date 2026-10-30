# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Discovery and diagnostics: halopsa_navigate and halopsa_status.

All tools are always listed and callable; navigate only describes the tools of one area and keeps no state.
"""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import _json, api
from ..config import BASE_URL_HEADER, CLIENT_ID_HEADER, CLIENT_SECRET_HEADER, TENANT_HEADER, Settings
from ..credentials import CredentialError, current, resolve_endpoints
from ._common import LOCAL, READ

DOMAINS: dict[str, tuple[str, tuple[str, ...]]] = {
    "tickets": (
        "Ticket management - list, get, create, update tickets, add notes and attach files",
        (
            "halopsa_tickets_list",
            "halopsa_tickets_get",
            "halopsa_tickets_create",
            "halopsa_tickets_update",
            "halopsa_tickets_add_action",
            "halopsa_tickets_add_attachment",
            "halopsa_tickets_list_actions",
        ),
    ),
    "clients": (
        "Client/company management - list and get client information and relationships",
        ("halopsa_clients_list", "halopsa_clients_get", "halopsa_clients_create", "halopsa_clients_search"),
    ),
    "assets": (
        "Asset management - list and get hardware/software assets, configurations",
        ("halopsa_assets_list", "halopsa_assets_get", "halopsa_assets_search", "halopsa_assets_list_types"),
    ),
    "agents": (
        "Agent management - list and get support staff and technician information, and teams",
        ("halopsa_agents_list", "halopsa_agents_get", "halopsa_teams_list"),
    ),
    "invoices": (
        "Invoice management - list and get billing and invoice information",
        ("halopsa_invoices_list", "halopsa_invoices_get"),
    ),
    "lookups": (
        "Reference data - read the tenant's ticket statuses, priorities, ticket types, Category 1-4 values and "
        "SLA details (including an SLA's priority list), so ids and category strings are resolved live instead "
        "of hardcoded",
        ("halopsa_lookups_get", "halopsa_sla_get"),
    ),
    "users": (
        "Contact management - search, get, create (with duplicate-prevention by email) and update "
        "(partial, including activate/deactivate) contacts",
        ("halopsa_users_search", "halopsa_users_get", "halopsa_users_create", "halopsa_users_update"),
    ),
    "sites": ("Site management - list sites, optionally scoped to one client", ("halopsa_sites_list",)),
}

Domain = Literal["tickets", "clients", "assets", "agents", "invoices", "lookups", "users", "sites"]
DOMAIN_DESC = "The domain to explore:\n" + "\n".join(f"- {name}: {desc}" for name, (desc, _) in DOMAINS.items())


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="halopsa_navigate",
        description=(
            "Discover available HaloPSA tools by domain. Returns tool names and descriptions for the selected "
            "domain. All tools are callable at any time; this is a help/discovery aid, not a prerequisite."
        ),
        annotations=LOCAL,
        structured_output=False,
    )
    async def halopsa_navigate(domain: Annotated[Domain, Field(description=DOMAIN_DESC)]) -> str:
        if domain not in DOMAINS:
            return _json.error("invalid_argument", f"Unknown domain. Use one of: {', '.join(DOMAINS)}.")
        description, names = DOMAINS[domain]
        tools = {t.name: t for t in await mcp.list_tools()}
        return _json.dump(
            {
                "domain": domain,
                "description": description,
                "tools": [
                    {"name": n, "description": tools[n].description, "parameters": tools[n].inputSchema}
                    for n in names
                    if n in tools
                ],
            }
        )

    @mcp.tool(
        name="halopsa_status",
        description=(
            "Show credentials status and available domains: which HaloPSA headers were sent, the instance URL in "
            "use, and whether a token could be obtained."
        ),
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_status() -> str:
        creds = current()
        out: dict = {
            "headers": {
                CLIENT_ID_HEADER: bool(creds and creds.client_id),
                CLIENT_SECRET_HEADER: bool(creds and creds.client_secret),
                TENANT_HEADER: bool(creds and creds.tenant),
                BASE_URL_HEADER: bool(creds and creds.base_url),
            },
            "domains": list(DOMAINS),
        }
        if creds is None:
            out.update(configured=False, connected=False, message="No HaloPSA credentials were sent.")
            return _json.dump(out)
        try:
            endpoints = resolve_endpoints(creds)
        except CredentialError as exc:
            out.update(configured=False, connected=False, message=str(exc))
            return _json.dump(out)
        out.update(configured=True, instance_url=endpoints.root)
        try:
            async with api.HaloClient(creds, settings) as client:
                await client.token()
                await client.get("/TicketType", {"count": 1})
        except api.ApiError as exc:
            out.update(connected=False, error={"code": exc.code, "message": exc.message, "retryable": exc.retryable})
            return _json.dump(out)
        except Exception:  # noqa: BLE001 - tools must never raise
            out.update(
                connected=False, error={"code": "upstream_error", "message": "Unexpected error.", "retryable": True}
            )
            return _json.dump(out)
        out.update(connected=True, message="HaloPSA accepted the credentials and the API answered.")
        return _json.dump(out)
