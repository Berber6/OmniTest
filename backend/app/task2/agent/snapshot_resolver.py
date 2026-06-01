"""从 Playwright MCP 快照文本中解析元素引用 (eN ref)。

Playwright MCP 的 browser_snapshot 返回包含 YAML 代码块的文本，
格式为：

### Page
- Page URL: ...
- Page Title: ...
### Snapshot
```yaml
- textbox [ref=e9]
- button "Login" [ref=e16]
- generic [ref=e5]: Email or username
```

每个交互元素带有 [ref=eN] 标记。本模块将人类可读的元素描述
（如"邮箱输入框"、"登录按钮")映射到快照中的实际 eN 引用。
"""

import re

# 中文关键词到英文的映射表，用于跨语言元素匹配
# 每个中文关键词可映射到多个英文候选词，以列表形式提供
KEYWORD_MAP = {
    "邮箱": ["email"],
    "电子邮件": ["email"],
    "密码": ["password"],
    "登录": ["login", "log in"],
    "注册": ["register", "sign up"],
    "提交": ["submit"],
    "按钮": ["button"],
    "输入框": ["textbox"],
    "搜索": ["search"],
    "链接": ["link"],
    "下拉": ["select"],
    "选择": ["select"],
    "复选框": ["checkbox"],
    "标题": ["heading"],
    "图片": ["image"],
    "看板": ["board", "kanban"],
    "视图": ["view"],
    "仪表盘": ["dashboard"],
    "侧边栏": ["sidebar"],
    "菜单": ["menu"],
    "卡片": ["card"],
    "列表": ["list"],
    "关闭": ["close"],
    "取消": ["cancel"],
    "确认": ["confirm"],
    "保存": ["save"],
    "删除": ["delete"],
    "编辑": ["edit"],
    "添加": ["add"],
    "新建": ["new"],
    "创建": ["create"],
    "用户名": ["username"],
    "展开": ["show", "hide"],  # 看板列表切换按钮可能显示 "Show boards" 或 "Hide boards"
    "折叠": ["hide"],
}

# 中文描述词到元素 role 的映射
CN_ROLE_MAP = {
    "输入框": "textbox",
    "按钮": "button",
    "下拉": "select",
    "链接": "link",
    "标题": "heading",
    "图片": "img",
    "菜单": "menu",
    "卡片": "card",
}


def _extract_yaml_block(snapshot_text: str) -> str:
    """从 Playwright MCP 快照中提取 YAML 代码块内容。

    快照格式可能有两种：
    1. 包裹格式：### Page ... ### Snapshot ```yaml ... ```
    2. 纯 YAML 格式：直接以 - 开头的行

    提取后去除缩进前缀，使每行从 - 开头，方便后续逐行解析。
    """
    # 尝试提取 ```yaml ... ``` 代码块
    yaml_match = re.search(r'```yaml\n(.*?)```', snapshot_text, re.DOTALL)
    if yaml_match:
        raw = yaml_match.group(1)
    else:
        # 如果没有代码块，可能是纯 YAML 格式
        lines = []
        for line in snapshot_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("  -"):
                lines.append(stripped)
        raw = "\n".join(lines) if lines else snapshot_text

    # 去除每行前的缩进空格，统一为 - 开头的格式，方便正则匹配
    normalized_lines = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped:  # 跳过空行
            normalized_lines.append(stripped)
    return "\n".join(normalized_lines)


def _parse_snapshot_elements(snapshot_text: str) -> list[dict]:
    """解析快照文本，提取所有带 [ref=eN] 的交互元素。

    返回元素列表，每个元素包含 role、name、ref、label。

    逐行解析规范化后的 YAML 文本，支持多种格式：
    - 带名称: - button "Login" [ref=e16]
    - 仅角色: - textbox [ref=e12]
    - 带标签文本: - generic [ref=e9]: Email or username
    - 带额外属性: - heading "Log in" [level=1] [ref=e6]

    还会利用上下文继承标签：如果 textbox 紧跟在带标签文本的 generic 之后，
    将 generic 的标签文本赋给 textbox 的 label 字段（如"Password" → 密码输入框）。
    """
    yaml_text = _extract_yaml_block(snapshot_text)
    elements = []

    for line in yaml_text.split("\n"):
        line = line.strip()
        if not line.startswith("-"):
            continue

        # 检查是否有 ref=eN
        ref_match = re.search(r'\[ref=(e\d+)\]', line)
        if not ref_match:
            continue
        ref = ref_match.group(1)

        # 如果该 ref 已存在，跳过
        if any(e["ref"] == ref for e in elements):
            continue

        # 提取角色（第一个单词）
        role_match = re.match(r'-\s+(\w+)', line)
        if not role_match:
            continue
        role = role_match.group(1)

        # 提取名称（"..." 引号内的文本）
        name = ""
        name_match = re.search(r'"([^"]+)"', line)
        if name_match:
            name = name_match.group(1)

        # 提取标签文本（ref=eN 后的冒号内容）
        label = ""
        # 在整行中找 [ref=eN]: 后面的文本
        label_match = re.search(r'\[ref=e\d+\]:\s*(.+)', line)
        if label_match:
            label_text = label_match.group(1).strip()
            # 如果冒号后是子元素行（以 - 开头），则不算标签
            if not label_text.startswith("-"):
                label = label_text

        elements.append({
            "role": role,
            "name": name,
            "ref": ref,
            "label": label,
        })

    # 利用上下文继承标签：如果 textbox 紧跟在带标签文本的 generic 之后，
    # 将 generic 的标签文本赋给 textbox 的 label 字段
    # 例如：- generic [ref=e11]: Password → textbox [ref=e13] 获得 label="Password"
    for i, elem in enumerate(elements):
        if elem["role"] == "textbox" and not elem["label"] and not elem["name"]:
            # 向前查找最近的带标签的 generic 元素
            for j in range(i - 1, -1, -1):
                prev = elements[j]
                if prev["label"] and prev["role"] in ("generic", "group"):
                    elem["label"] = prev["label"]
                    break

    return elements


