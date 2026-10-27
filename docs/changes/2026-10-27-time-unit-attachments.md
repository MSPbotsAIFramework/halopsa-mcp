# 2026-10-27 Time unit on actions, ticket attachments

## Time logged on actions (PRD-21378)

The previous HaloPSA connector described `timetaken` as minutes but passed the number to HaloPSA,
which stores an action's `timetaken` as decimal hours, so 11 minutes were logged as 11 hours. This
server has converted minutes to hours since its first version; the unit is now explicit:

- `halopsa_tickets_add_action`: new optional `time_taken_minutes`. `timetaken` keeps its meaning
  (minutes, as the registered connector described it) and its description now says so in capitals.
  Both are divided by 60 and rounded to 4 places (11 -> 0.1833). Passing both, or a negative value,
  returns `invalid_argument`.
- Returned actions (`halopsa_tickets_add_action`, `halopsa_tickets_get` with actions) keep HaloPSA's
  `timetaken` in hours and add `time_taken_minutes`. The tool and `include_actions` descriptions
  state that `timetaken` is hours.
- No other tool takes a time value.

## Ticket attachments (PRD-21372)

New tool `halopsa_tickets_add_attachment` (27 tools now), so agents can attach generated reports
(CSV, HTML, ...) to a ticket.

- Parameters: `ticket_id`, `filename`, `content` (required); `content_encoding` (`base64` default, or
  `text` for UTF-8 text sent as is), `content_type` (defaults to the type of the file extension,
  `application/octet-stream` if unknown; a `data:<type>;base64,` prefix on `content` is accepted and
  its type used), `note`, `hidden_from_user` (default true).
- HaloPSA API (public swagger, `Attachment` schema): `POST /Attachment` with a JSON array of one
  object carrying `ticket_id`, `filename`, `data_base64`, `content_type`, `isimage`, `showforusers`
  (= not `hidden_from_user`) and, with a note, `action_id`. The note is `POST /Actions` (outcome
  `Note`, `hiddenfromuser` = `hidden_from_user`) made before the upload.
- The ticket is read first so a missing ticket returns `not_found` without uploading anything.
- Limit: 10 MB per file after decoding; larger files and invalid base64 return `invalid_argument`.
  The base64 length is checked before decoding.
- The result is `{ticket_id, attachment_id, action_id?, filename, content_type, size_bytes,
  hidden_from_user}`; the content is never echoed. If the upload fails after the note was added, the
  error names the note action.
- Not verified against a live HaloPSA tenant: that `data_base64` takes plain base64 (no data-URL
  prefix), that `action_id` links the file to the note, and that `showforusers` controls end-user
  visibility of a ticket attachment.
