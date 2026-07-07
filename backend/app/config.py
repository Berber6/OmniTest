"""Application configuration using pydantic-settings.

All settings are loaded from environment variables or a .env file.
Defaults are provided for development convenience.
"""

import os
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve .env file paths — search parent directories too
def _find_env_file() -> str:
    """Find .env file in current dir or parent directories."""
    candidates = [
        Path(".env"),            # backend/.env
        Path("../.env"),         # project root .env
        Path("../../.env"),      # deeper search
    ]
    for p in candidates:
        if p.resolve().exists():
            return str(p.resolve())
    return ".env"  # default, let pydantic-settings handle missing


class Settings(BaseSettings):
    """Central configuration for the omni_test backend."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM Configuration ---
    llm_api_base_url: str = "https://chatbox.isrc.ac.cn/api/v1"
    # Read from env vars, .env file, or fallback
    llm_api_key: str = ""

    # LiteLLM model mapping: role -> model identifier
    llm_model_generation: str = "openai/DeepSeek-V4-Flash"
    llm_model_reasoning: str = "openai/GLM-5.1"
    llm_model_vision: str = "openai/Qwen3-VL-235B-A22B-Instruct"

    # --- MCP Server Configuration ---
    mcp_servers: Dict[str, Dict] = {
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp"],
            "transport": "stdio",
        },
        "verify": {
            "command": "python",
            "args": ["-m", "app.task2.mcp_servers.verify_mcp"],
            "transport": "stdio",
        },
        "memory": {
            "command": "python",
            "args": ["-m", "app.task2.mcp_servers.memory_mcp"],
            "transport": "stdio",
        },
    }

    # --- Database Paths ---
    data_dir: Path = Path("./data")
    sqlite_path: Path = Path("./data/omni_test.db")
    chroma_path: Path = Path("./data/chroma_db")
    chroma_db_path: Path = Path("./data/chroma_db")

    # --- Crawl4ai Configuration ---
    crawl_headless: bool = True
    crawl_timeout: int = 60

    # --- Execution Configuration ---
    max_retry_count: int = 3
    screenshot_dir: Path = Path("./data/screenshots")

    # --- 登录凭据（4gaboards 演示站点）---
    login_url: str = "https://demo.4gaboards.com/login"
    login_email: str = "z1491861920@gmail.com"
    login_password: str = "Zzb.20021114"

    # --- ChromaDB / RAG Configuration ---
    chroma_collection_name: str = "web_features"
    embedding_model_name: str = "BAAI/bge-m3"
    # Max cosine distance for RAG retrieval. Raised from 0.50 to 0.70 because
    # cross-lingual (Chinese query → English docs) matches score lower.
    rag_max_distance: float = 0.70

    # --- CORS ---
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]

    # --- Neo4j Configuration (optional) ---
    neo4j_enabled: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "omnitest"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    def get_api_key(self) -> str:
        """Get the effective API key from env, .env file, or config."""
        return (
            os.environ.get("ISRC_API_KEY", "")
            or os.environ.get("LLM_API_KEY", "")
            or self.llm_api_key
        )

    def get_litellm_model(self, role: str) -> str:
        """Return the LiteLLM model identifier for a given role."""
        mapping = {
            "generation": self.llm_model_generation,
            "reasoning": self.llm_model_reasoning,
            "vision": self.llm_model_vision,
        }
        if role not in mapping:
            raise ValueError(f"Unknown LLM role: {role}. Choose from {list(mapping.keys())}")
        return mapping[role]

    def ensure_dirs(self) -> None:
        """Create all required directories on disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.chroma_db_path.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()