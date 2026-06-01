"""Runtime configuration store backed by SQLite.

Distinguishes between dynamic settings (modifiable via API) and static
settings (read-only, sourced from env vars).  Secrets are masked when
returned through the API.
"""

import json
import logging
from typing import Any

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import AppSetting

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Setting definitions
# ---------------------------------------------------------------------------

# Dynamic settings that can be modified via the API
DYNAMIC_SETTINGS: dict[str, dict[str, Any]] = {
    "llm_model_generation": {
        "category": "llm",
        "is_secret": False,
        "description": "LiteLLM model for generation tasks (e.g. feature extraction, scenario generation)",
        "default": "openai/DeepSeek-V4-Flash",
    },
    "llm_model_reasoning": {
        "category": "llm",
        "is_secret": False,
        "description": "LiteLLM model for reasoning tasks (e.g. planning, reflection, verification)",
        "default": "openai/GLM-5.1",
    },
    "llm_model_vision": {
        "category": "llm",
        "is_secret": False,
        "description": "LiteLLM model for vision tasks (e.g. visual verification)",
        "default": "openai/Qwen3-VL-235B-A22B-Instruct",
    },
    "crawl_headless": {
        "category": "crawl",
        "is_secret": False,
        "description": "Run crawler in headless mode (no visible browser)",
        "default": "True",
    },
    "crawl_timeout": {
        "category": "crawl",
        "is_secret": False,
        "description": "Crawl timeout in seconds",
        "default": "60",
    },
    "max_retry_count": {
        "category": "execution",
        "is_secret": False,
        "description": "Maximum retry count for agent execution",
        "default": "3",
    },
    "login_url": {
        "category": "auth",
        "is_secret": False,
        "description": "Login URL for the target web application",
        "default": "https://demo.4gaboards.com/login",
    },
    "login_email": {
        "category": "auth",
        "is_secret": False,
        "description": "Login email for the target web application",
        "default": "z1491861920@gmail.com",
    },
    "login_password": {
        "category": "auth",
        "is_secret": True,
        "description": "Login password for the target web application",
        "default": "",
    },
    # Cost coefficient settings (per 1M tokens)
    "cost_per_1m_tokens.deepseek_v4_flash.prompt": {
        "category": "cost",
        "is_secret": False,
        "description": "Cost per 1M prompt tokens for deepseek_v4_flash model",
        "default": "0.14",
    },
    "cost_per_1m_tokens.deepseek_v4_flash.completion": {
        "category": "cost",
        "is_secret": False,
        "description": "Cost per 1M completion tokens for deepseek_v4_flash model",
        "default": "0.28",
    },
    "cost_per_1m_tokens.glm_5_1.prompt": {
        "category": "cost",
        "is_secret": False,
        "description": "Cost per 1M prompt tokens for glm_5_1 model",
        "default": "1.0",
    },
    "cost_per_1m_tokens.glm_5_1.completion": {
        "category": "cost",
        "is_secret": False,
        "description": "Cost per 1M completion tokens for glm_5_1 model",
        "default": "2.0",
    },
    "cost_per_1m_tokens.qwen3_vl.prompt": {
        "category": "cost",
        "is_secret": False,
        "description": "Cost per 1M prompt tokens for qwen3_vl model",
        "default": "2.0",
    },
    "cost_per_1m_tokens.qwen3_vl.completion": {
        "category": "cost",
        "is_secret": False,
        "description": "Cost per 1M completion tokens for qwen3_vl model",
        "default": "6.0",
    },
    "cost_currency": {
        "category": "cost",
        "is_secret": False,
        "description": "Currency for cost display (USD or CNY)",
        "default": "USD",
    },
    # Neo4j
    "neo4j_enabled": {
        "category": "neo4j",
        "is_secret": False,
        "description": "Enable Neo4j graph database integration",
        "default": "False",
    },
}

# Static settings that can only be read (env-only)
STATIC_SETTINGS: list[str] = [
    "llm_api_key",
    "neo4j_password",
    "cors_origins",
    "llm_api_base_url",
]


