# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Sites (client locations)."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import READ, Limit50, Offset, cap, fetch_page, run


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(name="halopsa_sites_list", description="List sites", annotations=READ, structured_output=False)
    async def halopsa_sites_list(
        client_id: Annotated[int | None, Field(description="Scope to one client's sites")] = None,
        limit: Limit50 = None,
        offset: Offset = None,
    ) -> str:
        size = cap(limit, 50)

        async def handler(client: api.HaloClient):
            return await fetch_page(client, "/Site", "sites", {"client_id": client_id}, size, offset)

        return await run(settings, handler)
