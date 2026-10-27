# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""FastMCP server and HTTP app."""

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from ._arguments import EnvelopeFastMCP
from .config import Settings
from .credentials import CredentialMiddleware
from .tools import agents, assets, clients, invoices, lookups, meta, sites, tickets, users

INSTRUCTIONS = (
    "HaloPSA is the PSA (ticketing, CRM and billing) system the MSP runs its service desk in. "
    "Clients are the MSP's customer companies; sites are their locations; users are their contacts; "
    "agents are the MSP's technicians, grouped into teams. Start from an ID: find a client with "
    "halopsa_clients_search, an agent with halopsa_agents_list, a team with halopsa_teams_list. "
    "Before creating or updating a ticket, resolve ticket type, status, priority and category values with "
    "halopsa_lookups_get instead of guessing them. To reassign a ticket use halopsa_tickets_update with "
    "halo_agent_id and/or team_id; to log work or a note use halopsa_tickets_add_action; "
    "to attach a file or report use halopsa_tickets_add_attachment. "
    "halopsa_navigate describes the tools of one area; halopsa_status checks the connection. "
    "Ask the user before creating or changing records."
)


def create_mcp(settings: Settings) -> EnvelopeFastMCP:
    mcp = EnvelopeFastMCP(
        name="halopsa-mcp",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        # The gateway forwards requests with its own Host header; DNS-rebinding
        # protection would reject them with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for module in (meta, tickets, clients, assets, agents, invoices, lookups, users, sites):
        module.register(mcp, settings)
    return mcp


def create_app(settings: Settings) -> Starlette:
    mcp = create_mcp(settings)
    mcp_app = mcp.streamable_http_app()

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Mount() does not run a sub-app's lifespan; without forwarding it the
    # session manager never starts and /mcp fails while /health still passes.
    return Starlette(
        routes=[Route("/health", health), Mount("/", app=CredentialMiddleware(mcp_app))],
        lifespan=lambda app: mcp_app.router.lifespan_context(app),
    )
