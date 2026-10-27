# 2026-10-27 Exact paging, compact records, error codes

QA findings on INT (PRD-21467, PRD-21468, PRD-21469).

- **Paging (PRD-21467)**: `_json.py` replaced with the shared version used by the other MSPbotsAIFramework
  vendors. Every list and search tool takes `offset` and returns `offset` / `next_offset`;
  `next_offset` resumes right after the last record returned, also when a page is cut to fit the size
  limit, so following it reaches every record once. HaloPSA-paged endpoints (`/Tickets`, `/Client`,
  `/Users`, `/Asset`, `/Invoice`, `/Site`) are read with `pageinate`; `/Agent`, `/Team`,
  `/AssetType` and the reference tables are read whole and sliced. `page_no` on
  `halopsa_tickets_list` still works but no longer appears in results. Invoice `sent` / `paid` / date
  filters are applied to one 200-invoice page per call and continue by `next_offset`. Invoices are
  now ordered with HaloPSA's `order` parameter (was `orderby`, which HaloPSA ignores).
- **Records (PRD-21468)**: tickets and contacts return the main fields by default (`full_response`
  for the raw record); custom fields are reduced to id / name / label / value / display and only
  those set. Other get tools drop empty values and "no date" dates. Ticket actions are paged with
  `actions_limit` (default 20) / `actions_offset`. A record still too large has long fields shortened
  (`fields_truncated`) instead of a text preview.
- **Errors and writes (PRD-21469)**: `halopsa_clients_create` sends phone and email as
  `newclient_phonenumber` / `newclient_contactemail` (welcome email off), re-reads the client and warns
  if HaloPSA did not store them. Writes to a missing ticket, contact or client return `not_found`
  (HaloPSA's 400 "not found" is mapped; `halopsa_users_update` and `halopsa_tickets_create` check the
  contact / client first, so no record is created by mistake). Argument-validation errors use the
  `invalid_argument` envelope (PRD-20836 handler, `_arguments.py`).
- **Retest fix (PRD-21469)**: HaloPSA creates no main contact from `newclient_contactemail` alone, so
  the email was dropped. `halopsa_clients_create` now also sends `newclient_contactname` (new optional
  `contact_name`, default "Main Contact"); if the re-read client still has no main contact email, the
  contact is added with `POST /Users` on the main site (`ismaincontact: true`) and the client is read again.
