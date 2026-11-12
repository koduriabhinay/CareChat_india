"""Shared Claude client."""

from functools import lru_cache

import anthropic

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@lru_cache(maxsize=1)
def get_client() -> anthropic.AsyncAnthropic:
    # Reads ANTHROPIC_API_KEY (or another configured credential) from the environment.
    return anthropic.AsyncAnthropic()
