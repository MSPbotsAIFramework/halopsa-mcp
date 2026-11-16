# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""PRD-22078: phone_fields on contacts, clients and sites, and halopsa_phone_search."""

import httpx
import pytest

from conftest import API, TOKEN_URL
from halopsa_mcp.tools._common import country_of, phone_fields

pytestmark = pytest.mark.usefixtures("creds")


@pytest.fixture(autouse=True)
def token_route(respx_mock):
    return respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))


CONTACT = {
    "id": 122,
    "name": "Alan Reed",
    "client_id": 23,
    "client_name": "Metro Sales",
    "phonenumber": "7084577301",
    "homenumber": "7084577302",
    "mobilenumber": "7084577303",
    "fax": "7084577304",
    "phonenumber_preferred": "  ",
    "whatsapp_number": "",
    "client_id_ext": "9",
    "mobilenumber_use": "yes",
}


def test_phone_fields_keeps_every_number_and_drops_blank_and_non_number_keys():
    assert phone_fields(CONTACT) == {
        "phonenumber": "7084577301",
        "homenumber": "7084577302",
        "mobilenumber": "7084577303",
        "fax": "7084577304",
    }


def test_phone_fields_ignores_ids_names_and_extension_keys():
    row = {"phone_country": "US", "site_phone_ext": "12", "telephone": "2175550100", "client_name": "Phoneworks"}
    assert phone_fields(row) == {"telephone": "2175550100"}


def test_country_of_reads_any_country_key():
    assert country_of({"country": "Canada"}) == "Canada"
    assert country_of({"country_code": " GB "}) == "GB"
    assert country_of({"name": "x"}) is None


async def test_users_search_returns_home_and_fax_in_phone_fields(respx_mock, call):
    route = respx_mock.get(f"{API}/Users").mock(
        return_value=httpx.Response(200, json={"record_count": 1, "users": [CONTACT]})
    )
    out = await call("halopsa_users_search", include_inactive=True, include_details=True)
    assert route.calls.last.request.url.params["includedetails"] == "true"
    item = out["items"][0]
    assert item["phone_fields"]["homenumber"] == "7084577302"
    assert item["phone_fields"]["fax"] == "7084577304"
    assert item["phonenumber"] == "7084577301"  # flat keys stay, back-compat


async def test_users_get_returns_phone_fields(respx_mock, call):
    respx_mock.get(f"{API}/Users/122").mock(return_value=httpx.Response(200, json=CONTACT))
    out = await call("halopsa_users_get", contact_id=122)
    assert out["phone_fields"]["fax"] == "7084577304"


async def test_sites_list_adds_phone_fields_client_and_country(respx_mock, call):
    site = {
        "id": 5,
        "name": "Chicago",
        "client_id": 23,
        "client_name": "Metro Sales",
        "phonenumber": "3125550100",
        "country": "Canada",
    }
    respx_mock.get(f"{API}/Site").mock(return_value=httpx.Response(200, json={"record_count": 1, "sites": [site]}))
    item = (await call("halopsa_sites_list"))["items"][0]
    assert item["phone_fields"] == {"phonenumber": "3125550100"}
    assert item["country"] == "Canada"
    assert item["client_id"] == 23 and item["name"] == "Chicago"


async def test_clients_list_adds_phone_fields(respx_mock, call):
    row = {"id": 23, "name": "Metro Sales", "main_phonenumber": "3125550000"}
    respx_mock.get(f"{API}/Client").mock(return_value=httpx.Response(200, json={"record_count": 1, "clients": [row]}))
    item = (await call("halopsa_clients_list", inactive=True))["items"][0]
    assert item["phone_fields"] == {"main_phonenumber": "3125550000"}


def _route(respx_mock, path, key, rows):
    return respx_mock.get(f"{API}/{path}").mock(
        return_value=httpx.Response(200, json={"record_count": len(rows), key: rows})
    )


async def test_phone_search_single_contact_stops_after_one_request(respx_mock, call):
    users = _route(respx_mock, "Users", "users", [CONTACT])
    clients = _route(respx_mock, "Client", "clients", [])
    out = await call("halopsa_phone_search", phone="+1 (708) 457-7302")
    assert [c["id"] for c in out["contacts"]] == [122]
    assert out["clients"] == []
    assert users.call_count == 1 and clients.call_count == 0
    assert users.calls.last.request.url.params["search"] == "17084577302"


async def test_phone_search_client_main_number(respx_mock, call):
    _route(respx_mock, "Users", "users", [])
    _route(respx_mock, "Client", "clients", [{"id": 23, "name": "Metro Sales", "main_phonenumber": "3125550000"}])
    _route(respx_mock, "Site", "sites", [])
    out = await call("halopsa_phone_search", phone="312-555-0000")
    assert out["contacts"] == []
    assert out["clients"][0]["id"] == 23 and out["clients"][0]["matched"] == "main"


async def test_phone_search_site_number_returns_the_client(respx_mock, call):
    _route(respx_mock, "Users", "users", [])
    _route(respx_mock, "Client", "clients", [])
    site = {"id": 5, "name": "Chicago", "client_id": 23, "client_name": "Metro Sales", "phonenumber": "3125550100"}
    _route(
        respx_mock, "Site", "sites", [site, {"id": 6, "name": "Other", "client_id": 24, "phonenumber": "9995550199"}]
    )
    out = await call("halopsa_phone_search", phone="3125550100")
    assert [(c["id"], c["matched"], c["site_name"]) for c in out["clients"]] == [(23, "site", "Chicago")]


async def test_phone_search_no_hit(respx_mock, call):
    _route(respx_mock, "Users", "users", [{"id": 1, "name": "X", "phonenumber": "1112223333"}])
    _route(respx_mock, "Client", "clients", [])
    _route(respx_mock, "Site", "sites", [])
    out = await call("halopsa_phone_search", phone="3125550100")
    assert out == {"contacts": [], "clients": []}


async def test_phone_search_rejects_a_too_short_number(call):
    out = await call("halopsa_phone_search", phone="12")
    assert out["error"]["code"] == "invalid_argument"
