# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Agents (technicians) and teams.

Teams belong to the agents area: ``halopsa_navigate`` lists ``halopsa_teams_list`` under ``agents``.
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import HALO_AGENT_ID_DESC, INCLUDE_INACTIVE_DESC, READ, Limit50, Offset, cap, run, seg, slim, window


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(name="halopsa_agents_list", description="List technicians", annotations=READ, structured_output=False)
    async def halopsa_agents_list(
        team_id: Annotated[int | None, Field(description="Only agents in this team (halopsa_teams_list).")] = None,
        inactive: Annotated[bool | None, Field(description=INCLUDE_INACTIVE_DESC)] = None,
        limit: Limit50 = None,
        offset: Offset = None,
    ) -> str:
        size = cap(limit, 50)

        async def handler(client: api.HaloClient):
            # Halo calls teams "sections" on this endpoint. It returns every agent; paging is done here.
            params = {"section_id": team_id, "includedisabled": True if inactive else None}
            return window(api.rows(await client.get("/Agent", params), "agents"), size, offset)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_agents_get",
        description="Get technician details by HaloPSA agent ID",
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_agents_get(halo_agent_id: Annotated[int, Field(description=HALO_AGENT_ID_DESC)]) -> str:
        async def handler(client: api.HaloClient):
            return slim(api.first(await client.get(f"/Agent/{seg(halo_agent_id)}", {"includedetails": True})))

        return await run(settings, handler)

    @mcp.tool(name="halopsa_teams_list", description="List teams", annotations=READ, structured_output=False)
    async def halopsa_teams_list(limit: Limit50 = None, offset: Offset = None) -> str:
        size = cap(limit, 50)

        async def handler(client: api.HaloClient):
            return window(api.rows(await client.get("/Team"), "teams"), size, offset)

        return await run(settings, handler)
