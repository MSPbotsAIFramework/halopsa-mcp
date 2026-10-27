# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Clients (the MSP's customer companies)."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import (
    CREATE,
    INCLUDE_INACTIVE_DESC,
    READ,
    Limit25,
    Limit50,
    Offset,
    ToolInputError,
    cap,
    fetch_page,
    run,
    seg,
    slim,
)

CREATED_FIELDS = (
    "id",
    "name",
    "website",
    "notes",
    "main_site_id",
    "main_phonenumber",
    "main_contact_id",
    "main_contact_name",
    "main_contact_email",
)
DEFAULT_CONTACT_NAME = "Main Contact"


def register(mcp: FastMCP, settings: Settings) -> None:
    async def _list(
        client: api.HaloClient, size: int, offset: int | None, search: str | None, inactive: bool | None
    ) -> dict:
        params = {"search": search, "includeinactive": True if inactive else None}
        return await fetch_page(client, "/Client", "clients", params, size, offset)

    @mcp.tool(name="halopsa_clients_list", description="List companies", annotations=READ, structured_output=False)
    async def halopsa_clients_list(
        search: Annotated[str | None, Field(description="Text to match in the company name.")] = None,
        inactive: Annotated[bool | None, Field(description=INCLUDE_INACTIVE_DESC)] = None,
        limit: Limit50 = None,
        offset: Offset = None,
    ) -> str:
        size = cap(limit, 50)
        return await run(settings, lambda client: _list(client, size, offset, search, inactive))

    @mcp.tool(
        name="halopsa_clients_get", description="Get company details by ID", annotations=READ, structured_output=False
    )
    async def halopsa_clients_get(client_id: int) -> str:
        async def handler(client: api.HaloClient):
            return slim(api.first(await client.get(f"/Client/{seg(client_id)}", {"includedetails": True})))

        return await run(settings, handler)

    @mcp.tool(name="halopsa_clients_create", description="Create company", annotations=CREATE, structured_output=False)
    async def halopsa_clients_create(
        name: str,
        website: str | None = None,
        phonenumber: Annotated[
            str | None, Field(description="Main phone number; HaloPSA keeps it on the client's main site.")
        ] = None,
        email: Annotated[
            str | None,
            Field(description="Email of the client's main contact; HaloPSA has no company-level email."),
        ] = None,
        notes: str | None = None,
        contact_name: Annotated[
            str | None,
            Field(description=f'Name of the main contact that holds email (default "{DEFAULT_CONTACT_NAME}").'),
        ] = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            if not name.strip():
                raise ToolInputError("name must not be empty.")
            contact = (contact_name or "").strip() or DEFAULT_CONTACT_NAME
            # Halo has no phonenumber / email on a client: on create they go to the main site and the
            # main contact Halo creates with it. Unknown fields are ignored without an error, and Halo
            # creates no main contact from an email without a contact name.
            body: dict[str, Any] = {
                "name": name.strip(),
                "website": website,
                "notes": notes,
                "newclient_phonenumber": phonenumber,
                "newclient_contactemail": email,
            }
            if email is not None:
                body["newclient_contactname"] = contact
                body["newclient_sendwelcomeemail"] = False
            saved = api.first(await client.post("/Client", [{k: v for k, v in body.items() if v is not None}]))
            client_id = saved.get("id")

            async def reread(current: dict[str, Any]) -> dict[str, Any]:
                return api.first(await client.get(f"/Client/{seg(client_id)}", {"includedetails": True})) or current

            if (phonenumber or email) and client_id is not None:
                saved = await reread(saved)
            if email and client_id is not None and not saved.get("main_contact_email") and saved.get("main_site_id"):
                # Halo did not create the main contact: add it as a contact of the main site.
                await client.post(
                    "/Users",
                    [
                        {
                            "name": contact,
                            "emailaddress": email,
                            "client_id": int(client_id),
                            "site_id": int(seg(saved["main_site_id"])),
                            "ismaincontact": True,
                        }
                    ],
                )
                saved = await reread(saved)
            result: dict[str, Any] = {k: saved[k] for k in CREATED_FIELDS if saved.get(k) not in (None, "")}
            stored = (("phonenumber", phonenumber, "main_phonenumber"), ("email", email, "main_contact_email"))
            missing = [label for label, value, key in stored if value and not saved.get(key)]
            if missing:
                result["warning"] = (
                    f"The client was created, but HaloPSA did not save {' and '.join(missing)}. "
                    "Set them on the client's main site or main contact."
                )
            return result

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_clients_search", description="Search companies by name", annotations=READ, structured_output=False
    )
    async def halopsa_clients_search(query: str, limit: Limit25 = None, offset: Offset = None) -> str:
        size = cap(limit, 25)

        async def handler(client: api.HaloClient):
            if not query.strip():
                raise ToolInputError("query must not be empty.")
            return await _list(client, size, offset, query.strip(), None)

        return await run(settings, handler)
