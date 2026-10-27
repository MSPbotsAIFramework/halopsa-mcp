# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Invalid arguments come back as the invalid_argument envelope (PRD-20836)."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolRequest, CallToolRequestParams

from halopsa_mcp.config import Settings
from halopsa_mcp.server import create_mcp


def _server():
    return create_mcp(Settings())


async def _required_tool(mcp, types=("string", "integer", "number", "boolean")):
    for tool in await mcp.list_tools():
        required = tool.inputSchema.get("required") or []
        props = tool.inputSchema.get("properties", {})
        if required and props.get(required[0], {}).get("type") in types:
            return tool, required
    pytest.skip("no tool with a required scalar argument")


def _envelope(result):
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)["error"]


async def test_missing_required_argument_is_invalid_argument():
    mcp = _server()
    tool, required = await _required_tool(mcp)
    error = _envelope(await mcp.call_tool(tool.name, {}))
    assert error["code"] == "invalid_argument" and error["retryable"] is False
    assert required[0] in error["message"] and "Field required" in error["message"]


async def test_wrong_type_is_invalid_argument_without_echoing_the_value():
    mcp = _server()
    tool, required = await _required_tool(mcp)
    error = _envelope(await mcp.call_tool(tool.name, {name: {"secret-value": 1} for name in required}))
    assert error["code"] == "invalid_argument" and required[0] in error["message"]
    assert "secret-value" not in error["message"]


async def test_protocol_result_carries_the_envelope_like_other_tool_errors():
    mcp = _server()
    tool, _ = await _required_tool(mcp)
    handler = mcp._mcp_server.request_handlers[CallToolRequest]
    request = CallToolRequest(method="tools/call", params=CallToolRequestParams(name=tool.name, arguments={}))
    result = (await handler(request)).root
    assert result.isError is False
    assert json.loads(result.content[0].text)["error"]["code"] == "invalid_argument"


async def test_unknown_tool_is_unchanged():
    with pytest.raises(ToolError, match="Unknown tool"):
        await _server().call_tool("no_such_tool", {})
