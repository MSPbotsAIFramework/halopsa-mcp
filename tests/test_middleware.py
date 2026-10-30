# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
import pytest
from starlette.testclient import TestClient

from halopsa_mcp import credentials
from halopsa_mcp.config import Settings
from halopsa_mcp.server import create_app

LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
PROBE = {
    "X-Halo-Client-Id": "probe-placeholder",
    "X-Halo-Client-Secret": "probe-placeholder",
    "X-Halo-Tenant": "probe-placeholder",
    "X-Halo-Base-Url": "probe-placeholder",
}


@pytest.fixture
def client():
    with TestClient(create_app(Settings())) as c:
        yield c


def test_health_needs_no_credentials(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_missing_headers_is_401(client):
    r = client.post("/mcp", json=LIST, headers=HEADERS)
    assert r.status_code == 401
    body = r.json()
    assert body["required_headers"] == ["X-Halo-Client-Id", "X-Halo-Client-Secret"]
    assert body["one_of_headers"] == ["X-Halo-Tenant", "X-Halo-Base-Url"]


def test_missing_tenant_and_base_url_is_401(client):
    h = {**HEADERS, "X-Halo-Client-Id": "a", "X-Halo-Client-Secret": "b"}
    r = client.post("/mcp", json=LIST, headers=h)
    assert r.status_code == 401
    assert "X-Halo-Tenant or X-Halo-Base-Url" in r.json()["message"]


def test_placeholder_values_are_accepted(client):
    # The platform probes with placeholders; no format validation in middleware.
    r = client.post("/mcp", json=LIST, headers={**HEADERS, **PROBE})
    assert r.status_code == 200
    assert len(r.json()["result"]["tools"]) == 29


@pytest.mark.parametrize("location", ["x-halo-tenant", "x-halo-base-url"])
def test_either_location_header_is_enough(client, location):
    h = {**HEADERS, "x-halo-client-id": "a", "x-halo-client-secret": "b", location: "anything"}
    assert client.post("/mcp", json=LIST, headers=h).status_code == 200


def test_initialize_then_list(client):
    h = {**HEADERS, **PROBE}
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    }
    assert client.post("/mcp", json=init, headers=h).status_code == 200
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert client.post("/mcp", json=note, headers=h).status_code in (200, 202)
    assert client.post("/mcp", json=LIST, headers=h).status_code == 200


def C(**kw):
    return credentials.Credentials(client_id="a", client_secret="b", **kw)


@pytest.mark.parametrize(
    ("creds", "root", "tenant_param"),
    [
        (C(tenant="acme"), "https://acme.halopsa.com", None),
        (C(tenant="ACME.halopsa.com"), "https://acme.halopsa.com", None),
        (C(tenant="https://acme.halopsa.com/"), "https://acme.halopsa.com", None),
        (C(base_url="https://halo.example.com/"), "https://halo.example.com", None),
        (C(base_url="https://halo.example.com/api"), "https://halo.example.com", None),
        (C(base_url="https://halo.example.com/auth"), "https://halo.example.com", None),
        (C(tenant="acme", base_url="https://halo.example.com"), "https://halo.example.com", "acme"),
        (C(tenant="${HALO_TENANT}", base_url="https://halo.example.com"), "https://halo.example.com", None),
        (C(tenant="acme", base_url="${HALO_BASE_URL}"), "https://acme.halopsa.com", None),
    ],
)
def test_resolve_endpoints(creds, root, tenant_param):
    ep = credentials.resolve_endpoints(creds)
    assert ep.root == root
    assert ep.token_url == f"{root}/auth/token" and ep.api_url == f"{root}/api"
    assert ep.tenant == tenant_param


@pytest.mark.parametrize(
    "creds",
    [
        C(base_url="http://halo.example.com"),
        C(base_url="probe-placeholder"),
        C(tenant="bad tenant!"),
        C(tenant="${X}"),
        C(),
    ],
)
def test_resolve_endpoints_rejects(creds):
    with pytest.raises(credentials.CredentialError):
        credentials.resolve_endpoints(creds)


def test_credentials_do_not_leak_between_requests():
    assert credentials.current() is None
