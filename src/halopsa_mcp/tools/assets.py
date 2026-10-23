# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Assets (configuration items) and asset types."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import INCLUDE_INACTIVE_DESC, READ, Limit25, Limit50, Limit100, ToolInputError, cap, listing, run, seg


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="halopsa_assets_list",
        description="List configuration items with optional filters",
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_assets_list(
        client_id: int | None = None,
        site_id: int | None = None,
        assettype_id: int | None = None,
        inactive: Annotated[bool | None, Field(description=INCLUDE_INACTIVE_DESC)] = None,
        limit: Limit50 = None,
    ) -> str:
        size = cap(limit, 50)

        async def handler(client: api.HaloClient):
            params = {
                "count": size + 1,
                "client_id": client_id,
                "site_id": site_id,
                "assettype_id": assettype_id,
                "includeinactive": True if inactive else None,
            }
            return listing(api.rows(await client.get("/Asset", params), "assets"), size)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_assets_get", description="Get asset details by ID", annotations=READ, structured_output=False
    )
    async def halopsa_assets_get(asset_id: int) -> str:
        async def handler(client: api.HaloClient):
            return api.first(await client.get(f"/Asset/{seg(asset_id)}", {"includedetails": True}))

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_assets_search",
        description="Search assets by inventory number and key fields",
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_assets_search(query: str, client_id: int | None = None, limit: Limit25 = None) -> str:
        size = cap(limit, 25)

        async def handler(client: api.HaloClient):
            if not query.strip():
                raise ToolInputError("query must not be empty.")
            params = {"count": size + 1, "search": query.strip(), "client_id": client_id}
            return listing(api.rows(await client.get("/Asset", params), "assets"), size)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_assets_list_types", description="List asset types", annotations=READ, structured_output=False
    )
    async def halopsa_assets_list_types(limit: Limit100 = None) -> str:
        size = cap(limit, 100)

        async def handler(client: api.HaloClient):
            return listing(api.rows(await client.get("/AssetType"), "assettypes"), size)

        return await run(settings, handler)
