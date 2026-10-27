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
