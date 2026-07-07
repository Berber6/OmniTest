"""Cost estimation for LLM token usage.

Reads per-model cost coefficients from ConfigStore (user-customizable).
Provides estimate_cost() for each token usage record.
Cost coefficients are per 1M (1,000,000) tokens.
"""

from functools import lru_cache

from app.db.config_store import ConfigStore


def estimate_cost(
    model_key: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float, str]:
    """Estimate cost for a single LLM call.

    Cost coefficients are per 1M tokens.
    Returns (cost_estimate, currency).
    """
    rates = ConfigStore.get_cost_per_1m_tokens(model_key)
    currency = ConfigStore.get_currency()

    prompt_cost = (prompt_tokens / 1_000_000) * rates["prompt"]
    completion_cost = (completion_tokens / 1_000_000) * rates["completion"]

    return (prompt_cost + completion_cost, currency)