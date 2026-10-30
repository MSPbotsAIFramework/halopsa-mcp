# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""tools/list contract: names and parameters must stay compatible with the registered connector."""

import json
from pathlib import Path

BASELINE = {t["name"]: t for t in json.loads((Path(__file__).parent / "fixtures" / "tools_baseline.json").read_text())}

COMPATIBLE = {
    "number": {"number", "integer"},
    "integer": {"integer"},
    "string": {"string"},
    "boolean": {"boolean"},
    "array": {"array"},
    "object": {"object"},
}


async def _tools(mcp):
    return {t.name: t for t in await mcp.list_tools()}


def _types(schema: dict) -> set[str]:
    """JSON types a property accepts, ignoring null."""
    if "anyOf" in schema:
        out: set[str] = set()
        for option in schema["anyOf"]:
            out |= _types(option)
        return out
    value = schema.get("type")
    types = set(value) if isinstance(value, list) else {value} if value else set()
    return types - {"null"}


async def test_tool_names_match_baseline(mcp):
    assert set(await _tools(mcp)) == set(BASELINE)


async def test_parameters_are_backward_compatible(mcp):
    tools = await _tools(mcp)
    for name, expected in BASELINE.items():
        schema = tools[name].inputSchema
        props = schema.get("properties", {})
        base_props = expected["inputSchema"].get("properties", {})
        required = set(schema.get("required", []))
        assert set(base_props) <= set(props), f"{name} lost parameters"
        assert required <= set(expected["inputSchema"].get("required", [])), f"{name} gained required parameters"
        for param, base in base_props.items():
            mine = _types(props[param])
            for t in _types(base):
                assert mine & COMPATIBLE[t], f"{name}.{param}: {t} not accepted (got {mine})"
            if "enum" in base:
                options = props[param].get("anyOf", [props[param]])
                enums = {v for o in options for v in o.get("enum", [])}
                assert set(base["enum"]) <= enums, f"{name}.{param} lost enum values"


async def test_descriptions_are_concise(mcp):
    for tool in (await _tools(mcp)).values():
        assert tool.description and len(tool.description) <= 500, tool.name


async def test_annotations(mcp):
    tools = await _tools(mcp)
    for name, tool in tools.items():
        is_read = any(
            name.endswith(s)
            for s in ("_list", "_get", "_search", "_list_types", "_list_actions", "_status", "_navigate")
        )
        assert tool.annotations.readOnlyHint is is_read, name
        assert tool.annotations.destructiveHint is False, name  # no delete tools


async def test_no_agent_id_parameter(mcp):
    # The platform injects its own value into parameters named agent_id.
    for tool in (await _tools(mcp)).values():
        assert "agent_id" not in tool.inputSchema.get("properties", {}), tool.name


async def test_navigate_covers_every_tool(mcp):
    from halopsa_mcp.tools.meta import DOMAINS

    listed = {n for _, names in DOMAINS.values() for n in names}
    assert listed | {"halopsa_navigate", "halopsa_status"} == set(BASELINE)
    assert "halopsa_teams_list" in DOMAINS["agents"][1]


async def test_tools_list_snapshot(mcp):
    """Rough snapshot so accidental schema changes show up in review."""
    tools = await _tools(mcp)
    summary = {n: sorted(t.inputSchema.get("properties", {})) for n, t in tools.items()}
    assert summary["halopsa_tickets_update"][:3] == ["category_1", "category_2", "category_3"]
    assert "custom_fields" in summary["halopsa_tickets_update"]
    assert len(tools) == 29
