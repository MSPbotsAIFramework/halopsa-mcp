# 2026-11-01 Fix halopsa_tickets_add_attachment payload (PRD-21372)

On INT (2026-11-01, HaloPSA Test client, ticket 3543) every `halopsa_tickets_add_attachment` call
failed with `HaloPSA returned 500` and no file reached the ticket: CSV and HTML, base64 and text,
with and without a note. Creating the ticket and the note worked, so only the attachment request
body was wrong.

HaloPSA's API documentation (Rest API 2.256.7, Resources > Attachments, `POST /Attachment` example
request) settles the two points the 2026-10-27 change left unverified:

- `data_base64` is a data URL, `"data:mimetype;base64,base64string"`, not plain base64.
- The `Attachment` object has no `content_type` and no `isimage` field. Its fields are `id`,
  `filename`, `datecreated`, `note`, `filesize`, `type`, `unique_id`, `desc`, `data`, `ticket_id`,
  `action_id`, `user_id`, `agent_id`, `attachmentaction_id`, `_canupdate`, `_warning`, `showforusers`,
  `data_base64`.

Changes:

- `POST /Attachment` now sends `ticket_id`, `filename`, `data_base64` as
  `data:<content_type>;base64,<content>`, `showforusers` (= not `hidden_from_user`) and, with a note,
  `action_id`. `content_type` and `isimage` are no longer sent; the tool's `content_type` parameter
  and result field are unchanged and now set the type inside the data URL.
- `.csv`, `.html`/`.htm`, `.txt`, `.json` and `.pdf` get a fixed type before `mimetypes` is asked.
  On Windows `mimetypes` reads the registry, which maps `.csv` to `application/vnd.ms-excel`.
- Writes (`POST` and other non-GET calls) are no longer retried on 5xx or timeouts, only on 429.
  HaloPSA may already have saved the record when it fails, so a resend could attach a file or add
  a note twice. GET requests and the token request keep the old retries.

Still to confirm on INT after this is deployed: that the file opens with unchanged content, that
`action_id` links it to the note, and that `showforusers` controls end-user visibility.
