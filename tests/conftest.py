# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from halopsa_mcp import credentials
from halopsa_mcp.config import Settings
from halopsa_mcp.server import create_mcp

ROOT = "https://example.halopsa.com"
API = f"{ROOT}/api"
TOKEN_URL = f"{ROOT}/auth/token"


@pytest.fixture
def settings() -> Settings:
    # Keep retries fast in tests.
    return Settings(max_retries=2, call_budget_seconds=10)


@pytest.fixture
def mcp(settings):
    return create_mcp(settings)


@pytest.fixture
def creds():
    token = credentials._current.set(
        credentials.Credentials(client_id="YOUR_CLIENT_ID", client_secret="YOUR_CLIENT_SECRET", tenant="example")
    )
    yield
    credentials._current.reset(token)


@pytest.fixture
def call(mcp):
    async def _call(tool: str, /, **args):
        result = await mcp.call_tool(tool, args)
        blocks = result[0] if isinstance(result, tuple) else result
        return json.loads(blocks[0].text)

    return _call
