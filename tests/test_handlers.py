# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Tool behaviour against a mocked HaloPSA API."""

import json
from urllib.parse import parse_qs

import httpx
import pytest

from conftest import API, TOKEN_URL

pytestmark = pytest.mark.usefixtures("creds")


@pytest.fixture(autouse=True)
def token_route(respx_mock):
    return respx_mock.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
    )


def sent(route):
    return json.loads(route.calls.last.request.content)


async def test_token_request_and_bearer(respx_mock, call, token_route):
    route = respx_mock.get(f"{API}/Client").mock(return_value=httpx.Response(200, json={"clients": [{"id": 1}]}))
    await call("halopsa_clients_list")
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form == {
        "grant_type": ["client_credentials"],
        "client_id": ["YOUR_CLIENT_ID"],
        "client_secret": ["YOUR_CLIENT_SECRET"],
        "scope": ["all"],
    }
    assert route.calls.last.request.headers["authorization"] == "Bearer test-token"


async def test_token_is_fetched_per_call(respx_mock, call, token_route):
    respx_mock.get(f"{API}/Team").mock(return_value=httpx.Response(200, json=[]))
    await call("halopsa_teams_list")
    await call("halopsa_teams_list")
    assert token_route.call_count == 2


async def test_bad_secret_is_unauthorized(call, token_route):
    token_route.mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    out = await call("halopsa_teams_list")
    assert out["error"]["code"] == "unauthorized" and "invalid_client" in out["error"]["message"]


async def test_missing_credentials_envelope(call):
    from halopsa_mcp import credentials

    token = credentials._current.set(None)
    try:
        out = await call("halopsa_clients_get", client_id=1)
    finally:
        credentials._current.reset(token)
    assert out["error"]["code"] == "not_configured"


async def test_placeholder_base_url_is_not_configured(call):
    from halopsa_mcp import credentials

    token = credentials._current.set(credentials.Credentials("a", "b", base_url="probe-placeholder"))
    try:
        out = await call("halopsa_clients_get", client_id=1)
    finally:
        credentials._current.reset(token)
    assert out["error"]["code"] == "not_configured"


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (400, "invalid_argument", False),
        (500, "upstream_error", True),
    ],
)
async def test_error_mapping_surfaces_body(respx_mock, call, status, code, retryable):
    respx_mock.get(f"{API}/Client/9").mock(
        return_value=httpx.Response(status, text="Halo says no", headers={"Retry-After": "0"})
    )
    out = await call("halopsa_clients_get", client_id=9)
    assert out["error"]["code"] == code
    assert out["error"]["retryable"] is retryable
    assert "Halo says no" in out["error"]["message"]


async def test_retries_rate_limit_then_succeeds(respx_mock, call):
    route = respx_mock.get(f"{API}/Team").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(200, json=[{"id": 1}])]
    )
    out = await call("halopsa_teams_list")
    assert out["count"] == 1 and route.call_count == 2


async def test_tickets_list_params_and_paging(respx_mock, call):
    route = respx_mock.get(f"{API}/Tickets").mock(
        return_value=httpx.Response(200, json={"record_count": 120, "tickets": [{"id": 5, "summary": "x"}]})
    )
    out = await call(
        "halopsa_tickets_list",
        client_id=3,
        halo_agent_id=7,
        open_only=True,
        dateoccurred_start="2026-04-06T00:00:00Z",
        limit=500,
        page_no=2,
    )
    p = route.calls.last.request.url.params
    assert p["agent_id"] == "7" and p["client_id"] == "3" and p["open_only"] == "true"
    assert p["page_size"] == "100" and p["page_no"] == "2" and p["pageinate"] == "true"
    assert p["datesearch"] == "dateoccurred" and p["startdate"] == "2026-04-06T00:00:00Z"
    assert out["total_count"] == 120 and out["has_more"] is True and out["page_no"] == 2


async def test_tickets_list_rejects_bad_date(call):
    out = await call("halopsa_tickets_list", dateoccurred_start="last tuesday")
    assert out["error"]["code"] == "invalid_argument"


