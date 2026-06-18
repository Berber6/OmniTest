"""Target application configuration.

Loads app-specific settings from the database (settings store) or defaults.
This replaces hardcoded 4gaboards-specific logic in the planner prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class TargetAppConfig:
    """Configuration for the target web application being tested."""
    name: str = "4gaboards"
    base_url: str = "https://demo.4gaboards.com"
    login_url: str = "/login"
    login_email: str = ""
    login_password: str = ""
    post_login_actions: list[dict] = field(default_factory=list)
    # Example post_login_actions:
    # [{"tool": "browser_click", "args": {"target": "Show boards按钮"}, "description": "点击Show boards展开侧边栏"}]
    mandatory_login: bool = True

    @classmethod
    def from_settings(cls) -> "TargetAppConfig":
        """Load config from app settings.

        base_url is derived from settings.login_url so that any .env override
        of the login URL automatically propagates to navigation targets.
        """
        base_url = settings.login_url.replace("/login", "").rstrip("/")
        return cls(
            name="4gaboards",
            base_url=base_url,
            login_url="/login",
            login_email=settings.login_email,
            login_password=settings.login_password,
            post_login_actions=[
                {"tool": "browser_click", "args": {"target": "Show boards按钮"}, "description": "点击Show boards展开看板侧边栏"},
                {"tool": "browser_wait_for", "args": {"time": 2}, "description": "等待Board列表加载"},
                {"tool": "browser_snapshot", "args": {}, "description": "获取Board列表快照"},
            ],
            mandatory_login=True,
        )

    def login_url_full(self) -> str:
        return f"{self.base_url}{self.login_url}"

    def to_prompt_text(self) -> str:
        """Format config for injection into LLM prompts."""
        lines = [
            f"目标应用: {self.name}",
            f"基础URL: {self.base_url}",
            f"登录页: {self.login_url_full()}",
            f"登录凭据: 邮箱={self.login_email}, 密码={self.login_password}",
            f"登录后必做操作: {json.dumps(self.post_login_actions, ensure_ascii=False)}",
            f"必须先登录: {self.mandatory_login}",
        ]
        return "\n".join(lines)