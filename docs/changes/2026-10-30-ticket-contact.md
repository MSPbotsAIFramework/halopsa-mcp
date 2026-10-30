# 2026-10-30 Set a ticket's contact on create (PRD-21708)

`halopsa_tickets_create` had no way to set the new ticket's contact, even though the agent can
already find the right HaloPSA contact with `halopsa_users_search`/`halopsa_users_get` (`id`).
This was blocking migration of a Rewst workflow that sets the ticket's contact to the customer's
General User.

- New optional parameter `user_id: int | None`, passed straight through as HaloPSA's own `user_id`
  ticket field (same field `halopsa_tickets_get`/`_update` already read back). Omitting it is
  byte-for-byte the same request as before this change.
- Before the write, the id is checked against `GET /Users/{id}` (same `_require` guard already used
  for `client_id`); an id that is not a real HaloPSA contact fails with `not_found` naming the
  missing contact, and no ticket is created.
- Deliberately kept the name `user_id` (HaloPSA's own wire field) rather than this server's
  `contact_id` convention used on the contacts tools (`halopsa_users_get`/`_create`/`_update`), so
  the parameter matches what `halopsa_tickets_get`/`_update` already expose for the same entity and
  what the requester's acceptance check names verbatim. The description on the new parameter spells
  out that it is the same id the contacts tools call `id`, not `contact_id`.
- No new tool, no new required parameter, no change to any other tool's behavior.
- Not verified against a live HaloPSA tenant (no test account available in this environment): whether
  `/Tickets` needs anything besides a bare `user_id` to make the contact stick, the way `team_id`
  needs a companion `team` name. If wrong, this fails loudly as a HaloPSA-side error on the next real
  call, the same way any other bad write on this tool already does.
