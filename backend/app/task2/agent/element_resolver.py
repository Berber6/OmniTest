"""Progressive element resolution with fallback chain.

When an element description cannot be resolved by the primary eN reference
method, this module progressively tries alternative strategies:

1. eN reference scoring (snapshot_resolver) — fastest, most accurate
2. CSS/XPath selector from snapshot attributes
3. HTML rule matching (built-in dictionary + browser_evaluate verification)
4. VLM visual coordinate (Qwen3-VL screenshot analysis)
5. Keyboard fallback (only for form-submit scenarios)

Each method returns a ResolutionResult indicating the resolved value,
which method succeeded, and a confidence score.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from functools import wraps

from app.task2.agent.snapshot_resolver import resolve_ref_from_snapshot

logger = logging.getLogger(__name__)


# ── Resolution result ──────────────────────────────────────────────

@dataclass
class ResolutionResult:
    """Result of element resolution with method tracking."""
    value: str
    method: str     # "en_ref" | "css_selector" | "html_rule" | "vlm_coordinate" | "keyboard"
    confidence: float = 1.0


# ── Built-in HTML rule dictionary ──────────────────────────────────

# Maps Chinese description keywords to CSS selector candidates.
# Each entry is a list of selectors tried in order; the first one that
# matches a live element in the DOM wins.

HTML_RULES: dict[str, list[str]] = {
    # Authentication
    "邮箱": ["input[type=email]", "input[name*=email]", "input[placeholder*=email]", "input[name*=username]"],
    "电子邮件": ["input[type=email]", "input[name*=email]", "input[placeholder*=email]"],
    "密码": ["input[type=password]", "input[name*=password]", "input[placeholder*=password]"],
    "登录": ["button[type=submit]", "button[name*=login]", "input[type=submit]", "a[href*=login]"],
    "注册": ["button[name*=register]", "button[name*=signup]", "a[href*=register]", "a[href*=signup]"],
    "提交": ["button[type=submit]", "input[type=submit]", "button[name*=submit]"],
    "注销": ["button[name*=logout]", "a[href*=logout]", "button[class*=logout]"],
    "退出": ["button[name*=logout]", "a[href*=logout]", "button[class*=logout]"],
    # Board management
    "创建": ["button[class*=create]", "a[class*=create]", "button[name*=create]", "a[href*=create]"],
    "删除": ["button[class*=delete]", "button[name*=delete]", "a[class*=delete]", "a[href*=delete]"],
    "编辑": ["button[class*=edit]", "button[name*=edit]", "a[class*=edit]", "a[href*=edit]"],
    "保存": ["button[type=submit]", "button[name*=save]", "button[class*=save]"],
    "取消": ["button[name*=cancel]", "button[class*=cancel]", "a[class*=cancel]"],
    "导出": ["button[class*=export]", "a[href*=export]", "button[name*=export]"],
    "导入": ["button[class*=import]", "a[href*=import]", "button[name*=import]"],
    # Navigation
    "搜索": ["input[type=search]", "input[name*=search]", "input[placeholder*=search]"],
    "关闭": ["button[class*=close]", "button[name*=close]", "[aria-label*=close]"],
    "确认": ["button[class*=confirm]", "button[name*=confirm]", "button[type=submit]"],
    # Card operations
    "添加": ["button[class*=add]", "button[name*=add]", "a[class*=add]"],
    "移动": ["button[class*=move]", "button[name*=move]", "a[class*=move]"],
    "复制": ["button[class*=copy]", "button[name*=copy]"],
    # List operations
    "排序": ["button[class*=sort]", "select[name*=sort]"],
    "筛选": ["button[class*=filter]", "select[name*=filter]"],
    # Generic
    "菜单": ["button[class*=menu]", "[aria-label*=menu]"],
    "设置": ["button[class*=settings]", "a[href*=settings]", "[aria-label*=settings]"],
    "通知": ["button[class*=notification]", "a[href*=notification]", "[aria-label*=notification]"],
    "展开": ["button[class*=expand]", "[aria-label*=expand]", "button[aria-expanded=false]"],
    "折叠": ["button[class*=collapse]", "[aria-label*=collapse]", "button[aria-expanded=true]"],
    "选择": ["select", "button[class*=select]", "[role=listbox]"],
    "侧边栏": ["nav", "[class*=sidebar]", "[class*=side-bar]", "[class*=menu]"],
}

# Chinese keyword to English mapping for CSS construction from snapshot
_CSS_KEYWORD_MAP: dict[str, list[str]] = {
    "邮箱": ["email"],
    "密码": ["password"],
    "登录": ["login", "log in", "signin", "sign in"],
    "注册": ["register", "signup", "sign up"],
    "提交": ["submit"],
    "创建": ["create", "new", "add"],
    "删除": ["delete", "remove"],
    "编辑": ["edit", "modify"],
    "保存": ["save"],
    "取消": ["cancel"],
    "搜索": ["search"],
    "导出": ["export"],
    "导入": ["import"],
    "确认": ["confirm", "ok", "yes"],
    "关闭": ["close", "dismiss"],
    "菜单": ["menu"],
    "设置": ["settings", "options"],
    "通知": ["notification", "alert"],
    "展开": ["expand", "show", "more"],
    "折叠": ["collapse", "hide", "less"],
    "选择": ["select", "choose"],
    "添加": ["add", "new"],
    "移动": ["move", "drag"],
    "侧边栏": ["sidebar", "navigation", "nav"],
}


# ── Method 2: CSS selector from snapshot ────────────────────────────

def _parse_snapshot_roles(snapshot_text: str) -> list[dict]:
    """Extract role+name pairs from snapshot YAML for CSS construction."""
    elements = []
    in_yaml = False
    for line in snapshot_text.split("\n"):
        if "```yaml" in line:
            in_yaml = True
            continue
        if "```" in line and in_yaml:
            in_yaml = False
            continue
        if not in_yaml:
            continue

        # Pattern: - role "name" [ref=eN] or - role [ref=eN]
        m = re.match(r'^\s*-\s+(\w+)\s+"([^"]+)"\s+\[ref=(e\d+)\]', line)
        if m:
            elements.append({"role": m.group(1), "name": m.group(2), "ref": m.group(3)})
            continue
        m = re.match(r'^\s*-\s+(\w+)\s+\[ref=(e\d+)\]', line)
        if m:
            elements.append({"role": m.group(1), "name": "", "ref": m.group(2)})
    return elements


def construct_css_from_snapshot(snapshot_text: str, description: str) -> str | None:
    """Construct CSS selectors from snapshot role/name attributes.

    Args:
        snapshot_text: browser_snapshot YAML content
        description: Chinese/English element description

    Returns:
        Best matching CSS selector, or None.
    """
    elements = _parse_snapshot_roles(snapshot_text)
    if not elements:
        return None

    # Translate Chinese keywords to English for matching
    english_keywords: list[str] = []
    for cn, en_list in _CSS_KEYWORD_MAP.items():
        if cn in description.lower():
            english_keywords.extend(en_list)
    # Also add any English words from the description itself
    for word in description.split():
        if word.isascii() and len(word) > 2:
            english_keywords.append(word.lower())

    if not english_keywords:
        return None

    # Score each element and construct CSS selectors
    best_selector = None
    best_score = 0

    for elem in elements:
        role = elem["role"]
        name = elem["name"].lower()
        score = 0

        # Keyword matching on name
        for kw in english_keywords:
            if kw in name:
                score += 3

        # Role-role consistency bonus
        if score > 0:
            score += 2  # name matched, role is probably relevant

        if score <= best_score:
            continue

        # Construct CSS selector candidates
        selectors = []
        if name:
            # Role-based + name-based
            selectors.append(f'{role}[name*="{name}"]')
            selectors.append(f'[role={role}][name*="{name}"]')
            selectors.append(f'{role}:has-text("{name}")')

        if selectors and score > best_score:
            best_score = score
            best_selector = selectors[0]  # Use first (most specific)

    return best_selector


# ── Method 3: HTML rule matching ────────────────────────────────────

async def match_html_rules(description: str, mcp_client) -> str | None:
    """Match description against built-in HTML rule dictionary.

    Uses browser_evaluate to verify each candidate selector actually
    finds a live element in the current DOM.

    Args:
        description: Chinese element description
        mcp_client: MCPClient with playwright connection

    Returns:
        First verified CSS selector, or None.
    """
    # Find matching rules
    candidates: list[str] = []
    desc_lower = description.lower()
    for keyword, selectors in HTML_RULES.items():
        if keyword in desc_lower:
            candidates.extend(selectors)

    if not candidates:
        # Fallback: try English keywords from description
        for word in description.split():
            if word.isascii() and len(word) > 2:
                for keyword, selectors in HTML_RULES.items():
                    en_map = _CSS_KEYWORD_MAP.get(keyword, [])
                    if word.lower() in en_map:
                        candidates.extend(selectors)

    if not candidates:
        return None

    # Verify each candidate via browser_evaluate
    for selector in candidates:
        try:
            js_script = f"document.querySelector('{selector}') !== null"
            result = await mcp_client.call_tool_text(
                "playwright", "browser_evaluate", {"script": js_script}
            )
            # Check if result indicates element exists
            if result and "true" in result.lower():
                # Also verify the element is visible
                visible_script = f"""
                    const el = document.querySelector('{selector}');
                    el !== null && el.offsetParent !== null && el.offsetWidth > 0
                """
                visible_result = await mcp_client.call_tool_text(
                    "playwright", "browser_evaluate", {"script": visible_script}
                )
                if visible_result and "true" in visible_result.lower():
                    logger.info(f"HTML rule match: '{description}' → '{selector}' (verified visible)")
                    return selector
        except Exception as exc:
            logger.debug(f"HTML rule candidate '{selector}' verify failed: {exc}")
            continue

    return None


# ── Method 4: VLM visual coordinate ─────────────────────────────────

async def resolve_with_vlm(description: str, mcp_client) -> dict | None:
    """Use Qwen3-VL to find element coordinates from a screenshot.

    Args:
        description: Element description to find
        mcp_client: MCPClient with playwright connection

    Returns:
        Dict with {"x": int, "y": int} center coordinates, or None.
    """
    from app.llm.router import call_llm_with_vision

    try:
        # Take screenshot
        content_blocks = await mcp_client.call_tool("playwright", "browser_take_screenshot", {})
        screenshot_b64 = None
        for block in content_blocks:
            if hasattr(block, "data") and block.data:
                screenshot_b64 = block.data
                break
            if hasattr(block, "text") and block.text:
                # Sometimes screenshot is returned as text with base64
                if len(block.text) > 100:
                    screenshot_b64 = block.text

        if not screenshot_b64:
            logger.warning("VLM resolution: no screenshot obtained")
            return None

        # Construct VLM prompt
        vlm_prompt = (
            f"请在截图中找到 \"{description}\" 元素的位置。\n"
            f"返回JSON格式: {{\"x\": 中心x坐标, \"y\": 中心y坐标}}\n"
            f"坐标基于截图的像素位置。如果找不到该元素，返回 {{\"found\": false}}。"
        )

        vlm_system = (
            "你是网页UI分析助手。根据截图和描述，精确定位元素的像素坐标。"
            "只返回JSON，不要返回其他内容。"
        )

        response = await call_llm_with_vision(
            model_key="deepseek_v4_flash",
            prompt=vlm_prompt,
            image=screenshot_b64,
            system_prompt=vlm_system,
            pipeline_stage="vlm_element_resolve",
        )

        if not response:
            logger.warning("VLM resolution: empty response")
            return None

        # Parse coordinates from response
        # Try to extract JSON from response
        json_match = re.search(r'\{[^}]+\}', response)
        if json_match:
            try:
                coords = json.loads(json_match.group())
                if coords.get("found") is False:
                    logger.info(f"VLM resolution: element '{description}' not found in screenshot")
                    return None
                x = int(coords.get("x", 0))
                y = int(coords.get("y", 0))
                if x > 0 and y > 0:
                    logger.info(f"VLM resolution: '{description}' → coordinates ({x}, {y})")
                    return {"x": x, "y": y}
            except json.JSONDecodeError:
                pass

        logger.warning(f"VLM resolution: could not parse coordinates from response: {response[:100]}")
        return None

    except Exception as exc:
        logger.warning(f"VLM resolution failed: {exc}")
        return None


# ── Method 5: Keyboard fallback ────────────────────────────────────

def should_try_keyboard(description: str, tool_name: str) -> bool:
    """Determine if keyboard fallback is appropriate.

    Only applicable for form-submit scenarios where Enter can substitute
    for a click on submit/login buttons.
    """
    if tool_name != "browser_click":
        return False

    keyboard_keywords = ["登录", "提交", "确认", "保存", "注册", "login", "submit", "confirm", "save", "register"]
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in keyboard_keywords)


# ── Main entry point: progressive fallback ──────────────────────────

async def resolve_element_with_fallback(
    snapshot_text: str,
    description: str,
    mcp_client,
    ui_elements: list | None = None,
    tool_name: str = "browser_click",
) -> ResolutionResult | None:
    """Try progressive fallback chain to resolve an element description.

    Args:
        snapshot_text: browser_snapshot YAML content
        description: Chinese/English element description (e.g. "邮箱输入框")
        mcp_client: MCPClient instance for browser + memory access
        ui_elements: Optional UI element registry for eN scoring boost
        tool_name: The MCP tool being used (for keyboard appropriateness check)

    Returns:
        ResolutionResult with value, method, and confidence; or None if all methods fail.
    """
    # ── Method 1: eN reference (existing snapshot_resolver) ──
    ref = resolve_ref_from_snapshot(snapshot_text, description, ui_elements)
    if ref:
        logger.info(f"Element resolved via eN ref: '{description}' → '{ref}'")
        return ResolutionResult(value=ref, method="en_ref", confidence=0.9)

    # ── Method 2: CSS selector from snapshot ──
    css = construct_css_from_snapshot(snapshot_text, description)
    if css:
        # Verify selector finds an element via browser_evaluate
        try:
            verify_script = f"document.querySelector('{css}') !== null"
            result = await mcp_client.call_tool_text(
                "playwright", "browser_evaluate", {"script": verify_script}
            )
            if result and "true" in result.lower():
                logger.info(f"Element resolved via CSS: '{description}' → '{css}'")
                return ResolutionResult(value=css, method="css_selector", confidence=0.7)
        except Exception as exc:
            logger.debug(f"CSS selector '{css}' verification failed: {exc}")

    # ── Method 3: HTML rule matching ──
    rule_selector = await match_html_rules(description, mcp_client)
    if rule_selector:
        logger.info(f"Element resolved via HTML rule: '{description}' → '{rule_selector}'")
        return ResolutionResult(value=rule_selector, method="html_rule", confidence=0.6)

    # ── Method 4: VLM visual coordinate ──
    coords = await resolve_with_vlm(description, mcp_client)
    if coords:
        logger.info(f"Element resolved via VLM: '{description}' → ({coords['x']}, {coords['y']})")
        return ResolutionResult(
            value=json.dumps(coords), method="vlm_coordinate", confidence=0.5,
        )

    # ── Method 5: Keyboard fallback (only for form-submit) ──
    if should_try_keyboard(description, tool_name):
        logger.info(f"Element resolved via keyboard fallback: '{description}' → Enter key")
        return ResolutionResult(value="Enter", method="keyboard", confidence=0.3)

    logger.warning(f"All resolution methods failed for '{description}'")
    return None