# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Invoices.

The Halo invoice list filters by client and posted state on the server. ``sent``, ``paid`` and the
invoice date range are applied to the page Halo returns, which is noted in the result.
"""

from datetime import date
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import api
from ..config import Settings
from ._common import READ, Limit50, ToolInputError, cap, listing, run, seg

# Halo writes "no date" as 1899-12-30 / 1900-01-01.
NO_DATE_BEFORE = "1901-01-01"
POSTED = {"posted": True, "notposted": False, "not_posted": False, "unposted": False, "draft": False}
SCAN_PAGE = 200


def _date(name: str, value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10]).isoformat()
    except ValueError as exc:
        raise ToolInputError(f"{name} must be a date in YYYY-MM-DD format.") from exc


def _real_date(value: Any) -> bool:
    return isinstance(value, str) and value[:10] >= NO_DATE_BEFORE


def _is_paid(inv: dict[str, Any]) -> bool:
    if _real_date(inv.get("datepaid")):
        return True
    due, paid = inv.get("amountdue"), inv.get("amountpaid")
    return isinstance(due, int | float) and isinstance(paid, int | float) and due <= 0 and paid > 0


def _is_sent(inv: dict[str, Any]) -> bool:
    return _real_date(inv.get("datesent")) or bool(inv.get("emailstatus"))


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="halopsa_invoices_list",
        description="List invoices with optional filters by client, status, or date range",
        annotations=READ,
        structured_output=False,
    )
    async def halopsa_invoices_list(
        client_id: int | None = None,
        status: Annotated[
            str | None, Field(description="Invoice state: 'posted' or 'notposted'. Other values are rejected.")
        ] = None,
        sent: Annotated[
            bool | None, Field(description="Only invoices that were (true) or were not (false) sent.")
        ] = None,
        paid: Annotated[
            bool | None, Field(description="Only invoices that are (true) or are not (false) paid.")
        ] = None,
        invoice_date_start: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
        invoice_date_end: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
        limit: Limit50 = None,
    ) -> str:
        size = cap(limit, 50)

        async def handler(client: api.HaloClient):
            start = _date("invoice_date_start", invoice_date_start)
            end = _date("invoice_date_end", invoice_date_end)
            params: dict[str, Any] = {"client_id": client_id, "orderby": "invoice_date", "orderdesc": True}
            if status and status.strip():
                key = status.strip().lower().replace(" ", "")
                if key not in POSTED:
                    raise ToolInputError("status must be 'posted' or 'notposted'.")
                params["postedonly" if POSTED[key] else "notpostedonly"] = True
            local = sent is not None or paid is not None or start or end
            params["count"] = SCAN_PAGE if local else size + 1
            items = api.rows(await client.get("/Invoice", params), "invoices")
            if local:
                scanned = len(items)
                items = [
                    i
                    for i in items
                    if (sent is None or _is_sent(i) == sent)
                    and (paid is None or _is_paid(i) == paid)
                    and (not start or str(i.get("invoice_date") or "")[:10] >= start)
                    and (not end or str(i.get("invoice_date") or "")[:10] <= end)
                ]
                result = listing(items, size)
                if scanned >= SCAN_PAGE:
                    result["has_more"] = True
                result["note"] = (
                    f"sent, paid and date filters were applied to the latest {scanned} invoices HaloPSA returned."
                )
                return result
            return listing(items, size)

        return await run(settings, handler)

    @mcp.tool(
        name="halopsa_invoices_get", description="Get invoice details by ID", annotations=READ, structured_output=False
    )
    async def halopsa_invoices_get(invoice_id: int) -> str:
        async def handler(client: api.HaloClient):
            return api.first(await client.get(f"/Invoice/{seg(invoice_id)}", {"includedetails": True}))

        return await run(settings, handler)