async def test_tickets_get_collapses_expanded_records(respx_mock, call):
    respx_mock.get(f"{API}/Tickets/5").mock(
        return_value=httpx.Response(
            200,
            json={"id": 5, "tickettype_id": 1, "tickettype": {"id": 1, "name": "Incident", "huge": "x" * 1000}},
        )
    )
    out = await call("halopsa_tickets_get", ticket_id=5)
    assert out["tickettype"] == {"id": 1, "name": "Incident"}
    full = await call("halopsa_tickets_get", ticket_id=5, full_response=True)
    assert "huge" in full["tickettype"]


async def test_tickets_get_with_actions(respx_mock, call):
    respx_mock.get(f"{API}/Tickets/5").mock(return_value=httpx.Response(200, json={"id": 5}))
    actions = respx_mock.get(f"{API}/Actions").mock(
        return_value=httpx.Response(200, json={"actions": [{"id": 1, "note": "hi", "who_colour": "red"}]})
    )
    out = await call("halopsa_tickets_get", ticket_id=5, include_actions=True)
    assert actions.calls.last.request.url.params["ticket_id"] == "5"
    assert out["actions"] == [{"id": 1, "note": "hi"}]


async def test_tickets_create_maps_agent_and_team(respx_mock, call):
    respx_mock.get(f"{API}/Team/4").mock(return_value=httpx.Response(200, json={"id": 4, "name": "Service Desk"}))
    route = respx_mock.post(f"{API}/Tickets").mock(return_value=httpx.Response(201, json={"id": 9, "summary": "S"}))
    out = await call(
        "halopsa_tickets_create",
        summary="S",
        client_id=3,
        tickettype_id=1,
        halo_agent_id=7,
        team_id=4,
        category_1="Hardware>Laptop",
    )
    assert sent(route) == [
        {
            "summary": "S",
            "client_id": 3,
            "tickettype_id": 1,
            "agent_id": 7,
            "category_1": "Hardware>Laptop",
            "team_id": 4,
            "team": "Service Desk",
        }
    ]
    assert out["id"] == 9


async def test_tickets_update_team_and_custom_fields(respx_mock, call):
    respx_mock.get(f"{API}/Team/4").mock(return_value=httpx.Response(200, json={"id": 4, "name": "Escalations"}))
    route = respx_mock.post(f"{API}/Tickets").mock(return_value=httpx.Response(201, json={"id": 5, "team_id": 4}))
    out = await call(
        "halopsa_tickets_update",
        ticket_id=5,
        team_id=4,
        custom_fields=[{"id": 291, "value": True}, {"name": "CFNote", "value": None}],
    )
    assert sent(route) == [
        {
            "id": 5,
            "customfields": [{"id": 291, "value": True}, {"name": "CFNote", "value": None}],
            "team_id": 4,
            "team": "Escalations",
        }
    ]
    assert out["team_id"] == 4


async def test_tickets_update_unknown_team(respx_mock, call):
    respx_mock.get(f"{API}/Team/99").mock(return_value=httpx.Response(404))
    out = await call("halopsa_tickets_update", ticket_id=5, team_id=99)
    assert out["error"]["code"] == "invalid_argument"


async def test_tickets_update_custom_field_needs_id_or_name(call):
    out = await call("halopsa_tickets_update", ticket_id=5, custom_fields=[{"value": 1}])
    assert out["error"]["code"] == "invalid_argument"


async def test_tickets_update_needs_a_field(call):
    out = await call("halopsa_tickets_update", ticket_id=5)
    assert out["error"]["code"] == "invalid_argument"


async def test_tickets_update_type_goes_through_action_and_is_verified(respx_mock, call):
    action = respx_mock.post(f"{API}/Actions").mock(return_value=httpx.Response(201, json={"id": 1}))
    respx_mock.get(f"{API}/Tickets/5").mock(return_value=httpx.Response(200, json={"id": 5, "tickettype_id": 8}))
    out = await call("halopsa_tickets_update", ticket_id=5, tickettype_id=8)
    body = sent(action)[0]
    assert body["new_tickettype"] == 8 and body["hiddenfromuser"] is True and body["outcome"]
    assert out["tickettype_id"] == 8