class ConfigStore:
    """Persistent configuration store using SQLite AppSetting table."""

    @staticmethod
    def _get_db():
        return SessionLocal()

    @staticmethod
    def ensure_defaults() -> None:
        """Populate DB with default values for all dynamic settings that don't exist.

        Also migrates old cost_per_1k_tokens keys to cost_per_1m_tokens
        by deleting the old keys and creating new ones with adjusted defaults.
        """
        db = SessionLocal()
        try:
            # Phase 1: Migrate old 1K keys → 1M keys (values multiplied by 1000)
            old_key_names = ["cost_per_1k_tokens.deepseek_v4_flash.prompt",
                             "cost_per_1k_tokens.deepseek_v4_flash.completion",
                             "cost_per_1k_tokens.glm_5_1.prompt",
                             "cost_per_1k_tokens.glm_5_1.completion",
                             "cost_per_1k_tokens.qwen3_vl.prompt",
                             "cost_per_1k_tokens.qwen3_vl.completion"]
            for old_key in old_key_names:
                old_setting = db.execute(select(AppSetting).where(AppSetting.key == old_key)).scalar_one_or_none()
                if old_setting:
                    new_value = str(float(old_setting.value) * 1000)
                    new_key = old_key.replace("cost_per_1k_tokens", "cost_per_1m_tokens")
                    db.delete(old_setting)
                    new_spec = DYNAMIC_SETTINGS.get(new_key)
                    if new_spec:
                        db.add(AppSetting(
                            key=new_key,
                            value=new_value,
                            category=new_spec["category"],
                            is_secret=new_spec["is_secret"],
                            description=new_spec["description"],
                        ))
                    logger.info(f"Migrated cost key: {old_key} → {new_key} (value {old_setting.value} → {new_value})")
            db.commit()  # Commit migration separately so the next phase sees the changes

            # Phase 2: Populate defaults for any missing dynamic settings
            for key, spec in DYNAMIC_SETTINGS.items():
                existing = db.execute(
                    select(AppSetting).where(AppSetting.key == key)
                ).scalar_one_or_none()
                if existing is None:
                    setting = AppSetting(
                        key=key,
                        value=spec["default"],
                        category=spec["category"],
                        is_secret=spec["is_secret"],
                        description=spec["description"],
                    )
                    db.add(setting)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_setting(key: str) -> str | None:
        """Get a setting value by key. Returns None if not found."""
        db = SessionLocal()
        try:
            setting = db.execute(
                select(AppSetting).where(AppSetting.key == key)
            ).scalar_one_or_none()
            if setting:
                return setting.value
            # Fall back to dynamic setting defaults
            if key in DYNAMIC_SETTINGS:
                return DYNAMIC_SETTINGS[key]["default"]
            return None
        finally:
            db.close()

    @staticmethod
    def set_setting(key: str, value: str) -> AppSetting:
        """Set a dynamic setting value. Raises ValueError for static keys."""
        if key in STATIC_SETTINGS or key.startswith("llm_api_key"):
            raise ValueError(f"Setting '{key}' is static (env-only) and cannot be modified via API")

        if key not in DYNAMIC_SETTINGS:
            raise ValueError(f"Unknown setting key: '{key}'")

        db = SessionLocal()
        try:
            setting = db.execute(
                select(AppSetting).where(AppSetting.key == key)
            ).scalar_one_or_none()
            if setting:
                setting.value = value
            else:
                spec = DYNAMIC_SETTINGS[key]
                setting = AppSetting(
                    key=key,
                    value=value,
                    category=spec["category"],
                    is_secret=spec["is_secret"],
                    description=spec["description"],
                )
                db.add(setting)
            db.commit()
            db.refresh(setting)
            return setting
        finally:
            db.close()

    @staticmethod
    def get_all_settings() -> list[dict]:
        """Return all settings (dynamic + static), masking secrets."""
        db = SessionLocal()
        try:
            # Ensure defaults exist
            ConfigStore.ensure_defaults()

            # Dynamic settings from DB
            rows = db.execute(select(AppSetting)).scalars().all()
            settings = []
            for row in rows:
                val = row.value
                if row.is_secret and val:
                    val = val[:2] + "****" + val[-2:] if len(val) > 6 else "****"
                settings.append({
                    "key": row.key,
                    "value": val,
                    "category": row.category,
                    "is_secret": row.is_secret,
                    "description": row.description,
                    "is_dynamic": True,
                })

            # Static settings from env/config (masked)
            from app.config import settings as app_settings
            static_values = {
                "llm_api_key": app_settings.get_api_key(),
                "neo4j_password": app_settings.neo4j_password,
                "cors_origins": json.dumps(app_settings.cors_origins),
                "llm_api_base_url": app_settings.llm_api_base_url,
            }
            for key in STATIC_SETTINGS:
                val = static_values.get(key, "")
                # Mask all static values (they are secrets by nature)
                if val and len(val) > 6:
                    val = val[:2] + "****" + val[-2:]
                elif val:
                    val = "****"
                is_secret = key in ("llm_api_key", "neo4j_password")
                settings.append({
                    "key": key,
                    "value": val,
                    "category": "static",
                    "is_secret": is_secret,
                    "description": f"Static setting (env-only): {key}",
                    "is_dynamic": False,
                })

            return settings
        finally:
            db.close()

    @staticmethod
    def get_cost_per_1m_tokens(model_key: str) -> dict[str, float]:
        """Get cost per 1M tokens for a model, reading from DB if customized."""
        prompt_key = f"cost_per_1m_tokens.{model_key}.prompt"
        completion_key = f"cost_per_1m_tokens.{model_key}.completion"

        prompt_cost = ConfigStore.get_setting(prompt_key)
        completion_cost = ConfigStore.get_setting(completion_key)

        return {
            "prompt": float(prompt_cost) if prompt_cost else 1.0,
            "completion": float(completion_cost) if completion_cost else 2.0,
        }

    @staticmethod
    def get_currency() -> str:
        """Get the configured currency for cost display."""
        return ConfigStore.get_setting("cost_currency") or "USD"

    @staticmethod
    def get_model_config() -> dict[str, str]:
        """Get current model assignments (from DB overrides or defaults)."""
        return {
            "generation": ConfigStore.get_setting("llm_model_generation") or DYNAMIC_SETTINGS["llm_model_generation"]["default"],
            "reasoning": ConfigStore.get_setting("llm_model_reasoning") or DYNAMIC_SETTINGS["llm_model_reasoning"]["default"],
            "vision": ConfigStore.get_setting("llm_model_vision") or DYNAMIC_SETTINGS["llm_model_vision"]["default"],
        }