"""Token usage logging for every Claude call.

Each call logs one line like:
  tokens call=answer model=claude-sonnet-5-5 input=812 cache_read=1430 cache_write=0 output=240
so cost and cache hit rate can be tracked from the logs.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("carechat.tokens")


def usage_dict(usage: Any) -> dict[str, int]:
    """Pull the token counts out of an API usage object (missing fields count as 0)."""
    def get(name: str) -> int:
        value = getattr(usage, name, None) if usage is not None else None
        return int(value) if isinstance(value, int) else 0

    return {
        "input": get("input_tokens"),
        "cache_read": get("cache_read_input_tokens"),
        "cache_write": get("cache_creation_input_tokens"),
        "output": get("output_tokens"),
    }


def log_usage(call: str, model: str, usage: Any) -> dict[str, int]:
    counts = usage_dict(usage)
    from .metrics import metrics  # local import: metrics imports settings only

    metrics.tokens_used(call, model, counts)
    log.info(
        "tokens call=%s model=%s input=%d cache_read=%d cache_write=%d output=%d",
        call, model, counts["input"], counts["cache_read"], counts["cache_write"], counts["output"],
    )
    return counts
