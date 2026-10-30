# 2026-10-30 Add halopsa_tickets_list_actions (PRD-21575)

Ginko IT's Rewst flows (an AI reply-suggestion flow and nine webhook "Update Ticket" flows) call
HaloPSA's `GET /Actions?ticket_id={id}&excludesys=true` (plus ten other optional filters) to read a
ticket's action history. None of the connector's 27 existing tools covered this: the only read path,
`halopsa_tickets_get`'s `include_actions`, sends none of HaloPSA's own `/Actions` filters and returns
a narrower field set.

- New read-only tool `halopsa_tickets_list_actions(ticket_id, ...11 optional filters, limit, offset,
  full_response)` in `src/halopsa_mcp/tools/tickets.py`. Each of HaloPSA's 11 native `/Actions` filters
  (`excludesys`, `excludeprivate`, `agentonly`, `supplieronly`, `importantonly`, `ischildnotes`,
  `includehtmlnote`, `includehtmlemail`, `includeattachments`, `slaonly`, `conversationonly`) is sent
  only when the caller sets it; unset flags are omitted so HaloPSA's own defaults apply.
- Ticket-scoped: a `GET /Tickets/{id}` existence check runs first, so a nonexistent ticket returns
  `not_found` naming it rather than a misleadingly empty action list.
- Returns a richer field set than `halopsa_tickets_get`'s `include_actions` path: adds `who_type`,
  `who_agentid`, `note_html`, `old_status`, `attachment_count`, `replied_to_action_id` to the existing
  `id`/`ticket_id`/`datetime`/`who`/`outcome`/`note`/`timetaken`/`hiddenfromuser`/`important`/
  `new_status` set, plus the derived `time_taken_minutes` (same convention as every other action
  response here). Kept as a separate field tuple (`LIST_ACTIONS_FIELDS`) rather than widening the
  existing `ACTION_FIELDS`, so `halopsa_tickets_get(include_actions=true)`'s response shape is
  unchanged for existing callers.
- Uses the standard list envelope (`items`/`count`/`limit`/`offset`/`has_more`/`next_offset`), reusing
  the same over-fetch-and-slice technique `halopsa_tickets_get` already uses for `/Actions` (that
  technique is now shared as `_fetch_actions()`, used by both tools, byte-for-byte the same request
  `halopsa_tickets_get` already sent). `total_count` is HaloPSA's own `record_count` when it sends one,
  omitted otherwise — not the size of the over-fetched page.
- No new file, no new dependency, no schema/DB change (this server is stateless and has none). No
  existing tool lost a parameter, gained a required parameter, or was renamed; a new entry was added to
  `tests/fixtures/tools_baseline.json` for the new tool only.
- Not verified against a live HaloPSA tenant (no test account available in this environment): whether
  `/Actions` itself 404s or returns zero rows for a bad `ticket_id` (the explicit existence check makes
  this moot either way); the live field names for `who_type`/`who_agentid`/`old_status`/
  `attachment_count`/`replied_to_action_id`; and whether `include_html_note`/`include_html_email`
  populate `note_html` the way the Rewst migration expects. `pick()` silently drops any field HaloPSA
  does not send, so a misnamed field degrades to "absent" rather than a crash.
