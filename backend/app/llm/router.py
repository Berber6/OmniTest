"""LiteLLM unified routing for domestic LLM models.

Uses the OpenAI-compatible API at chatbox.isrc.ac.cn with LiteLLM
as the routing layer. Falls back to httpx transport when aiohttp
has connectivity issues (common in proxy-restricted environments).
"""

import os
import asyncio
import logging
from typing import Any, Optional

import litellm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
# Resolve API key: ISRC_API_KEY env > LLM_API_KEY env > .env file > config
def _resolve_api_key() -> str:
    key = os.environ.get("ISRC_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
    if key:
        return key
    # Try loading from settings (which reads .env file)
    try:
        from app.config import settings
        return settings.get_api_key()
    except Exception:
        pass
    return ""

def _resolve_api_base() -> str:
    base = os.environ.get("LLM_API_BASE", "")
    if base:
        return base
    try:
        from app.config import settings
        return settings.llm_api_base_url
    except Exception:
        pass
    return "https://chatbox.isrc.ac.cn/api/v1"

API_KEY = _resolve_api_key()
API_BASE_URL = _resolve_api_base()

MODEL_MAP = {
    "deepseek_v4_flash": {
        "model": "openai/DeepSeek-V4-Flash",
        "api_base": API_BASE_URL,
        "api_key": API_KEY,
    },
    "glm_5_1": {
        "model": "openai/GLM-5.1",
        "api_base": API_BASE_URL,
        "api_key": API_KEY,
    },
    "qwen3_vl": {
        "model": "openai/Qwen3-VL-235B-A22B-Instruct",
        "api_base": API_BASE_URL,
        "api_key": API_KEY,
    },
}

# Fallback chains: if the primary model fails, try alternatives in order.
FALLBACK_MAP = {
    "deepseek_v4_flash": ["glm_5_1"],
    "glm_5_1": ["deepseek_v4_flash"],
    "qwen3_vl": ["glm_5_1"],
}

MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds


class LLMRouterError(Exception):
    """Raised when all retries and fallbacks fail."""


def _get_effective_api_key() -> str:
    """Get the effective API key, re-resolving at call time (not just module load)."""
    key = os.environ.get("ISRC_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
    if key:
        return key
    try:
        from app.config import settings
        return settings.get_api_key()
    except Exception:
        pass
    return API_KEY


async def call_llm(
    model_key: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    pipeline_stage: str = "unknown",
    **kwargs: Any,
) -> str:
    """Call an LLM model via LiteLLM with retry and fallback support.

    Args:
        model_key: Key in MODEL_MAP (e.g. "deepseek_v4_flash").
        prompt: User prompt text.
        system_prompt: Optional system prompt.
        pipeline_stage: Pipeline stage for token tracking (e.g. "extract", "generate", "plan").
        **kwargs: Additional LiteLLM kwargs (temperature, max_tokens, etc.).
    """
    effective_api_key = _get_effective_api_key()
    if not effective_api_key:
        raise LLMRouterError(
            "No API key configured. Set ISRC_API_KEY or LLM_API_KEY environment variable, "
            "or add LLM_API_KEY to .env file."
        )

    model_keys = [model_key] + FALLBACK_MAP.get(model_key, [])

    for mk in model_keys:
        config = MODEL_MAP.get(mk)
        if config is None:
            logger.warning(f"Unknown model key '{mk}', skipping fallback.")
            continue

        result = await _call_with_retries(
            model=config["model"],
            api_base=config["api_base"],
            api_key=effective_api_key,
            prompt=prompt,
            system_prompt=system_prompt,
            pipeline_stage=pipeline_stage,
            model_key=mk,  # pass through for token tracking
            **kwargs,
        )
        if result is not None:
            return result

        logger.warning(f"Model '{mk}' failed after all retries, trying fallback.")

    raise LLMRouterError(
        f"All models exhausted for model_key='{model_key}'. "
        f"Attempted: {model_keys}"
    )


async def _call_with_retries(
    model: str,
    api_base: str,
    api_key: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    pipeline_stage: str = "unknown",
    model_key: str = "",
    **kwargs: Any,
) -> Optional[str]:
    """Call LiteLLM with exponential backoff retries.

    Uses httpx transport instead of aiohttp to avoid proxy/SSL issues
    in restricted network environments.

    Returns None if all retries fail (so fallback can be attempted).
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Remove non-LiteLLM kwargs before passing
    litellm_kwargs = {k: v for k, v in kwargs.items()
                      if k not in ("system_prompt", "response_format", "pipeline_stage", "model_key")}

    # Disable aiohttp transport to use httpx (more reliable in this environment)
    litellm.disable_aiohttp_transport = True

    for attempt in range(MAX_RETRIES):
        backoff = INITIAL_BACKOFF * (2 ** attempt)
        if attempt > 0:
            logger.info(f"Retry {attempt}/{MAX_RETRIES}, backoff={backoff}s")
            await asyncio.sleep(backoff)

        try:
            litellm.drop_params = True
            call_start = asyncio.get_event_loop().time()
            # 使用同步版本在线程中运行，避免与 anyio cancel scope 冲突
            # litellm.acompletion 在 anyio 环境中会产生 CancelledError
            response = await asyncio.to_thread(
                litellm.completion,
                model=model,
                messages=messages,
                api_base=api_base,
                api_key=api_key,
                **litellm_kwargs,
            )
            call_duration = asyncio.get_event_loop().time() - call_start
            # litellm returns a ModelResponse; extract text content
            content = response.choices[0].message.content
            if content:
                # Capture token usage for tracking
                if hasattr(response, 'usage') and response.usage and model_key:
                    try:
                        from app.llm.token_tracker import record_token_usage
                        record_token_usage(
                            model_key=model_key,
                            model_name=model,
                            prompt_tokens=response.usage.prompt_tokens or 0,
                            completion_tokens=response.usage.completion_tokens or 0,
                            total_tokens=response.usage.total_tokens or 0,
                            pipeline_stage=pipeline_stage,
                            duration_seconds=call_duration,
                        )
                    except Exception as track_exc:
                        logger.warning(f"Token tracking failed: {track_exc}")
                return content.strip()
            logger.warning(f"Empty response content on attempt {attempt}")
        except Exception as exc:
            logger.error(f"LLM call failed (attempt {attempt}): {exc}")

    return None


async def call_llm_with_vision(
    model_key: str,
    prompt: str,
    image: str,
    system_prompt: Optional[str] = None,
    pipeline_stage: str = "unknown",
    **kwargs: Any,
) -> str:
    """Call a vision-capable LLM with an image input.

    Args:
        model_key: Key in MODEL_MAP (e.g. "qwen3_vl").
        prompt: User prompt text.
        image: Image URL or base64 string.
        system_prompt: Optional system prompt.
        pipeline_stage: Pipeline stage for token tracking (e.g. "verify_visual").
        **kwargs: Additional LiteLLM kwargs.
    """
    effective_api_key = _get_effective_api_key()
    if not effective_api_key:
        raise LLMRouterError(
            "No API key configured. Set ISRC_API_KEY or LLM_API_KEY environment variable, "
            "or add LLM_API_KEY to .env file."
        )

    # Build multimodal message content
    image_content: dict
    if image.startswith("http://") or image.startswith("https://"):
        image_content = {"type": "image_url", "image_url": {"url": image}}
    else:
        # Assume base64; prefix with data URI if not already present
        b64 = image if image.startswith("data:") else f"data:image/png;base64,{image}"
        image_content = {"type": "image_url", "image_url": {"url": b64}}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            image_content,
        ],
    })

    model_keys = [model_key] + FALLBACK_MAP.get(model_key, [])

    for mk in model_keys:
        config = MODEL_MAP.get(mk)
        if config is None:
            logger.warning(f"Unknown model key '{mk}', skipping fallback.")
            continue

        litellm_kwargs = {k: v for k, v in kwargs.items() if k not in ("system_prompt", "pipeline_stage")}
        result = await _call_with_retries_vision(
            model=config["model"],
            api_base=config["api_base"],
            api_key=effective_api_key,
            messages=messages,
            pipeline_stage=pipeline_stage,
            model_key=mk,
            **litellm_kwargs,
        )
        if result is not None:
            return result

        logger.warning(f"Vision model '{mk}' failed after all retries, trying fallback.")

    raise LLMRouterError(
        f"All vision models exhausted for model_key='{model_key}'. "
        f"Attempted: {model_keys}"
    )


async def _call_with_retries_vision(
    model: str,
    api_base: str,
    api_key: str,
    messages: list[dict],
    pipeline_stage: str = "unknown",
    model_key: str = "",
    **kwargs: Any,
) -> Optional[str]:
    """Call LiteLLM with vision messages and exponential backoff retries.

    Uses httpx transport for reliability."""
    litellm.disable_aiohttp_transport = True
    litellm_kwargs = {k: v for k, v in kwargs.items()
                      if k not in ("pipeline_stage", "model_key")}

    for attempt in range(MAX_RETRIES):
        backoff = INITIAL_BACKOFF * (2 ** attempt)
        if attempt > 0:
            logger.info(f"Vision retry {attempt}/{MAX_RETRIES}, backoff={backoff}s")
            await asyncio.sleep(backoff)

        try:
            litellm.drop_params = True
            call_start = asyncio.get_event_loop().time()
            # 使用同步版本在线程中运行，避免 anyio cancel scope 冲突
            response = await asyncio.to_thread(
                litellm.completion,
                model=model,
                messages=messages,
                api_base=api_base,
                api_key=api_key,
                **litellm_kwargs,
            )
            call_duration = asyncio.get_event_loop().time() - call_start
            content = response.choices[0].message.content
            if content:
                # Capture token usage for tracking
                if hasattr(response, 'usage') and response.usage and model_key:
                    try:
                        from app.llm.token_tracker import record_token_usage
                        record_token_usage(
                            model_key=model_key,
                            model_name=model,
                            prompt_tokens=response.usage.prompt_tokens or 0,
                            completion_tokens=response.usage.completion_tokens or 0,
                            total_tokens=response.usage.total_tokens or 0,
                            pipeline_stage=pipeline_stage,
                            duration_seconds=call_duration,
                        )
                    except Exception as track_exc:
                        logger.warning(f"Token tracking failed: {track_exc}")
                return content.strip()
            logger.warning(f"Empty vision response content on attempt {attempt}")
        except Exception as exc:
            logger.error(f"Vision LLM call failed (attempt {attempt}): {exc}")

    return None