async def test_tickets_update_type_that_does_not_stick_fails(respx_mock, call):
    respx_mock.post(f"{API}/Actions").mock(return_value=httpx.Response(201, json={"id": 1}))
    respx_mock.get(f"{API}/Tickets/5").mock(return_value=httpx.Response(200, json={"id": 5, "tickettype_id": 2}))
    out = await call("halopsa_tickets_update", ticket_id=5, tickettype_id=8)
    assert out["error"]["code"] == "upstream_error"


async def test_add_action_converts_minutes_to_hours(respx_mock, call):
    route = respx_mock.post(f"{API}/Actions").mock(return_value=httpx.Response(201, json={"id": 3, "ticket_id": 5}))
    await call("halopsa_tickets_add_action", ticket_id=5, note="Called user", timetaken=30, hidden_from_user=True)
    assert sent(route) == [
        {"ticket_id": 5, "note": "Called user", "outcome": "Note", "timetaken": 0.5, "hiddenfromuser": True}
    ]


async def test_clients_search_uses_count_and_has_more(respx_mock, call):
    route = respx_mock.get(f"{API}/Client").mock(
        return_value=httpx.Response(200, json={"record_count": 3, "clients": [{"id": i} for i in range(3)]})
    )
    out = await call("halopsa_clients_search", query="Example", limit=2)
    p = route.calls.last.request.url.params
    assert p["search"] == "Example" and p["count"] == "3"
    assert out["count"] == 2 and out["has_more"] is True


async def test_agents_list_accepts_bare_or_wrapped_rows(respx_mock, call):
    route = respx_mock.get(f"{API}/Agent").mock(return_value=httpx.Response(200, json=[{"id": 1}, {"id": 2}]))
    out = await call("halopsa_agents_list", team_id=4, inactive=True)
    p = route.calls.last.request.url.params
    assert p["section_id"] == "4" and p["includedisabled"] == "true"
    assert out["count"] == 2
    route.mock(return_value=httpx.Response(200, json={"agents": [{"id": 3}]}))
    assert (await call("halopsa_agents_list"))["items"] == [{"id": 3}]


async def test_invoices_local_filters(respx_mock, call):
    respx_mock.get(f"{API}/Invoice").mock(
        return_value=httpx.Response(
            200,
            json={
                "invoices": [
                    {"id": 1, "invoice_date": "2026-04-10T00:00:00", "datepaid": "2026-04-20T00:00:00"},
                    {"id": 2, "invoice_date": "2026-04-11T00:00:00", "datepaid": "1899-12-30T00:00:00"},
                    {"id": 3, "invoice_date": "2026-03-01T00:00:00", "datepaid": "1899-12-30T00:00:00"},
                ]
            },
        )
    )
    out = await call("halopsa_invoices_list", paid=False, invoice_date_start="2026-04-01")
    assert [i["id"] for i in out["items"]] == [2]
    assert "note" in out


async def test_invoices_status_maps_to_posted(respx_mock, call):
    route = respx_mock.get(f"{API}/Invoice").mock(return_value=httpx.Response(200, json={"invoices": []}))
    await call("halopsa_invoices_list", status="posted")
    assert route.calls.last.request.url.params["postedonly"] == "true"
    out = await call("halopsa_invoices_list", status="overdue")
    assert out["error"]["code"] == "invalid_argument"


async def test_lookups_projection_and_partial_failure(respx_mock, call):
    respx_mock.get(f"{API}/Status").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "New", "colour": "x"}, {"id": 2, "inactive": True}])
    )
    respx_mock.get(f"{API}/Priority").mock(
        return_value=httpx.Response(200, json=[{"id": 10, "priorityid": 1, "name": "P1"}])
    )
    respx_mock.get(f"{API}/TicketType").mock(
        return_value=httpx.Response(500, text="boom", headers={"Retry-After": "0"})
    )
    cats = respx_mock.get(f"{API}/Category").mock(
        return_value=httpx.Response(200, json=[{"id": 4, "value": "Hardware>Laptop", "type_id": 1}])
    )
    out = await call("halopsa_lookups_get", category_type_id=1)
    assert out["statuses"]["items"] == [{"id": 1, "name": "New"}]
    assert out["priorities"]["items"][0]["ticket_priority_id"] == 1
    assert out["ticket_types"]["error"]["code"] == "upstream_error"
    assert out["categories"]["items"] == [{"id": 4, "value": "Hardware>Laptop", "type_id": 1}]
    assert cats.calls.last.request.url.params["type_id"] == "1"


