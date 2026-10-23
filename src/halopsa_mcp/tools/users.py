# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Users (contacts at client companies). Halo calls contacts "Users"."""

import re
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import CREATE, READ, UPDATE, Limit50, ToolInputError, cap, listing, run, seg

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTACT_FIELDS = (
    "id",
    "name",
    "emailaddress",
    "phonenumber",
    "client_id",
    "client_name",
    "site_id",
    "site_name",
    "inactive",
)


def _email(value: str) -> str:
    text = value.strip()
    if not EMAIL_RE.match(text):
        raise ToolInputError(f"{value!r} is not a valid email address.")
    return text


def _contact(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: raw[k] for k in CONTACT_FIELDS if k in raw}


async def _find_by_email(client: api.HaloClient, email: str) -> dict[str, Any] | None:
    """Exact (case-insensitive) email match across active and inactive contacts."""
    params = {"search": email, "includeactive": True, "includeinactive": True, "count": 50}
    for row in api.rows(await client.get("/Users", params), "users"):
        for key in ("emailaddress", "email"):
            if str(row.get(key) or "").strip().lower() == email.lower():
                return row
    return None


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="halopsa_users_search",
        description="Search contacts by name or email",
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_users_search(
        query: str,
        limit: Limit50 = None,
        client_id: Annotated[int | None, Field(description="Only contacts of this client.")] = None,
        include_inactive: Annotated[bool | None, Field(description="Include inactive contacts.")] = None,
    ) -> str:
        size = cap(limit, 50)

        async def handler(client: api.HaloClient):
            if not query.strip():
                raise ToolInputError("query must not be empty.")
            params = {
                "search": query.strip(),
                "client_id": client_id,
                "includeinactive": True if include_inactive else None,
                "count": size + 1,
            }
            return listing(api.rows(await client.get("/Users", params), "users"), size)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_users_get", description="Get contact details by ID", annotations=READ, structured_output=False
    )
    async def halopsa_users_get(contact_id: int) -> str:
        async def handler(client: api.HaloClient):
            return api.first(await client.get(f"/Users/{seg(contact_id)}", {"includedetails": True}))

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_users_create",
        description="Create a contact; refuses and reports the existing record if the email is already in use",
        annotations=CREATE,
        structured_output=False,
    )
    async def halopsa_users_create(
        name: str,
        email: str,
        client_id: Annotated[
            int,
            Field(
                description="HaloPSA client (company) this contact belongs to. Required by HaloPSA's Contact entity."
            ),
        ],
        site_id: Annotated[
            int | None,
            Field(description="HaloPSA site this contact belongs to; defaults to the client's main site when omitted"),
        ] = None,
        phonenumber: str | None = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            if not name.strip():
                raise ToolInputError("name must not be empty.")
            address = _email(email)
            existing = await _find_by_email(client, address)
            if existing:
                return {
                    "created": False,
                    "duplicate": True,
                    "message": f"A contact with email {address} already exists (id {existing.get('id')}).",
                    "existing": _contact(existing),
                }
            site = site_id
            if site is None:
                company = api.first(await client.get(f"/Client/{seg(client_id)}"))
                site = company.get("main_site_id")
                if not site:
                    raise ToolInputError(f"Client {client_id} has no main site; pass site_id.")
            body = {
                "name": name.strip(),
                "emailaddress": address,
                "client_id": int(client_id),
                "site_id": int(seg(site)),
                "phonenumber": phonenumber,
            }
            saved = api.first(await client.post("/Users", [{k: v for k, v in body.items() if v is not None}]))
            return {"created": True, "contact": _contact(saved)}

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_users_update",
        description="Update only the fields provided; set inactive to deactivate or reactivate a contact",
        annotations=UPDATE,
        structured_output=False,
    )
    async def halopsa_users_update(
        contact_id: int,
        name: str | None = None,
        email: str | None = None,
        phonenumber: str | None = None,
        inactive: Annotated[bool | None, Field(description="true deactivates, false reactivates")] = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            body: dict[str, Any] = {"id": int(seg(contact_id))}
            if name is not None:
                if not name.strip():
                    raise ToolInputError("name must not be empty.")
                body["name"] = name.strip()
            if email is not None:
                body["emailaddress"] = _email(email)
            if phonenumber is not None:
                body["phonenumber"] = phonenumber
            if inactive is not None:
                body["inactive"] = inactive
            if len(body) == 1:
                raise ToolInputError("Nothing to update: pass at least one field to change.")
            saved = api.first(await client.post("/Users", [body]))
            return {"updated": True, "contact": _contact(saved) or {"id": body["id"]}}

        return await run(settings, handler)
