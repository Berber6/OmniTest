"""Common LLM JSON response parser.

Handles the various formats LLMs return:
- Direct JSON
- JSON wrapped in markdown code blocks (```json ... ```)
- JSON embedded in free text
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def parse_llm_json(response: str) -> dict | None:
    """Parse an LLM response into a JSON dict.

    Attempts multiple strategies:
    1. Direct json.loads
    2. Extract from markdown code blocks (```json ... ```)
    3. Find first JSON object via regex

    Returns parsed dict or None if all strategies fail.
    """
    if not response:
        return None

    # Strategy 1: Direct parse
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: Markdown code block extraction
    match = re.match(r"```(?:json)?\s*\n(.*?)\n```", response.strip(), re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find first JSON object
    match = re.search(r"\{[^{}]*\}", response)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse LLM response as JSON: %s", response[:300])
    return None