def resolve_ref_from_snapshot(snapshot_text: str, description: str, ui_elements: list | None = None) -> str | None:
    """根据人类可读的元素描述，从快照中找到对应的 eN 引用。

    Args:
        snapshot_text: browser_snapshot 返回的原始文本
        description: 人类可读描述，如"邮箱输入框"或"登录按钮"
        ui_elements: Optional list of known UIElement dicts for rule-based boost

    Returns:
        匹配的 eN 引用字符串（如 "e12"），未找到则返回 None
    """
    if not snapshot_text or not description:
        return None

    # 如果描述已经是有效的 eN 引用，直接返回
    if re.match(r'^e\d+$', description.strip()):
        return description.strip()

    elements = _parse_snapshot_elements(snapshot_text)
    if not elements:
        return None

    # 从快照中提取页面品牌名（用于惩罚品牌/logo链接）
    # 页面标题通常是 "Page Title | Brand" 或 "Brand - Page" 格式
    _page_brand = ""
    for line in snapshot_text.split("\n"):
        if "Page Title:" in line:
            title = line.replace("- Page Title:", "").strip()
            # 提取品牌部分：从 "Dashboard - 4ga Boards" 得到 "4ga Boards"
            for sep in (" - ", " | ", " — "):
                if sep in title:
                    _page_brand = title.split(sep)[-1].strip()
                    break
            if not _page_brand:
                _page_brand = title
            break

    desc_lower = description.lower().strip()

    # 将中文关键词翻译为英文 — 先扫描所有匹配的关键词位置，按位置排序后逐段翻译
    positions = []
    for cn, en_list in KEYWORD_MAP.items():
        idx = 0
        while True:
            pos = desc_lower.find(cn, idx)
            if pos == -1:
                break
            positions.append((pos, cn, en_list))
            idx = pos + len(cn)

    positions.sort(key=lambda x: x[0])
    translated_words = []
    last_pos = 0
    for pos, cn, en_list in positions:
        segment = desc_lower[last_pos:pos]
        if segment.strip():
            # 段中可能还有未匹配的关键词，二次扫描
            remaining_words = segment.strip().split()
            for w in remaining_words:
                if w in CN_ROLE_MAP:
                    translated_words.append(CN_ROLE_MAP[w])
                else:
                    translated_words.append(w)
        # 添加所有候选翻译词
        for en in en_list:
            translated_words.append(en)
        last_pos = pos + len(cn)

    # 处理最后的剩余部分
    remaining = desc_lower[last_pos:]
    if remaining.strip():
        for w in remaining.strip().split():
            if w in CN_ROLE_MAP:
                translated_words.append(CN_ROLE_MAP[w])
            else:
                translated_words.append(w)

    # 为每个元素评分，选最佳匹配
    # 收集所有候选及其分数，然后在同分时用特异性决胜
    candidates = []

    # 提取翻译后的角色关键词（如 "textbox", "button"）
    role_words = set()
    for w in translated_words:
        if w in {"textbox", "button", "select", "link", "heading", "img", "menu", "card", "checkbox"}:
            role_words.add(w)

    for elem in elements:
        score = 0
        name_lower = elem["name"].lower()
        role_lower = elem["role"].lower()
        label_lower = elem["label"].lower() if elem["label"] else ""

        # 翻译后的关键词逐个匹配元素名称、标签和角色
        for word in translated_words:
            if word in name_lower:
                score += 4
            if word in label_lower:
                score += 3
            if word in role_lower:
                score += 2

        # 名称完全匹配加分
        if any(word in name_lower for word in translated_words):
            score += 2
        # 标签包含关键词加分
        if any(word in label_lower for word in translated_words):
            score += 1

        # 名称特异性加分：名称越长越具体，匹配越可信
        # 长名称比短名称更有可能是真正的目标元素
        if name_lower and any(word in name_lower for word in translated_words):
            # 按名称长度比例加分，而非固定阈值
            # 这样 "Learn 4ga Boards" (19 chars) 比 "4ga Boards" (11 chars) 得分更高
            name_bonus = min(len(name_lower) // 5, 4)  # 每5个字符1分，上限4分
            score += name_bonus

        # 角色一致性加分：描述中包含角色关键词时，元素角色匹配该关键词大幅加分
        if role_words:
            if role_lower in role_words:
                score += 5  # 角色匹配权重高，避免"密码输入框"匹配到按钮
                # 角色匹配但名称中没有非角色关键词 — 这是弱匹配，应扣分
                # 例如"登录按钮"不应匹配"Show boards"按钮（只有角色匹配，名称无关）
                if not any(word in name_lower for word in translated_words if word not in role_words):
                    score -= 4
            # 如果描述明确要求某个角色，但元素角色不匹配，扣分
            # 扣分力度更大以防止角色不匹配的元素胜过角色匹配的元素
            if role_lower not in role_words and role_lower in ("button", "img", "link"):
                score -= 5

        # 名称匹配比例加分：关键词匹配占名称的比例越高越好
        # 例如 "Board" 在 "4ga Boards" 中占比低，但在 "Learn 4ga Boards" 中占比也低
        # 但如果关键词匹配了名称的大部分内容，说明名称就是为此关键词而命名的
        if name_lower:
            matched_chars = sum(len(word) for word in translated_words if word in name_lower)
            ratio = matched_chars / max(len(name_lower), 1)
            if ratio > 0.5:
                score += 3  # 名称超过一半内容与关键词匹配，很可能是目标

        # 推销/品牌/社交链接惩罚：名称包含这些关键词的元素很可能是
        # 推销链接而非功能性导航链接，应大幅扣分
        _PROMO_WORDS = {"star", "github", "support", "feedback", "follow",
                        "share", "tweet", "like", "subscribe", "sponsor",
                        "donate", "github!", "twitter", "facebook", "linkedin"}
        if name_lower:
            for pw in _PROMO_WORDS:
                if pw in name_lower:
                    score -= 8  # 推销链接惩罚权重大
                    break

        # 品牌名称/logo 链接惩罚：如果元素名称等于或包含页面品牌名
        # （如 "4ga Boards"），则它很可能是 logo 链接而非功能链接
        # 从页面标题中提取品牌名，用于比较
        if name_lower and _page_brand:
            # 如果元素名称与品牌名完全相同或包含品牌名作为主成分
            brand_lower = _page_brand.lower()
            if name_lower == brand_lower or (brand_lower in name_lower and len(name_lower) <= len(brand_lower) + 5):
                score -= 5  # 品牌/logo 链接扣分

        candidates.append((score, elem))

    # UI element boost: if known UI elements are provided, boost candidates
    # that match known UI elements for higher confidence matching
    if ui_elements:
        boosted = []
        for s, elem in candidates:
            boost = 0
            name_lower_boost = elem["name"].lower()
            role_lower_boost = elem["role"].lower()
            for ui_elem in ui_elements:
                ui_label = ui_elem.get("label", "").lower()
                ui_desc = ui_elem.get("description", "").lower()
                ui_role = ui_elem.get("role", "").lower()
                if ui_label and name_lower_boost == ui_label:
                    boost += 3
                elif ui_desc and any(word in name_lower_boost for word in ui_desc.split()):
                    boost += 2
                elif ui_role and role_lower_boost == ui_role and ui_label:
                    boost += 1
            boosted.append((s + boost, elem))
        candidates = boosted

    # 按分数降序排序
    candidates.sort(key=lambda x: x[0], reverse=True)

    # 最低分数阈值：至少需要 2 分才算有效匹配
    if not candidates or candidates[0][0] < 2:
        return None

    best_score = candidates[0][0]
    best_match = candidates[0][1]

    # 同分决胜：多个候选分数相同时，优先选择名称更具体的元素
    # 避免品牌名/logo 等通用名称胜过实际的功能元素
    tied = [c for c in candidates if c[0] == best_score]
    if len(tied) > 1:
        # 决胜规则1：名称更长的更具体
        tied.sort(key=lambda x: len(x[1]["name"]), reverse=True)
        # 决胜规则2：如果有多个同长名称，优先 link 而非 button/img
        # （因为"链接"描述通常指向导航链接）
        if desc_lower and ("链接" in desc_lower or "link" in desc_lower):
            link_candidates = [c for c in tied if c[1]["role"] == "link"]
            if link_candidates:
                best_match = link_candidates[0][1]
            else:
                best_match = tied[0][1]
        else:
            best_match = tied[0][1]

    return best_match["ref"]