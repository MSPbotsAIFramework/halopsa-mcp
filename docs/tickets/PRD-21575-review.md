# PRD-21575 · Code review

## Round 1 · 2026-10-30 · reviewed dev/PRD-21575 @ 5eeab8c (base main @ 4db11dc)

Status: frozen @ 5eeab8c

Verdict: approved

### Scope

`git diff 4db11dc...5eeab8c` on `MSPbotsAIFramework/halopsa-mcp`: one new read-only tool
`halopsa_tickets_list_actions` (`src/halopsa_mcp/tools/tickets.py`), its registration in
`tools/meta.py`, README tool table + behaviour note, baseline fixture entry, and 10 new tests
in `tests/test_handlers.py`. No other file outside `docs/` and `docs/changes/` touched.

### Findings

No must-fix findings.

1. [suggestion] `src/halopsa_mcp/tools/tickets.py:614` (`halopsa_tickets_list_actions` handler) — `mapped`
   maps every over-fetched row (`start+size+1` rows) through `_action(a, LIST_ACTIONS_FIELDS)` before
   `window()` slices to the requested page, so the one row beyond the page boundary is slimmed and then
   discarded. Harmless (bounded by `MAX_ACTIONS=100`, correctness unaffected — `window()` still slices
   `[start:start+size]` correctly, confirmed by `test_list_actions_pages_by_offset`), but slimming the
   extra row first and slicing second is one extra `pick()` call per request for no observable benefit.
   Not worth a round trip to fix.

### Independent verification (re-run on dev/PRD-21575 @ 5eeab8c, not just read from the Self-test section)

| Check | Command | Result |
|---|---|---|
| Unit tests | `uv run pytest -q` | `137 passed, 1 warning` — matches the `[DEV]` stub and Self-test claim exactly |
| Lint | `uv run ruff check src tests` | `All checks passed!` |
| Format | `uv run ruff format --check src tests` | `26 files already formatted` |
| Chinese-char scan | `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` (excluding the two pre-existing quoted-ticket-text hits already disclosed in the design doc) | zero hits in `src/`, `tests/` |
| README Connector section | `diff` against `~/.claude/skills/vendor-mcp-development/reference/readme-connector-section.md` | identical, byte for byte |

### Review against the MCP checklist (`legs/review.md` R3 + `mcp-track.md` §4.3)

- Credentials: no new credential code; the new tool reuses `run()`/`credentials.current()` exactly like
  every other tool (`test_list_actions_not_configured_without_credentials` confirms the same
  `not_configured` envelope). No per-request state leaks across calls.
- Tool name/params/return/errors match the tech design: `halopsa_tickets_list_actions(ticket_id, 11
  optional filters, limit, offset, full_response)`, structured `not_found` / `invalid_argument` /
  `not_configured` errors, standard `window()` list envelope — all as designed.
- Tests changed alongside the tool: 10 new tests (`tests/test_handlers.py`) cover every AC1–AC8/TC1–TC10
  judgement from the design's Test cases section, plus two dev-added tests (`full_response` passthrough,
  non-goal check that `halopsa_tickets_get`'s `include_actions` path is unchanged). None of the design's
  10 test-case judgements were narrowed or reworded.
- README Connector section and Chinese-character scan: both clean (above).
- Cross-repo headers/fields: not applicable — single repo, no new header, no cross-repo contract change
  (`release order: any`, correctly moot per the design's Rollout section).
- SOP §14 checklist: this is an incremental change to an already-compliant, already-registered connector
  (no container, credential-header, or lifespan changes); the applicable items (structured errors, empty
  result ≠ `not_found`, English-only, tests alongside tool/param changes) are satisfied as shown above.

### Design/AC conformance

Verified the diff against `docs/tickets/PRD-21575.md`'s Tech design and Data & API contract sections:
`LIST_ACTIONS_FIELDS` superset, `_fetch_actions()` extraction (reused by the pre-existing
`halopsa_tickets_get` call site with byte-identical request params — `test_tickets_get_with_actions`
passes unmodified), `_action()` widened with a `fields` parameter rather than a parallel function, and
the `window()`-based list envelope all match the chosen Option A exactly. `total_count` is sourced from
HaloPSA's own `record_count` and omitted when absent, matching the design's "Naming decision" paragraph.
No existing tool's signature or response shape changed (`tests/test_tools.py`'s backward-compatibility
suite passes with the baseline addition only).

### Reuse & cleanup (SKILL.md global constraint)

The in-scope extraction of `_fetch_actions()` removes the duplication this ticket would otherwise have
introduced (both `halopsa_tickets_get` and the new tool now share one over-fetch-and-slice
implementation). No new third-party dependency. No dead code, stale env var, or parameter-stacking
pattern found in the files this ticket touched.

### Conclusion

No must-fix findings. One suggestion noted above (not blocking). Proceeding to merge
`dev/PRD-21575` into `main`, INT publish, and the connector wiki check per `mcp-track.md` §4.4–4.5.
