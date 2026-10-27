# HaloPSA MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that lets AI agents on the
MSPbots Agent Platform work in HaloPSA: tickets and ticket notes, clients, sites, contacts, assets,
agents and teams, invoices, and the reference tables (statuses, priorities, ticket types, categories)
needed to write tickets correctly.

It runs as a stateless HTTP service behind the MSPbots MCP gateway. The gateway sends each
tenant's HaloPSA credentials as request headers on every call; the server keeps nothing between
requests.

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Credentials (request headers)

| Header | Required | Meaning |
|---|---|---|
| `X-Halo-Client-Id` | Yes | Client ID of a HaloPSA API application (**Config > Integrations > Halo API > View Applications**) using the **Client ID and Secret (Services)** authentication method. |
| `X-Halo-Client-Secret` | Yes | Client secret of that application. |
| `X-Halo-Tenant` | One of these two | Tenant name of a hosted instance: `yourcompany` for `https://yourcompany.halopsa.com`. |
| `X-Halo-Base-Url` | One of these two | Instance URL, e.g. `https://yourcompany.halopsa.com` or a custom domain (`https://` only). Takes precedence over the tenant. A trailing `/api` or `/auth` is accepted. |

Header names are case-insensitive. A request to `/mcp` without the client ID, the secret, or both
the tenant and base URL gets `401` with the list of expected headers. The middleware only checks
that the headers are present; a malformed tenant or base URL is reported by each tool as
`not_configured`.

The server gets an OAuth2 token (`client_credentials`, `scope=all`) from `<instance>/auth/token`
on every tool call and calls the REST API at `<instance>/api`. When both a base URL and a tenant are
sent, the tenant is added to the token request as `?tenant=` (as HaloPSA requires for some hosted
instances). Tokens are never cached between requests. Give the API application an agent with the
permissions the agents need (read tickets, clients, assets, invoices; write tickets, actions,
clients and contacts).

## Tools

| Area | Tools |
|---|---|
| Discovery | `halopsa_navigate`, `halopsa_status` |
| Tickets | `halopsa_tickets_list`, `halopsa_tickets_get`, `halopsa_tickets_create`, `halopsa_tickets_update`, `halopsa_tickets_add_action` |
| Clients | `halopsa_clients_list`, `halopsa_clients_get`, `halopsa_clients_create`, `halopsa_clients_search` |
| Assets | `halopsa_assets_list`, `halopsa_assets_get`, `halopsa_assets_search`, `halopsa_assets_list_types` |
| Agents and teams | `halopsa_agents_list`, `halopsa_agents_get`, `halopsa_teams_list` |
| Invoices | `halopsa_invoices_list`, `halopsa_invoices_get` |
| Reference data | `halopsa_lookups_get` |
| Contacts | `halopsa_users_search`, `halopsa_users_get`, `halopsa_users_create`, `halopsa_users_update` |
| Sites | `halopsa_sites_list` |

Tool names and parameters match the previous HaloPSA connector on the MSPbots Agent Platform, so
existing agents keep working. This is why the server has more than 20 tools.

Behaviour notes:

- Every tool returns a JSON string. Errors use one envelope:
  `{"error": {"code": "...", "message": "...", "retryable": false}}` with `code` one of
  `not_configured`, `unauthorized`, `not_found`, `invalid_argument`, `rate_limited`, `upstream_error`.
  HaloPSA's own error text is included in the message.
- List and search tools return `{"items", "count", "limit", "offset", "has_more"}` (plus `total_count`
  where HaloPSA reports it) and take `offset`. When `has_more` is true, `next_offset` is where to
  continue; it always starts right after the last record returned, also when a page was cut to fit
  the 20,000-character limit (`truncated`). A call can return fewer than `limit` records while more
  remain. `limit` defaults to 50 (25 for the search tools, 100 for asset types) and is capped at 200;
  tickets are capped at 100 per page (HaloPSA's maximum). `page_no` on `halopsa_tickets_list` still
  works. Records too long on their own come back with long fields shortened (`fields_truncated`),
  never as a text preview.
- All tools are always listed. `halopsa_navigate` only describes the tools of one area (teams are
  under `agents`); `halopsa_status` shows which headers were sent, the instance URL and whether a
  token could be obtained, without revealing secrets.
- Tickets: a HaloPSA ticket has about 1,000 fields plus the full definition of every custom field
  (about 70,000 characters for a new ticket). `halopsa_tickets_get/create/update` return the fields
  agents use (summary, details, status, type, priority, client, site, contact, agent, team,
  categories, dates), related records reduced to `{id, name}` and only the custom fields that hold a
  value, unless `full_response` is true. With `include_actions`, actions are paged with
  `actions_limit` / `actions_offset` (`next_actions_offset`). `halopsa_users_get` returns the contact
  the same way; the other get tools drop empty values and "no date" dates.
- `halopsa_clients_create`: HaloPSA has no phone or email on a client. `phonenumber` is saved on the
  main site and `email` on the client's main contact (`contact_name`, default "Main Contact"; HaloPSA creates it with
  the client, otherwise it is added as a contact of the main site; no welcome email is sent); the result shows `main_phonenumber` / `main_contact_email` as HaloPSA stored them, with a
  `warning` if a value was not saved.
- Writes to a record that does not exist return `not_found` naming it; invalid arguments (wrong type,
  missing, unknown value) return the `invalid_argument` envelope.
- `halopsa_tickets_update` changes only the fields given. `team_id` assigns the team (the team name is
  looked up and sent with it); `custom_fields` writes custom fields by id or name; `tickettype_id` is
  applied through a hidden action and the ticket is re-read to confirm the change stuck, otherwise
  the tool returns an error.
- `halopsa_tickets_add_action` takes `timetaken` in minutes and sends HaloPSA hours.
- `halopsa_users_create` refuses (and returns the existing contact) when the email is already used
  by any contact, active or inactive, and defaults `site_id` to the client's main site.
- `halopsa_invoices_list`: `status` accepts `posted` / `notposted` (sent to HaloPSA); `sent`, `paid`
  and the invoice date range are applied to the latest 200 invoices HaloPSA returns and the result
  says so.
- `halopsa_lookups_get` returns the identifying fields of each row; for priorities,
  `ticket_priority_id` is the value a ticket's `priority_id` takes. A table that fails is reported in
  place without failing the others.
- Transient failures (429, 5xx, timeouts) are retried with backoff, honouring `Retry-After`; one tool
  call stays under 120 seconds.

## Run locally

```bash
uv sync
uv run halopsa-mcp            # listens on 0.0.0.0:8080
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "X-Halo-Client-Id: $HALO_CLIENT_ID" -H "X-Halo-Client-Secret: $HALO_CLIENT_SECRET" \
  -H 'X-Halo-Tenant: yourcompany' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Environment variables (all optional): `MCP_HTTP_HOST` (default `0.0.0.0`), `MCP_HTTP_PORT`
(default `8080`), `MCP_TRANSPORT` (`http` or `stdio`). Unknown variables are ignored. Credentials
are never read from the environment.

## Docker

```bash
docker build -t halopsa-mcp .
docker run --rm -p 8080:8080 halopsa-mcp
```

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Code is in `src/halopsa_mcp/` (one module per area under `tools/`), tests in `tests/`.
The implementation follows the public HaloPSA API documentation at https://halo.halopsa.com/apidoc/
(each instance also serves it at `/apidoc/`).

## License

Copyright 2026 MSPbots.ai. Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE)
and [NOTICE](NOTICE).

HaloPSA is a trademark of its owner. This project is not affiliated with or endorsed by Halo.
