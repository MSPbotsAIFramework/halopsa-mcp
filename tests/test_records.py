# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Large records come back as compact JSON objects (PRD-21468); write fixes from PRD-21469."""

import json

import httpx
import pytest

from conftest import API, TOKEN_URL

pytestmark = pytest.mark.usefixtures("creds")

CAP = 20_000


@pytest.fixture(autouse=True)
def token_route(respx_mock):
    return respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))


def custom_field(i, value=None):
    # Halo sends each custom field with its whole definition, set or not.
    return {
        "id": 200 + i,
        "name": f"CF{i}",
        "label": f"Field {i}",
        "value": value,
        "display": value,
        **{f"setting_{k}": f"definition {k}" for k in range(65)},
    }


def halo_ticket(ticket_id):
    """A ticket shaped like Halo's: ~1,000 fields and every custom field definition, ~70,000 characters."""
    ticket = {f"setting_{k}": "" if k % 2 else 0 for k in range(900)}
    ticket.update(
        {
            "id": ticket_id,
            "summary": "Printer offline",
            "details": "It stopped printing.",
            "status_id": 1,
            "status_name": "New",
            "tickettype_id": 1,
            "tickettype_name": "Incident",
            "priority_id": 3,
            "client_id": 17,
            "client_name": "Example Co",
            "site_id": 60,
            "site_name": "Main",
            "agent_id": 4,
            "agent_name": "Jane Tech",
            "team_id": 2,
            "team": "Service Desk",
            "category_1": "Hardware>Printer",
            "dateclosed": "1900-01-01T00:00:00",
            "deadlinedate": "2026-11-01T00:00:00",
            "tickettype": {"id": 1, "name": "Incident", **{f"t{k}": "x" * 40 for k in range(250)}},
            "customfields": [custom_field(i, "yes" if i == 3 else None) for i in range(40)],
            "audit_log": [{"id": k, "text": "x" * 100} for k in range(50)],
        }
    )
    return ticket


def halo_contact():
    contact = {f"setting_{k}": "x" * 40 for k in range(380)}
    contact.update(
        {
            "id": 149,
            "name": "QA Contact",
            "emailaddress": "qa@example.com",
            "client_id": 40,
            "site_id": 60,
            "inactive": False,
            "customfields": [custom_field(i) for i in range(20)],
        }
    )
    return contact


async def test_tickets_get_returns_a_compact_ticket(respx_mock, call):
    raw = halo_ticket(3309)
    assert len(json.dumps(raw)) > 60_000
    respx_mock.get(f"{API}/Tickets/3309").mock(return_value=httpx.Response(200, json=raw))
    out = await call("halopsa_tickets_get", ticket_id=3309)
    assert len(json.dumps(out)) <= CAP and "preview" not in out and "truncated" not in out
    for key in ("id", "summary", "status_name", "priority_id", "tickettype_name", "client_name", "agent_name", "team"):
        assert out[key] == raw[key], key
    assert out["tickettype"] == {"id": 1, "name": "Incident"}
    assert out["customfields"] == [{"id": 203, "name": "CF3", "label": "Field 3", "value": "yes", "display": "yes"}]
    assert "dateclosed" not in out and "audit_log" not in out and "setting_1" not in out


async def test_tickets_get_full_response_never_returns_a_bare_preview(respx_mock, call):
    respx_mock.get(f"{API}/Tickets/3309").mock(return_value=httpx.Response(200, json=halo_ticket(3309)))
    out = await call("halopsa_tickets_get", ticket_id=3309, full_response=True)
    assert len(json.dumps(out)) <= CAP + 500 and "preview" not in out


async def test_tickets_get_pages_actions(respx_mock, call):
    respx_mock.get(f"{API}/Tickets/5").mock(return_value=httpx.Response(200, json={"id": 5}))
    actions = respx_mock.get(f"{API}/Actions").mock(
        return_value=httpx.Response(200, json={"actions": [{"id": i, "note": f"n{i}"} for i in range(45)]})
    )
    out = await call("halopsa_tickets_get", ticket_id=5, include_actions=True)
    assert [a["id"] for a in out["actions"]] == list(range(20)) and out["next_actions_offset"] == 20
    out = await call("halopsa_tickets_get", ticket_id=5, actions_offset=40)
    assert actions.calls.last.request.url.params["count"] == "61"
    assert [a["id"] for a in out["actions"]] == list(range(40, 45)) and "next_actions_offset" not in out


