# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""PRD-22078: halopsa_users_search can list all contacts, search by phone, and returns the detail
field set (every phone field), for mb-platform-agent's HaloPSA contact-sync adapter."""

import httpx
import pytest

from conftest import API, TOKEN_URL

pytestmark = pytest.mark.usefixtures("creds")


@pytest.fixture(autouse=True)
def token_route(respx_mock):
    return respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))


ROW = {
    "id": 42,
    "name": "Jane Doe",
    "firstname": "Jane",
    "surname": "Doe",
    "emailaddress": "jane@acme.test",
    "phonenumber": "2175550100",
    "phonenumber_preferred": "",
    "mobilenumber": "2175550199",
    "mobilenumber2": "",
    "client_id": 9,
    "client_name": "Acme",
    "site_id": 1,
    "site_name": "HQ",
    "inactive": False,
    "customfields": [],
    "a_field_not_in_the_detail_set": "should be dropped",
}


async def test_query_omitted_lists_every_contact(respx_mock, call):
    route = respx_mock.get(f"{API}/Users").mock(return_value=httpx.Response(200, json={"record_count": 1, "users": [ROW]}))
    out = await call("halopsa_users_search")
    assert "search" not in route.calls.last.request.url.params
    assert [r["id"] for r in out["items"]] == [42]


async def test_response_is_the_detail_field_set_not_the_narrow_one(respx_mock, call):
    respx_mock.get(f"{API}/Users").mock(return_value=httpx.Response(200, json={"record_count": 1, "users": [ROW]}))
    out = await call("halopsa_users_search", query="Jane")
    item = out["items"][0]
    assert item["phonenumber"] == "2175550100"
    assert item["mobilenumber"] == "2175550199"
    assert "a_field_not_in_the_detail_set" not in item
    # blank detail fields are dropped by slim(), same as halopsa_users_get's own contract.
    assert "phonenumber_preferred" not in item
    assert "client_name" in item and item["client_name"] == "Acme"


async def test_search_phonenumbers_is_passed_through_to_the_vendor_api(respx_mock, call):
    route = respx_mock.get(f"{API}/Users").mock(return_value=httpx.Response(200, json={"record_count": 0, "users": []}))
    await call("halopsa_users_search", query="2175550100", search_phonenumbers=True)
    params = route.calls.last.request.url.params
    assert params["search"] == "2175550100"
    assert params["search_phonenumbers"] == "true"


async def test_search_phonenumbers_without_a_query_is_rejected(call):
    out = await call("halopsa_users_search", search_phonenumbers=True)
    assert out["error"]["code"] == "invalid_argument"


async def test_include_inactive_still_works_with_no_query(respx_mock, call):
    route = respx_mock.get(f"{API}/Users").mock(return_value=httpx.Response(200, json={"record_count": 0, "users": []}))
    await call("halopsa_users_search", include_inactive=True)
    assert route.calls.last.request.url.params["includeinactive"] == "true"
