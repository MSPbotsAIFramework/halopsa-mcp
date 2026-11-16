# 2026-11-16 Every phone number on contacts, clients and sites, and a phone-owner search (PRD-22078)

mb-platform-agent's HaloPSA contact sync needs every number HaloPSA holds for a customer, at three
levels: a contact, a client's main line and each site. Before this change the list tools returned a
fixed field set that dropped a contact's home and fax numbers and every site number.

- `halopsa_users_search`, `halopsa_users_get`, `halopsa_clients_list`, `halopsa_clients_get` and
  `halopsa_sites_list` add `phone_fields` (`{key: number}`): every phone-like key of the raw HaloPSA
  record that holds a value (keys containing `phone`, `mobile`, `fax`, a `tel` prefix, or `homenumber`;
  `*_id`, `*_name`, `*_type`, `*_ext`, `*_country` and similar are not numbers). Matching on the key
  shape means a field HaloPSA names differently is still returned. Existing flat keys are unchanged.
- The same tools add `country` (HaloPSA's own value, name or code) when the record has a country key,
  so the platform can read a number without a country code in the right country.
- `halopsa_sites_list` rows keep every key HaloPSA sent (`client_id`, `client_name`, ...) and gain the
  two additions above.
- `halopsa_users_search` gains the optional `include_details` (sends `includedetails=true`): a list
  call without it does not carry a contact's home and fax numbers.
- New tool `halopsa_phone_search(phone)` (read only, at most 3 requests): contacts whose any phone field
  matches, and, only when that is not exactly one contact, the clients (main line) and sites whose own
  number matches, each row with its `phone_fields`. A number matches when the digits are equal or the
  last ten digits are equal.
- No tool renamed, no parameter removed, no required parameter added.
- Not verified against a live HaloPSA tenant (none available to the build): the real key of a site's
  phone number, whether `/Site` and `/Client` search match phone fields, and whether `/Users` list
  with `includedetails=true` returns `homenumber` and `fax`. The platform tolerates a missing
  `phone_fields`, and the INT cases for this ticket read the real shapes first.
