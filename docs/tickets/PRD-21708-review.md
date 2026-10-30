# PRD-21708 · Code review

## Round 1 · 2026-10-30 · reviewed dev/PRD-21708 @ ca33a8d (base 765d437)

Verdict: approved

### Findings

1. [suggestion] docs/tickets/PRD-21708.md:192 — The Self-test table's Chinese-character-scan row claims "No output", but the row itself quotes the translated phrase's original Chinese text ("运行模型") to document what was changed, so a literal re-run of `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` on the current tree does report one hit — this very line. Confirmed independently: the grep produces exactly one match, `docs/tickets/PRD-21708.md:192`, nothing in `src/` or `tests/`. This is self-referential documentation about a translation, not untranslated product/code content, and does not affect runtime behavior, tool output, or AGENTS.md's "English only" rule for the tool surface. Fix (non-blocking): rephrase the row without quoting the original Chinese characters (e.g. "...a Chinese SOP section title, translated to 'Operating model'...") so the scan's own evidence claim is literally accurate.

### Verification performed

- `uv run pytest -q` (PATH needed `~/.local/bin` for `uv`): `127 passed, 1 warning` — matches the Self-test claim exactly (same pre-existing `StarletteDeprecationWarning`).
- `uv run ruff check .`: `All checks passed!` — matches.
- `uv run ruff format --check .`: `34 files already formatted` — matches (no unformatted files).
- `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .`: one hit, `docs/tickets/PRD-21708.md:192` (see finding 1 above); no hits in `src/` or `tests/`.
- `git log --format='%H %an <%ae> / committer %cn <%ce>' 765d437..ca33a8d`: all three commits authored and committed as `Dev01.MBAgent <dev01.mbagent@mspbots.ai>`.
- Read `src/halopsa_mcp/tools/tickets.py:261-307` (full `halopsa_tickets_create` handler) against the diff: the new `user_id: ContactId = None` parameter is validated with the existing `_require(client, f"/Users/{seg(user_id)}", ...)` guard (same shape as the pre-existing `client_id` check), added to `body` before the existing `v is not None` filter, so omission is byte-for-byte unchanged — confirms AC1/AC2/AC4 as designed.
- `README.md` is untouched by this diff (confirmed via `git diff --stat`), so the Connector-section byte-for-byte claim carries no risk here.
- `credentials.py` and all other tools are untouched (confirmed via `git diff --stat`): no credential-handling surface in this change.
- `seg()` (`_common.py:165`) rejects non-plain-integer values before interpolating into the URL path — reused as-is for `user_id`, no new injection surface.

### Scope and design conformance

- Change matches the tech design exactly: one new optional parameter, one `_require` guard reused, one body key, three tests (extend + 2 new). No scope creep, no unrelated files touched beyond the two test files, the one source file, and the two doc files the design called for.
- No renamed tool/parameter, no new required parameter, no use of the reserved `agent_id` name (`AGENTS.md:19-20`) — `user_id: ContactId = None` is additive and optional.
- No new dependency, no schema/DB change (this server is stateless and has none).
- AC1–AC5 each have a corresponding passing automated test; TC6 (live-tenant round-trip) is correctly recorded as `untested — needs a real vendor account`, which `mcp-track.md` §2.5 explicitly says does not block.
- No in-scope dead code, duplication, or stale env vars found or introduced; none claimed either (Tech design "Reuse & cleanup" says none found, and the diff bears that out — this touches one function and its direct tests only).

Status: frozen @ ca33a8d
