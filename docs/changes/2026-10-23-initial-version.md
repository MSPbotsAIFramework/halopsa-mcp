# 2026-10-23 Initial version

First release of the MSPbots HaloPSA MCP server, written from the public HaloPSA API documentation.

- 26 tools covering tickets and ticket actions, clients, assets and asset types, agents and teams,
  invoices, reference tables (statuses, priorities, ticket types, Category 1-4), contacts and sites,
  plus `halopsa_navigate` and `halopsa_status`.
- Tool names and parameters are compatible with the previous HaloPSA connector on the platform
  (enforced by `tests/test_tools.py` against `tests/fixtures/tools_baseline.json`).
- Credentials: `X-Halo-Client-Id`, `X-Halo-Client-Secret` (required) and `X-Halo-Tenant` or
  `X-Halo-Base-Url` (at least one; the base URL wins). The middleware only checks presence;
  formats are validated in the tools (`not_configured`). A token is obtained per tool call and never
  cached.
- Behaviour kept from the previous connector's MSPbots changes: teams listed under the `agents`
  area; `team_id` and `custom_fields` on ticket update; `halo_agent_id` instead of `agent_id`;
  expanded ticket records collapsed unless `full_response`; HaloPSA's error text surfaced;
  list rows accepted whether HaloPSA wraps them or not; `halopsa_lookups_get`; ticket type change
  through a hidden action with an outcome, verified afterwards; contact duplicate check including
  inactive contacts; contact `site_id` defaulting to the client's main site; ticket date range and
  `page_no`; unresolved `${...}` placeholders in tenant / base URL treated as absent.
- Behaviour differences from the previous connector:
  - All tools are always listed; `halopsa_navigate` is a stateless description of one area.
  - `halopsa_status` reports header presence, the instance URL and a live token/API check.
  - Ticket pages are capped at 100 (HaloPSA's maximum); other lists at 200.
  - `halopsa_invoices_list`: `status` only accepts `posted` / `notposted` (other values return
    `invalid_argument`); `sent`, `paid` and the date range are filtered over the latest 200 invoices
    returned by HaloPSA, and the result carries a note.
  - `halopsa_tickets_add_action` converts `timetaken` from minutes to HaloPSA hours; `outcome`
    defaults to `Note`.
  - `halopsa_users_create` returns `{"created": false, "duplicate": true, "existing": {...}}` for a
    duplicate email instead of an error.
  - New optional parameters: `team_id` and `search` on `halopsa_tickets_list`, `team_id` on
    `halopsa_tickets_create`, `client_id` and `include_inactive` on `halopsa_users_search`.
  - `limit` / `page_no` values below 1 are clamped instead of rejected.
- Not verified against a live HaloPSA tenant (no account available): the `datesearch=dateoccurred`
  value, the `/Priority` and `/Category` endpoints and their `priorityid` / `type_id` fields, the
  `tickettype_id` filter on statuses and categories, `section_id` as the team filter on agents, and
  the `new_tickettype` action field.
