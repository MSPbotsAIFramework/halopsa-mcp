# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Users (contacts at client companies). Halo calls contacts "Users"."""

import re
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import (
    CREATE,
    READ,
    UPDATE,
    Limit50,
    Offset,
    ToolInputError,
    cap,
    fetch_page,
    phone_fields,
    run,
    seg,
    slim,
    with_phones,
)

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
# What halopsa_users_get returns by default; Halo's contact has about 380 fields.
CONTACT_DETAIL_FIELDS = (
    "id",
    "name",
    "firstname",
    "surname",
    "title",
    "jobtitle",
    "department",
    "emailaddress",
    "email2",
    "email3",
    "phonenumber",
    "phonenumber_preferred",
    "mobilenumber",
    "mobilenumber2",
    "client_id",
    "client_name",
    "site_id",
    "site_name",
    "inactive",
    "isimportantcontact",
    "linked_agent_id",
    "notes",
    "customfields",
)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _same_number(a: str, b: str) -> bool:
    """Same phone number whatever the formatting: equal digits, or equal last ten digits (country code optional)."""
    da, db = _digits(a), _digits(b)
    if len(da) < 7 or len(db) < 7:
        return False
    return da == db or (len(da) >= 10 and len(db) >= 10 and da[-10:] == db[-10:])


def _holds(record: dict[str, Any], digits: str) -> bool:
    return any(_same_number(value, digits) for value in phone_fields(record).values())


def _email(value: str) -> str:
    text = value.strip()
    if not EMAIL_RE.match(text):
        raise ToolInputError(f"{value!r} is not a valid email address.")
    return text


def _phones_of(row: dict[str, Any]) -> dict[str, Any]:
    return with_phones(row, {}) if phone_fields(row) else {}


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
        description=(
            "Search contacts by name, email or phone number; omit query to list every contact "
            "(paged, active and inactive with include_inactive)."
        ),
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_users_search(
        query: Annotated[
            str | None, Field(description="Text to match in the contact's name or email. Omit to list all.")
        ] = None,
        search_phonenumbers: Annotated[
            bool | None, Field(description="Match query against the contact's phone fields instead of name/email.")
        ] = None,
        limit: Limit50 = None,
        client_id: Annotated[int | None, Field(description="Only contacts of this client.")] = None,
        include_inactive: Annotated[bool | None, Field(description="Include inactive contacts.")] = None,
        include_details: Annotated[
            bool | None,
            Field(description="Ask HaloPSA for full contact records, so every phone field (home, fax) is present."),
        ] = None,
        offset: Offset = None,
    ) -> str:
        size = cap(limit, 50)

        async def handler(client: api.HaloClient):
            text = (query or "").strip()
            if search_phonenumbers and not text:
                raise ToolInputError("query must not be empty when search_phonenumbers is set.")
            params = {
                "search": text or None,
                "search_phonenumbers": True if search_phonenumbers else None,
                "client_id": client_id,
                "includeinactive": True if include_inactive else None,
                "includedetails": True if include_details else None,
            }
            page = await fetch_page(client, "/Users", "users", params, size, offset)
            # PRD-22078: the detail field set (CONTACT_DETAIL_FIELDS), not the narrower CONTACT_FIELDS,
            # plus phone_fields read from the raw row: slim() keeps only the detail set, which has no
            # home or fax number, and contact sync needs every number a contact has.
            page["items"] = [with_phones(row, slim(row, CONTACT_DETAIL_FIELDS)) for row in page["items"]]
            return page

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_phone_search",
        description=(
            "Find who owns a phone number: contacts (any phone field), and the clients and sites whose own phone "
            "matches. At most 3 HaloPSA requests; active and inactive records."
        ),
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_phone_search(
        phone: Annotated[str, Field(description="Phone number in any format; only the digits are used.")],
    ) -> str:
        async def handler(client: api.HaloClient):
            digits = _digits(phone)
            if len(digits) < 7:
                raise ToolInputError("phone must hold at least 7 digits.")
            params = {"search": digits, "includeinactive": True, "includedetails": True, "count": 10}
            found = api.rows(await client.get("/Users", {**params, "search_phonenumbers": True}), "users")
            contacts = [with_phones(row, slim(row, CONTACT_DETAIL_FIELDS)) for row in found if _holds(row, digits)]
            clients: list[dict[str, Any]] = []
            # A single contact is a final answer; otherwise the number may belong to a client or a site.
            if len(contacts) != 1:
                for row in api.rows(
                    await client.get("/Client", {"search": digits, "includeinactive": True}), "clients"
                ):
                    if _holds(row, digits):
                        clients.append(
                            {"id": row.get("id"), "name": row.get("name"), "matched": "main", **_phones_of(row)}
                        )
                for row in api.rows(await client.get("/Site", {"search": digits, "includeinactive": True}), "sites"):
                    if _holds(row, digits) and row.get("client_id") is not None:
                        clients.append(
                            {
                                "id": row.get("client_id"),
                                "name": row.get("client_name"),
                                "matched": "site",
                                "site_name": row.get("name"),
                                **_phones_of(row),
                            }
                        )
            return {"contacts": contacts, "clients": clients}

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_users_get", description="Get contact details by ID", annotations=READ, structured_output=False
    )
    async def halopsa_users_get(
        contact_id: int,
        full_response: Annotated[
            bool | None, Field(description="Return the contact exactly as HaloPSA sends it (very large).")
        ] = None,
    ) -> str:
        async def handler(client: api.HaloClient):
            record = api.first(await client.get(f"/Users/{seg(contact_id)}", {"includedetails": True}))
            return record if full_response else with_phones(record, slim(record, CONTACT_DETAIL_FIELDS))

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
            # Halo treats an update of a missing contact as a create and fails with "A Site must be selected".
            try:
                await client.get(f"/Users/{body['id']}")
            except api.ApiError as exc:
                if exc.code == "not_found":
                    raise api.ApiError("not_found", f"No contact {contact_id} in HaloPSA.", False, 404) from exc
                raise
            saved = api.first(await client.post("/Users", [body]))
            return {"updated": True, "contact": _contact(saved) or {"id": body["id"]}}

        return await run(settings, handler)
