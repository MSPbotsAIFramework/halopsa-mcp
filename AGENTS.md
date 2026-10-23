# AGENTS.md

HaloPSA MCP server for the MSPbots Agent Platform. Python 3.12, uv, official `mcp` SDK (FastMCP), Docker.

## Commands

- `uv sync`: install
- `uv run pytest -q`: tests
- `uv run ruff check . && uv run ruff format --check .`: lint
- `uv run halopsa-mcp`: run on 0.0.0.0:8080 (`/mcp`, `/health`)
- `docker build -t halopsa-mcp .`

## Layout

- `src/halopsa_mcp/server.py`: FastMCP instance, instructions, HTTP app
- `src/halopsa_mcp/credentials.py`: reads `X-Halo-*` headers into a per-request ContextVar; `resolve_endpoints()`
  turns tenant / base URL into the token and API URLs (called inside tools, never in middleware)
- `src/halopsa_mcp/api.py`: HaloPSA HTTP client (OAuth2 client credentials per call, retries, error mapping)
- `src/halopsa_mcp/tools/`: one module per area; `_common.py` has limits, annotations, `run()`;
  `meta.py` has `halopsa_navigate` (area -> tools map) and `halopsa_status`
- `tests/fixtures/tools_baseline.json`: tool names / parameters the platform already relies on

## Rules

- Credentials only from request headers; never from env, never cached across requests (no token cache either).
- Middleware only checks that headers are present. The platform probes `tools/list` with placeholder values,
  so validate formats inside tools and return the error envelope.
- Stateless (`stateless_http=True`); no module-level mutable state.
- Tools return JSON strings; errors use the envelope in `_json.py`; tools never raise.
- Do not rename tools, remove parameters or add required parameters: agents on the platform depend on them.
  `tests/test_tools.py` enforces this against the baseline. Never name a parameter `agent_id`
  (the platform injects its own value there); HaloPSA agent IDs are `halo_agent_id`.
- When adding a tool, add it to `DOMAINS` in `tools/meta.py`.
- English only. No real credentials, hostnames, tenant or customer data anywhere, including tests and history.
- No third-party branding other than the HaloPSA product itself.
- Add dependencies with `uv add`; commit `uv.lock`.
- Record changes in `docs/changes/` and releases in `docs/releases/`.
