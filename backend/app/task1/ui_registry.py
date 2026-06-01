"""UI Element Registry for constraining planner target descriptions.

Builds a registry of known interactive UI elements from crawled pages,
using a two-phase approach:
1. Text-based extraction (automatic, from markdown content + image alt text)
2. Dynamic extraction (optional, via Playwright accessibility tree)

The registry is used to:
- Constrain planner targets to known UI elements
- Boost snapshot_resolver scores for known elements
- Validate that planner-generated targets correspond to actual UI
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UIElement(BaseModel):
    """A known interactive UI element extracted from crawled pages."""

    page_url: str = Field(..., description="URL of the page containing this element")
    element_type: str = Field(..., description="button, link, input, select, etc.")
    label: str = Field(default="", description="Text content or aria-label")
    role: str = Field(default="", description="ARIA role")
    description: str = Field(default="", description="Chinese description derived from context")
    selector_hint: str = Field(default="", description="CSS selector hint for matching")
    source: str = Field(default="text", description="text (from markdown) or dynamic (from Playwright)")
    confidence: float = Field(default=0.5, description="Confidence score 0-1")


class UIElementRegistry:
    """Registry of known UI elements, persisted as JSON."""

    _elements: list[UIElement] = []
    _by_url: dict[str, list[UIElement]] = {}

    # ── Phase 1: Text-based extraction ──

    @classmethod
    def build_from_manifest(cls, manifest_path: str) -> list[UIElement]:
        """Phase 1: Extract UI elements from markdown content and image alt text."""
        path = Path(manifest_path)
        if not path.exists():
            logger.warning(f"Manifest not found at {manifest_path}")
            return []

        with open(path, "r", encoding="utf-8") as f:
            pages = json.load(f)

        elements = []
        for page in pages:
            page_url = page.get("url", "")
            content = page.get("content", "")
            images = page.get("images", [])
            page_elements = _extract_elements_from_markdown(page_url, content, images)
            elements.extend(page_elements)

        cls._elements = elements
        cls._by_url = {}
        for elem in elements:
            if elem.page_url not in cls._by_url:
                cls._by_url[elem.page_url] = []
            cls._by_url[elem.page_url].append(elem)

        logger.info(f"UIElementRegistry Phase 1: extracted {len(elements)} elements from {len(pages)} pages")
        return elements

    # ── Phase 2: Dynamic extraction (optional) ──

    @classmethod
    def build_from_accessibility_pages(cls, pages_data: list[dict]) -> list[UIElement]:
        """Phase 2: Extract UI elements from Playwright accessibility snapshots.

        pages_data: list of {url: str, snapshot_text: str} dicts.
        """
        elements = []
        for page_data in pages_data:
            page_url = page_data.get("url", "")
            snapshot = page_data.get("snapshot_text", "")
            page_elements = _extract_elements_from_snapshot(page_url, snapshot)
            elements.extend(page_elements)

        # Merge with existing text-based elements (dynamic overwrites text)
        existing_by_key = {}
        for elem in cls._elements:
            key = f"{elem.page_url}:{elem.label}:{elem.element_type}"
            existing_by_key[key] = elem

        for elem in elements:
            key = f"{elem.page_url}:{elem.label}:{elem.element_type}"
            existing_by_key[key] = elem  # Dynamic overwrites text

        cls._elements = list(existing_by_key.values())
        cls._by_url = {}
        for elem in cls._elements:
            if elem.page_url not in cls._by_url:
                cls._by_url[elem.page_url] = []
            cls._by_url[elem.page_url].append(elem)

        logger.info(f"UIElementRegistry Phase 2: merged {len(elements)} dynamic elements, total {len(cls._elements)}")
        return elements

    # ── Persistence ──

    @classmethod
    def save(cls, path: str) -> None:
        """Save registry to JSON file."""
        data = [elem.model_dump() for elem in cls._elements]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved UI registry ({len(cls._elements)} elements) to {path}")

    @classmethod
    def load(cls, path: str) -> list[UIElement]:
        """Load registry from JSON file."""
        p = Path(path)
        if not p.exists():
            logger.warning(f"UI registry not found at {path}")
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cls._elements = [UIElement(**d) for d in data]
        cls._by_url = {}
        for elem in cls._elements:
            if elem.page_url not in cls._by_url:
                cls._by_url[elem.page_url] = []
            cls._by_url[elem.page_url].append(elem)

        logger.info(f"Loaded UI registry ({len(cls._elements)} elements) from {path}")
        return cls._elements

    # ── Lookups ──

    @classmethod
    def get_elements_for_url(cls, url: str) -> list[UIElement]:
        """Get all known UI elements for a specific page URL."""
        return cls._by_url.get(url, [])

    @classmethod
    def get_all_elements(cls) -> list[UIElement]:
        """Get all registered UI elements."""
        return cls._elements

    @classmethod
    def format_for_prompt(cls, elements: list[UIElement]) -> str:
        """Format UI elements for inclusion in planner prompt."""
        if not elements:
            return "无可用的已知 UI 元素信息。"

        # Group by page URL
        by_page: dict[str, list[UIElement]] = {}
        for elem in elements:
            url_path = elem.page_url.split("/")[-1] or elem.page_url
            if url_path not in by_page:
                by_page[url_path] = []
            by_page[url_path].append(elem)

        lines = ["## 可用的 UI 元素（从文档中提取）"]
        for page_key, elems in by_page.items():
            lines.append(f"\n### 页面 {page_key}")
            for elem in elems:
                cn_desc = elem.description or elem.label
                lines.append(f"- {elem.element_type} \"{elem.label}\" ({cn_desc})")

        return "\n".join(lines)


# ── Extraction helpers ──

def _extract_elements_from_markdown(
    page_url: str,
    content: str,
    images: list[dict],
) -> list[UIElement]:
    """Extract interactive elements from markdown text and image metadata."""
    elements = []

    # 1. Extract links: [text](url)
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    for match in link_pattern.finditer(content):
        label = match.group(1)
        href = match.group(2)
        # Skip image links, navigation anchors, external links
        if href.startswith("#") or href.startswith("http") and "4gaboards.com/docs" not in href:
            continue
        if label and len(label) > 2 and not label.startswith("!"):
            cn_desc = _translate_label(label)
            elements.append(UIElement(
                page_url=page_url,
                element_type="link",
                label=label,
                role="link",
                description=cn_desc,
                selector_hint=f"a:has-text('{label}')",
                source="text",
                confidence=0.6,
            ))

    # 2. Extract button-like mentions from context
    # Pattern: "button", "点击", "click", "submit" near quoted text
    button_keywords = ["button", "按钮", "点击", "click", "submit", "提交", "新建", "创建", "删除", "保存", "取消", "确认"]
    for kw in button_keywords:
        # Find text near button keywords
        pattern = re.compile(r'["\']([^"\']+)["\'].*?' + kw + '|' + kw + r'.*?["\']([^"\']+)["\']', re.IGNORECASE)
        for match in pattern.finditer(content):
            label = match.group(1) or match.group(2)
            if label and len(label) > 2 and not any(e.label == label for e in elements):
                cn_desc = _translate_label(label)
                elements.append(UIElement(
                    page_url=page_url,
                    element_type="button",
                    label=label,
                    role="button",
                    description=cn_desc,
                    selector_hint=f"button:has-text('{label}')",
                    source="text",
                    confidence=0.5,
                ))

    # 3. Extract input-like mentions from context
    input_keywords = ["input", "输入框", "textbox", "field", "邮箱", "密码", "username", "email"]
    for kw in input_keywords:
        pattern = re.compile(kw, re.IGNORECASE)
        if pattern.search(content):
            cn_desc = _translate_keyword(kw)
            elements.append(UIElement(
                page_url=page_url,
                element_type="input",
                label=kw,
                role="textbox",
                description=cn_desc,
                selector_hint=f"input[placeholder*='{kw}']",
                source="text",
                confidence=0.4,
            ))

    # 4. Extract from image alt text (describes UI screens)
    for img in images:
        alt = img.get("alt", "")
        if alt and len(alt) > 5:
            # Alt text like "Login screen" or "Board creation form" describes whole screens
            cn_desc = _translate_label(alt)
            elements.append(UIElement(
                page_url=page_url,
                element_type="screen",
                label=alt,
                role="screen",
                description=cn_desc,
                selector_hint="",
                source="text",
                confidence=0.7,  # Image alt text is high-confidence for screen descriptions
            ))

    return elements


def _extract_elements_from_snapshot(
    page_url: str,
    snapshot_text: str,
) -> list[UIElement]:
    """Extract interactive elements from Playwright accessibility snapshot YAML."""
    elements = []
    yaml_match = re.search(r'```yaml\n(.*?)```', snapshot_text, re.DOTALL)
    if not yaml_match:
        return elements

    yaml_text = yaml_match.group(1)
    interactive_roles = {"button", "link", "textbox", "select", "checkbox", "searchbox", "combobox"}

    for line in yaml_text.split("\n"):
        line = line.strip()
        if not line.startswith("-"):
            continue

        ref_match = re.search(r'\[ref=(e\d+)\]', line)
        if not ref_match:
            continue

        role_match = re.match(r'-\s+(\w+)', line)
        if not role_match:
            continue
        role = role_match.group(1)

        name_match = re.search(r'"([^"]+)"', line)
        name = name_match.group(1) if name_match else ""

        if role in interactive_roles and name:
            cn_desc = _translate_label(name)
            elements.append(UIElement(
                page_url=page_url,
                element_type=role,
                label=name,
                role=role,
                description=cn_desc,
                selector_hint=f"[ref={ref_match.group(1)}]",
                source="dynamic",
                confidence=0.9,
            ))

    return elements


# ── Translation helpers ──

_KEYWORD_MAP_CN = {
    "login": "登录",
    "log in": "登录",
    "register": "注册",
    "sign up": "注册",
    "submit": "提交",
    "button": "按钮",
    "email": "邮箱",
    "password": "密码",
    "search": "搜索",
    "board": "看板",
    "kanban": "看板",
    "create": "创建",
    "new": "新建",
    "delete": "删除",
    "edit": "编辑",
    "save": "保存",
    "cancel": "取消",
    "close": "关闭",
    "confirm": "确认",
    "add": "添加",
    "view": "视图",
    "dashboard": "仪表盘",
    "settings": "设置",
    "project": "项目",
    "card": "卡片",
    "list": "列表",
    "menu": "菜单",
    "sidebar": "侧边栏",
    "screen": "界面",
    "form": "表单",
    "input": "输入框",
    "select": "下拉选择",
    "checkbox": "复选框",
    "notification": "通知",
    "account": "账户",
    "profile": "个人资料",
    "import": "导入",
    "export": "导出",
    "shortcuts": "快捷键",
}

def _translate_label(label: str) -> str:
    """Translate English label to Chinese description."""
    label_lower = label.lower()
    for en, cn in _KEYWORD_MAP_CN.items():
        if en in label_lower:
            # Replace English keywords with Chinese
            return cn + label.replace(en, "").strip()
    return label  # Keep original if no translation found


def _translate_keyword(keyword: str) -> str:
    """Translate a keyword to Chinese."""
    return _KEYWORD_MAP_CN.get(keyword.lower(), keyword)