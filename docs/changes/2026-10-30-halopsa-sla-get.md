# 2026-10-30 Add halopsa_sla_get (PRD-21577)

New read tool `halopsa_sla_get(sla_id: int)` in `tools/lookups.py`, calling
`GET /SLA/{id}?includedetails=true`. It returns that SLA's `id`, `name` and `priorities`
(each with `id`, `name`, `responsetime`, `fixtime`, `colour`), so an agent can resolve a
priority name to the id `halopsa_tickets_create`/`_update` expect — the same lookup a
customer's Rewst flow ("PSA: Get Ticket Priorities") did against HaloPSA directly.

- Registered in the `lookups` domain alongside `halopsa_lookups_get`; no new domain or module,
  since no second SLA tool is planned.
- Follows the repo's "get by id with `includedetails`" shape (`halopsa_invoices_get`,
  `halopsa_clients_get`, ...) with one deliberate difference: the SLA's own fields go through
  `slim()` as usual, but `priorities` is built by slimming each row individually and always kept
  as a list (`[]` when the SLA has none configured). Running the whole record through `slim()`
  the way the sibling `*_get` tools do would drop `priorities` entirely when it is empty (`slim()`
  treats an empty list as an empty value) and would leave per-row empty fields (e.g. a priority
  with no `colour`) untrimmed, since `slim()`/`collapse()` only act on top-level fields.
- `sla_id` has no default (not even Ginko IT's own Rewst default of `1`): every other `_get` tool
  in this repo requires its id explicitly.
- No `halopsa_sla_list` (`GET /api/SLA`, no id) tool added — nothing in the ticket or its cited
  caller enumerates SLAs; can be a fast follow if a real need appears.
- No existing tool's behavior changes; purely additive.
- Not verified against a live HaloPSA tenant (no test account available in this environment).