async def test_tickets_update_returns_the_compact_ticket(respx_mock, call):
    respx_mock.post(f"{API}/Tickets").mock(return_value=httpx.Response(201, json=halo_ticket(3310)))
    out = await call("halopsa_tickets_update", ticket_id=3310, summary="x")
    assert out["id"] == 3310 and out["status_name"] == "New" and len(json.dumps(out)) <= CAP


async def test_users_get_returns_a_compact_contact(respx_mock, call):
    respx_mock.get(f"{API}/Users/149").mock(return_value=httpx.Response(200, json=halo_contact()))
    out = await call("halopsa_users_get", contact_id=149)
    assert out == {
        "id": 149,
        "name": "QA Contact",
        "emailaddress": "qa@example.com",
        "client_id": 40,
        "site_id": 60,
        "inactive": False,
    }


# ---- PRD-21469 ---------------------------------------------------------------


async def test_clients_create_saves_phone_and_email_through_new_client_fields(respx_mock, call):
    post = respx_mock.post(f"{API}/Client").mock(return_value=httpx.Response(201, json={"id": 40, "name": "QA"}))
    respx_mock.get(f"{API}/Client/40").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 40,
                "name": "QA",
                "main_site_id": 60,
                "main_phonenumber": "555-0100",
                "main_contact_email": "qa-client@example.com",
            },
        )
    )
    out = await call("halopsa_clients_create", name="QA", phonenumber="555-0100", email="qa-client@example.com")
    assert json.loads(post.calls.last.request.content) == [
        {
            "name": "QA",
            "newclient_phonenumber": "555-0100",
            "newclient_contactemail": "qa-client@example.com",
            "newclient_sendwelcomeemail": False,
        }
    ]
    assert out["main_phonenumber"] == "555-0100" and out["main_contact_email"] == "qa-client@example.com"
    assert "warning" not in out


async def test_clients_create_warns_when_halo_drops_a_value(respx_mock, call):
    respx_mock.post(f"{API}/Client").mock(return_value=httpx.Response(201, json={"id": 40}))
    respx_mock.get(f"{API}/Client/40").mock(return_value=httpx.Response(200, json={"id": 40, "main_site_id": 60}))
    out = await call("halopsa_clients_create", name="QA", phonenumber="555-0100")
    assert out["id"] == 40 and "phonenumber" in out["warning"]


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("halopsa_tickets_update", {"ticket_id": 99999999, "summary": "x"}, "No ticket 99999999"),
        ("halopsa_tickets_add_action", {"ticket_id": 99999999, "note": "x"}, "No ticket 99999999"),
    ],
)
async def test_writes_to_a_missing_ticket_are_not_found(respx_mock, call, tool, args, message):
    path = "/Tickets" if tool == "halopsa_tickets_update" else "/Actions"
    detail = "Record not found" if path == "/Tickets" else "Ticket not found."
    respx_mock.post(f"{API}{path}").mock(return_value=httpx.Response(400, text=detail))
    error = (await call(tool, **args))["error"]
    assert error["code"] == "not_found" and message in error["message"]


async def test_users_update_of_a_missing_contact_is_not_found_and_writes_nothing(respx_mock, call):
    respx_mock.get(f"{API}/Users/99999999").mock(return_value=httpx.Response(404, text="Not found"))
    post = respx_mock.post(f"{API}/Users")
    error = (await call("halopsa_users_update", contact_id=99999999, name="x"))["error"]
    assert error["code"] == "not_found" and error["message"] == "No contact 99999999 in HaloPSA."
    assert not post.called


async def test_tickets_create_for_a_missing_client_is_not_found_and_writes_nothing(respx_mock, call):
    respx_mock.get(f"{API}/Client/99999999").mock(return_value=httpx.Response(404, text="Not found"))
    post = respx_mock.post(f"{API}/Tickets")
    out = await call("halopsa_tickets_create", summary="x", client_id=99999999, tickettype_id=1)
    assert out["error"]["code"] == "not_found" and "No client 99999999" in out["error"]["message"]
    assert not post.called


async def test_bad_argument_types_use_the_envelope(call):
    for tool, args in (("halopsa_tickets_get", {"ticket_id": "abc"}), ("halopsa_lookups_get", {"kinds": ["bogus"]})):
        error = (await call(tool, **args))["error"]
        assert error["code"] == "invalid_argument" and error["retryable"] is False
