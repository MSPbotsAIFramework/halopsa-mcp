# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Compact, size-capped JSON for tool results and the shared error envelope."""

import json
from typing import Any

MAX_CHARS = 20_000

ERROR_CODES = {
    "not_configured",
    "unauthorized",
    "not_found",
    "invalid_argument",
    "rate_limited",
    "upstream_error",
}


def compact(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)


def error(code: str, message: str, retryable: bool = False) -> str:
    assert code in ERROR_CODES, code
    return compact({"error": {"code": code, "message": message, "retryable": retryable}})


def dump(data: Any, max_chars: int = MAX_CHARS) -> str:
    """Serialize ``data``; if too large, shrink its ``items`` list and flag ``has_more``."""
    text = compact(data)
    if len(text) <= max_chars:
        return text

    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]
        lo, hi = 0, len(items)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(compact(_trimmed(data, items[:mid]))) <= max_chars:
                lo = mid
            else:
                hi = mid - 1
        return compact(_trimmed(data, items[:lo]))

    return compact(
        {
            "truncated": True,
            "note": f"Result is {len(text)} characters, above the {max_chars} limit. Narrow the request.",
            "preview": text[: max_chars // 2],
        }
    )


def _trimmed(data: dict, items: list) -> dict:
    out = dict(data)
    out["items"] = items
    out["count"] = len(items)
    out["truncated"] = True
    out["has_more"] = True
    out["note"] = "Result was cut to fit the size limit. Use a smaller page_size or narrower filters."
    return out
