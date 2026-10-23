# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Clients (the MSP's customer companies)."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import CREATE, INCLUDE_INACTIVE_DESC, READ, Limit25, Limit50, ToolInputError, cap, listing, run, seg


def register(mcp: FastMCP, settings: Settings) -> None:
    async def _list(client: api.HaloClient, size: int, search: str | None, inactive: bool | None) -> dict:
        params = {"count": size + 1, "search": search, "includeinactive": True if inactive else None}
        payload = await client.get("/Client", params)
        return listing(api.rows(payload, "clients"), size)

    @mcp.tool(name="halopsa_clients_list", description="List companies", annotations=READ, structured_output=False)
    async def halopsa_clients_list(
        search: Annotated[str | None, Field(description="Text to match in the company name.")] = None,
        inactive: Annotated[bool | None, Field(description=INCLUDE_INACTIVE_DESC)] = None,
        limit: Limit50 = None,
    ) -> str:
        size = cap(limit, 50)
        return await run(settings, lambda client: _list(client, size, search, inactive))

    @mcp.tool(
        name="halopsa_clients_get", description="Get company details by ID", annotations=READ, structured_output=False
    )
    async def halopsa_clients_get(client_id: int) -> str:
        async def handler(client: api.HaloClient):
            return api.first(await client.get(f"/Client/{seg(client_id)}", {"includedetails": True}))

        return await run(settings, handler)

    @mcp.tool(name="halopsa_clients_create", description="Create company", annotations=CREATE, structured_output=False)
    async def halopsa_clients_create(
        name: str,
        website: str | None = None,
        phonenumber: str | None = None,
        email: str | None = None,
        notes: str | None = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            if not name.strip():
                raise ToolInputError("name must not be empty.")
            body = {
                "name": name.strip(),
                "website": website,
                "phonenumber": phonenumber,
                "email": email,
                "notes": notes,
            }
            saved = api.first(await client.post("/Client", [{k: v for k, v in body.items() if v is not None}]))
            return {
                k: saved.get(k) for k in ("id", "name", "website", "phonenumber", "email", "main_site_id") if k in saved
            }

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_clients_search", description="Search companies by name", annotations=READ, structured_output=False
    )
    async def halopsa_clients_search(query: str, limit: Limit25 = None) -> str:
        size = cap(limit, 25)

        async def handler(client: api.HaloClient):
            if not query.strip():
                raise ToolInputError("query must not be empty.")
            return await _list(client, size, query.strip(), None)

        return await run(settings, handler)