async def test_lookups_large_result_is_trimmed(respx_mock, call):
    respx_mock.get(f"{API}/Category").mock(
        return_value=httpx.Response(200, json=[{"id": i, "value": "x" * 200, "type_id": 1} for i in range(200)])
    )
    out = await call("halopsa_lookups_get", kinds=["categories"])
    assert out["categories"]["truncated"] is True and out["categories"]["has_more"] is True
    assert len(json.dumps(out)) <= 21_000


async def test_users_create_refuses_duplicate_email(respx_mock, call):
    search = respx_mock.get(f"{API}/Users").mock(
        return_value=httpx.Response(
            200, json={"users": [{"id": 8, "name": "Jane", "emailaddress": "JANE@example.com", "inactive": True}]}
        )
    )
    post = respx_mock.post(f"{API}/Users")
    out = await call("halopsa_users_create", name="Jane", email="jane@example.com", client_id=3)
    assert search.calls.last.request.url.params["includeinactive"] == "true"
    assert out["created"] is False and out["existing"]["id"] == 8
    assert not post.called


async def test_users_create_defaults_to_main_site(respx_mock, call):
    respx_mock.get(f"{API}/Users").mock(return_value=httpx.Response(200, json={"users": []}))
    respx_mock.get(f"{API}/Client/3").mock(return_value=httpx.Response(200, json={"id": 3, "main_site_id": 12}))
    post = respx_mock.post(f"{API}/Users").mock(return_value=httpx.Response(201, json={"id": 20, "name": "Jane"}))
    out = await call("halopsa_users_create", name="Jane", email="jane@example.com", client_id=3)
    assert sent(post) == [{"name": "Jane", "emailaddress": "jane@example.com", "client_id": 3, "site_id": 12}]
    assert out == {"created": True, "contact": {"id": 20, "name": "Jane"}}


async def test_users_create_rejects_bad_email(call):
    out = await call("halopsa_users_create", name="Jane", email="not-an-email", client_id=3)
    assert out["error"]["code"] == "invalid_argument"


async def test_users_update_partial(respx_mock, call):
    post = respx_mock.post(f"{API}/Users").mock(return_value=httpx.Response(201, json={"id": 8, "inactive": True}))
    out = await call("halopsa_users_update", contact_id=8, inactive=True)
    assert sent(post) == [{"id": 8, "inactive": True}]
    assert out["updated"] is True


async def test_sites_list(respx_mock, call):
    route = respx_mock.get(f"{API}/Site").mock(return_value=httpx.Response(200, json={"sites": [{"id": 1}]}))
    out = await call("halopsa_sites_list", client_id=3)
    assert route.calls.last.request.url.params["client_id"] == "3" and out["count"] == 1


async def test_navigate_lists_teams_under_agents(call):
    out = await call("halopsa_navigate", domain="agents")
    assert [t["name"] for t in out["tools"]] == ["halopsa_agents_list", "halopsa_agents_get", "halopsa_teams_list"]


async def test_status_reports_connectivity(respx_mock, call):
    respx_mock.get(f"{API}/TicketType").mock(return_value=httpx.Response(200, json=[]))
    out = await call("halopsa_status")
    assert out["configured"] is True and out["connected"] is True
    assert out["instance_url"] == "https://example.halopsa.com"
    assert "YOUR_CLIENT_SECRET" not in json.dumps(out)


async def test_large_results_are_truncated(respx_mock, call):
    rows = [{"id": i, "name": "x" * 500} for i in range(100)]
    respx_mock.get(f"{API}/Asset").mock(return_value=httpx.Response(200, json={"assets": rows}))
    out = await call("halopsa_assets_list", limit=100)
    assert out["truncated"] is True and out["has_more"] is True
    assert len(json.dumps(out)) <= 20_500
