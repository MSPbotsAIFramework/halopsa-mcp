# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Cut list pages continue exactly by offset (PRD-21467)."""

import json
import re

import httpx
import pytest

from conftest import API, TOKEN_URL

pytestmark = pytest.mark.usefixtures("creds")

CAP = 20_000


@pytest.fixture(autouse=True)
def token_route(respx_mock):
    return respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))


def big(i):
    # ~2,000 characters of short fields: shortening long text can't make a page of 50 fit.
    return {"id": i, "name": f"record {i:04d}", **{f"field_{k}": f"value {k} " * 6 for k in range(30)}}


def paged_api(respx_mock, path, key, rows):
    """Fake Halo list endpoint paging by pageinate / page_size / page_no, like the real one."""

    def reply(request):
        params = request.url.params
        assert params["pageinate"] == "true"
        size, number = int(params["page_size"]), int(params["page_no"])
        return httpx.Response(200, json={"record_count": len(rows), key: rows[(number - 1) * size : number * size]})

    return respx_mock.get(url__regex=rf"{re.escape(API + path)}(\?.*)?$").mock(side_effect=reply)


def whole_api(respx_mock, path, key, rows):
    """Fake Halo endpoint that returns every row at once (/Agent, /Team, /AssetType)."""
    return respx_mock.get(url__regex=rf"{re.escape(API + path)}(\?.*)?$").mock(
        return_value=httpx.Response(200, json={key: rows})
    )


PAGED = [
    ("halopsa_tickets_list", "/Tickets", "tickets", {}),
    ("halopsa_clients_list", "/Client", "clients", {}),
    ("halopsa_clients_search", "/Client", "clients", {"query": "a"}),
    ("halopsa_users_search", "/Users", "users", {"query": "a"}),
    ("halopsa_assets_list", "/Asset", "assets", {}),
    ("halopsa_assets_search", "/Asset", "assets", {"query": "a"}),
    ("halopsa_invoices_list", "/Invoice", "invoices", {}),
    ("halopsa_sites_list", "/Site", "sites", {}),
]
WHOLE = [
    ("halopsa_agents_list", "/Agent", "agents"),
    ("halopsa_teams_list", "/Team", "teams"),
    ("halopsa_assets_list_types", "/AssetType", "assettypes"),
]


async def walk(call, tool, args):
    ids, calls, start = [], 0, {}
    while True:
        out = await call(tool, **args, **start)
        calls += 1
        assert len(json.dumps(out)) <= CAP + 500
        assert "retry_page_size" not in out and "preview" not in out
        ids += [r["id"] for r in out["items"]]
        if not out.get("has_more"):
            assert "next_offset" not in out
            return ids, calls
        start = {"offset": out["next_offset"]}
        assert calls < 200


@pytest.mark.parametrize(("tool", "path", "key", "args"), PAGED)
@pytest.mark.parametrize("limit", [None, 100])
async def test_cut_pages_walked_by_next_offset_return_every_record_once(respx_mock, call, tool, path, key, args, limit):
    rows = [big(i) for i in range(69)]
    paged_api(respx_mock, path, key, rows)
    ids, calls = await walk(call, tool, args | ({} if limit is None else {"limit": limit}))
    assert ids == list(range(69))
    assert calls > 2  # pages really were cut


@pytest.mark.parametrize(("tool", "path", "key"), WHOLE)
async def test_whole_lists_walked_by_next_offset_return_every_record_once(respx_mock, call, tool, path, key):
    rows = [big(i) for i in range(130)]
    whole_api(respx_mock, path, key, rows)
    ids, calls = await walk(call, tool, {})
    assert ids == list(range(130))
    assert calls > 2


async def test_offset_inside_a_page_skips_only_the_records_before_it(respx_mock, call):
    route = paged_api(respx_mock, "/Tickets", "tickets", [{"id": i} for i in range(120)])
    out = await call("halopsa_tickets_list", offset=57)
    p = route.calls.last.request.url.params
    assert p["page_size"] == "50" and p["page_no"] == "2"
    assert [r["id"] for r in out["items"]] == list(range(57, 100))
    assert out["offset"] == 57 and out["next_offset"] == 100 and out["total_count"] == 120


async def test_page_no_still_works(respx_mock, call):
    paged_api(respx_mock, "/Tickets", "tickets", [{"id": i} for i in range(120)])
    out = await call("halopsa_tickets_list", page_no=3)
    assert [r["id"] for r in out["items"]] == list(range(100, 120))
    assert out["has_more"] is False and "next_offset" not in out


async def test_invoice_local_filters_continue_after_the_last_match(respx_mock, call):
    paid = "2026-04-20T00:00:00"
    rows = [
        {"id": i, "invoice_date": "2026-04-10T00:00:00", "datepaid": paid if i % 3 else "1899-12-30T00:00:00"}
        for i in range(450)
    ]
    paged_api(respx_mock, "/Invoice", "invoices", rows)
    ids, _ = await walk(call, "halopsa_invoices_list", {"paid": True, "limit": 40})
    assert ids == [i for i in range(450) if i % 3]


async def test_lookups_table_continues_by_offset(respx_mock, call):
    rows = [{"id": i, "value": f"Cat>{i:03d}" + "x" * 150, "type_id": 1} for i in range(300)]
    respx_mock.get(f"{API}/Category").mock(return_value=httpx.Response(200, json=rows))
    ids, start = [], {}
    for _ in range(50):
        out = (await call("halopsa_lookups_get", kinds=["categories"], **start))["categories"]
        ids += [r["id"] for r in out["items"]]
        if not out["has_more"]:
            break
        start = {"offset": out["next_offset"]}
    assert ids == list(range(300))
