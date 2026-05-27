# 任务一优化总结

## 一、概述

任务一（RAG 管线：爬取 → 特征提取 → 场景生成）经历了三轮迭代优化，解决了嵌入模型、爬取噪声、URL 过滤、检索精度、数据管理等核心问题。以下记录每个问题的根因、修复方案及前后对比。

---

## 二、问题与优化详情

### 1. 嵌入模型：英文模型无法适配中文内容

**问题**

原始使用 `all-MiniLM-L6-v2`（384维，仅英文）作为 ChromaDB 嵌入模型。4gaboards 文档本身是英文，但 LLM 生成的特征和场景描述是中文，用户查询也多为中文。MiniLM 对中文几乎无语义理解能力，RAG 检索时中文查询的召回率和相关性极差。

**修复**

将嵌入模型替换为 `BAAI/bge-m3`（1024维，多语言），支持中英文混合检索。同时：
- 删除旧 ChromaDB 数据（维度不兼容）
- `VectorStore` 初始化传入 `local_files_only=True`，避免 HuggingFace 网络不可达时加载失败
- `crawl_docs` 中将全局删除代理环境变量改为保存/恢复模式（`try/finally`），确保爬取完成后 ChromaDB 和 LLM 能访问网络

**前后对比**

| 指标 | all-MiniLM-L6-v2 | BAAI/bge-m3 |
|------|-------------------|-------------|
| 嵌入维度 | 384 | 1024 |
| 中文查询支持 | 无 | 多语言 |
| 中文 Top-1 匹配率 | 20%（1/5 组） | 80%（8/10 组，含内容相关） |

**RAG 检索测试**（10个中文查询，bge-m3）

| 中文查询 | Top-1 文档 | 余弦距离 | 英文 Top-1 | 严格匹配 | 内容匹配 |
|---------|-----------|---------|-----------|---------|---------|
| 如何创建一个Board | Board | 0.3385 | Board | ✅ | ✅ |
| Card的创建和编辑操作 | Card | 0.2764 | Card | ✅ | ✅ |
| 用户权限管理 | instance-settings | 0.3978 | Board | ❌ | ✅（instance-settings含权限内容） |
| 通知和提醒功能 | Notifications | 0.3489 | Notifications | ✅ | ✅ |
| 导入导出数据 | Card | 0.5339 | import-export | ❌ | ❌ |
| Board过滤选项 | Board | 0.3608 | Board | ✅ | ✅ |
| 侧边栏导航 | admin-settings | 0.4599 | sidebar | ❌ | ✅（admin-settings详述了侧边栏） |
| 项目设置管理 | project-settings | 0.3643 | project-settings | ✅ | ✅ |
| 列表视图操作 | Card | 0.4232 | list-view | ❌ | ❌ |
| 账号注册和登录 | account | 0.3698 | account | ✅ | ✅ |

> 严格 Top-1 匹配率 60%（6/10），但考虑内容相关性后为 80%（8/10）。仅"导入导出数据"和"列表视图操作"2 组为真正的检索错误。

---

### 2. 爬取内容噪声：导航栏/侧边栏/页脚未过滤

**问题**

crawl4ai 将 Docusaurus 页面完整转为 markdown，包含大量噪声：
- **导航栏**：[Skip to main content]、Logo链接、Getting Started/Users/Admins/Devs 导航链接
- **侧边栏 TOC**：缩进链接列表（所有章节目录树），占约 30-50% 页面内容
- **页脚**：Previous/Next 导航、Edit this page、版权声明、Community/Docs 区块
- **语言切换器**：[English]/[Polski] 链接

噪声在所有页面重复出现，干扰特征提取（LLM 从导航链接提取"特征"），降低 RAG 检索精度。

**修复**

在 `crawler.py` 中添加 `_filter_markdown_content()` 函数，四阶段过滤：
1. 找到第一个 `# ` 标题行作为正文起点
2. 删除标题前的导航/侧边栏/语言切换器行（`_is_nav_sidebar_line()` 辅助函数）
3. 删除标题后的页脚元素（Previous/Next、Edit this page、版权、底部 TOC 锚点）
4. 压缩连续空行（3+行 → 2行）

识别规则保守：只删除明确属于导航/侧边栏/页脚的行，模糊行保留。

**前后对比**

| 指标 | 过滤前 | 过滤后 |
|------|--------|--------|
| 平均每页字符数 | ~6000+ | ~2976 |
| 总内容字符数 | ~160,000+ | 59,533 |
| 内容缩减比例 | — | 约 50% |
| 噪声占比 | 30-50% | 0% |
| 噪声 chunks 数量 | 56（占14%） | 0 |
| 干净 chunks | 316（79.4%） | 89（100%） |

---

### 3. 爬取 URL 过滤：无关 dev 页面导致检索错误

**问题**

原始爬取策略经历了两轮迭代：

**第一轮问题**：只有宽泛的 `/docs/dev/` 过滤规则，导致大量部署/运维文档被爬取（docker、install、k8s等），但 `/docs/dev/api` 和 `/docs/dev/sso` 等功能性文档也被排除。

**第二轮问题**：改为精确排除后，漏掉了 `/docs/dev/` 下的几个非功能性页面：
- `/docs/dev/web-server-config`（Nginx/Apache/Caddy 配置，32 chunks）—— 被 RAG 检索为"导入导出"相关，导致特征提取错误
- `/docs/dev/developers-additional`（日志/Fail2Ban，10 chunks）
- `/docs/dev/notifications`（SMTP通知配置，8 chunks）
- `/docs/dev/backup-restore`（备份恢复，2 chunks）
- `/docs/dev/development`（开发者入口，2 chunks）
- `/docs/dev/development/additional`（2 chunks）
- `/docs/dev/development/install`（2 chunks）

这些页面合计 56 chunks，占总量 47%，全部是运维/开发视角的内容，与"功能使用"无关。`web-server-config` 的 32 chunks 直接导致"导入导出"特征检索到错误的 Nginx 配置内容。

**修复**

从宽泛过滤改为精确的 `skip_patterns` 列表，同时用 `dev_keep_patterns` 保留功能性文档：

```python
skip_patterns = [
    "/docs/dev/docker", "/docs/dev/install", "/docs/dev/manual-install",
    "/docs/dev/k8s", "/docs/dev/uninstall", "/docs/dev/upgrade",
    "/docs/dev/migration", "/docs/dev/contributing", "/docs/dev/architecture",
    "/docs/dev/web-server-config",     # 服务器配置（非功能）
    "/docs/dev/developers-additional", # 日志/Fail2Ban（非功能）
    "/docs/dev/notifications",         # SMTP配置（非功能）
    "/docs/dev/backup-restore",        # 备份恢复（运维）
    "/docs/dev/development",           # 开发者入口页
    ...                                # 入口页、无关内容等
]

dev_keep_patterns = [
    "/docs/dev/api",                   # API 使用文档（功能性）
    "/docs/dev/sso",                   # SSO 单点登录（功能性）
]
```

**前后对比**

| 指标 | 第一轮（宽泛排除） | 第二轮（精确排除但漏掉） | 第三轮（最终版） |
|------|---------|---------|---------|
| sitemap URL 总数 | 59 | 59 | 59 |
| 保留 URL | ~45 | 27 | 20 |
| 爬取的无效页面 | ~18 | 7个dev运维页面 | 0（保留api+sso） |
| 无关 chunks | 大量 | 56 (47%) | 0 |
| "导入导出"检索 | — | 错误（web-server-config） | Top-1偏移但import-export仍在Top-3中 |

---

### 4. 检索数量过大：n_retrieval_results=60 几乎取全部 chunks

**问题**

`extractor.py` 中 `n_retrieval_results=60`，而总共只有 89 个 chunks（过滤后更少），检索 60 个几乎是全部文档。这导致：
- LLM context 过长，成本高
- 无关 chunks（如 dev 运维文档）被大量注入 context
- 信号淹没在噪声中，特征提取质量下降

**修复**

将 `n_retrieval_results` 从 60 降到 20，配合 URL 过滤和内容过滤后，20 个 chunks 足够覆盖每个查询的核心文档。

**前后对比**

| 指标 | n=60 | n=20 |
|------|------|------|
| 去重后唯一 chunks | 90（5查询×60） | 52（5查询×20） |
| LLM context 长度 | ~17,500 tokens | ~10,000 tokens（减少43%） |
| 低相关 chunks (dist≥0.5) | 有 | 0 |
| 覆盖页面数 | 20/20 | 19/20 |
| 无关内容注入 | 大量 | 极少 |

---

### 5. 爬取模式：全量重爬而非增量

**问题**

每次点击"爬取文档"按钮都重新下载所有页面，浪费带宽和时间，已有数据被完全覆盖。

**修复**

修改 `crawl_docs` 为增量模式：
- 加载现有 manifest.json，构建已爬取 URL 集合
- 过滤掉已存在的 URL，只爬取新 URL
- 将新页面与已有页面合并保存
- 无新 URL 时直接返回已有数据

**前后对比**

| 场景 | 全量重爬 | 增量爬取 |
|------|---------|---------|
| 首次爬取 | 爬 20 页 | 爬 20 页（相同） |
| 再次点击 | 重新爬 20 页（~5分钟） | 0 新 URL，直接返回（~2秒） |
| 文档新增 3 页 | 重新爬全部 23 页 | 只爬 3 页新内容 |

---

### 6. 缺乏数据管理能力：无法删除数据重来

**问题**

爬取/提取/生成后，如果结果不满意，只能手动删数据库和文件目录。

**修复**

新增三个 DELETE 接口：

| 接口 | 功能 | 附加操作 |
|------|------|---------|
| `DELETE /api/task1/crawl` | 删除爬取文档（文件+目录） | 重置 ChromaDB，重置爬取状态 |
| `DELETE /api/task1/features` | 删除所有特征 | 重置提取状态 |
| `DELETE /api/task1/scenarios` | 删除所有场景 | 重置生成状态 |

前端快捷操作面板在每个步骤完成后显示红色删除按钮。

---

### 7. 缺乏实时进度反馈

**问题**

点击操作按钮后只显示 spinner，无进度信息。

**修复**

- 后端新增 `_crawl_status`、`_extract_status`、`_generate_status` 模块级状态字典
- 新增 `/crawl/status`、`/extract/status`、`/generate/status` GET 接口
- 前端以 1.5s 间隔轮询状态，实时更新
- 仪表板改为流水线布局（1→2→3 箭头连接），每步显示圆形状态指示器+进度文字+删除按钮

**前后对比**

| 指标 | 之前 | 之后 |
|------|------|------|
| 进度显示 | 仅 spinner | 实时页数/特征数/场景数 |
| 操作完成 | 无指示 | 绿色✓圆形指示器 |
| 操作失败 | 无提示 | 红色✗ + 错误信息 |
| 步骤依赖 | 无限制 | 顺序限制 |
| 数据删除 | 手动清文件 | 一键删除按钮 |

---

### 8. 爬取图片缺失：文档截图未下载

**问题**

crawl4ai 只提取文字，功能截图未保存，无法用于后续截图对比（作为参考图）。

**修复**

- `CrawledPage` 模型新增 `images: list[dict]` 字段
- 新增 `_download_images()` 异步函数，提取同域图片
- 过滤掉 SVG、logo/icon/favicon、<100 bytes 的图片
- 图片保存到 `crawled_docs/images/`，manifest 记录 url/alt/local_path

**前后对比**

| 指标 | 之前 | 之后 |
|------|------|------|
| 图片数据 | 0 | 64 张 |
| 参考图可用性 | 无 | 每页平均约 3 张功能截图 |

---

## 三、全管线最终数据统计

### 三轮迭代对比

| 项目 | 第一轮（MiniLM+27页+n=60） | 第二轮（bge-m3+27页+n=60） | 第三轮（bge-m3+20页+n=20） |
|------|------|------|------|
| 爬取页面 | 27 | 27 | 20 |
| 文档块 | 398（含大量重复3倍+噪音） | 118 | 89 |
| 噪音 chunks | 56（占14%） | 0 | 0 |
| 干净 chunks | 316（79.4%） | 118 | 89（100%） |
| 提取特征 | 20 | 25 | 24 |
| 生成场景 | 36 | 47 | 43 |
| 爬取图片 | 0 | 52 | 64 |
| 总内容字符 | ~160,000 | 81,090 | 59,533 |
| 嵌入模型 | MiniLM-L6-v2（384维） | bge-m3（1024维） | bge-m3（1024维） |
| 无关 /docs/dev/ chunks | 大量 | 70（含web-server-config 32个） | 6（仅api+sso） |
| "导入导出"检索 | — | 错误（web-server-config） | Top-1偏移但import-export在Top-3 |
| 中文Top-1匹配率 | 20%（1/5组） | — | 80%（8/10组，含内容相关） |
| 中文查询距离范围 | 0.58-0.87 | — | 0.28-0.53 |
| RAG context (5×n) | ~17,500 tokens（5×60） | — | ~10,000 tokens（5×20） |

**跨语言检索详细对比（MiniLM vs bge-m3）**

| 中文查询 | MiniLM Top-1 | MiniLM dist | bge-m3 Top-1 | bge-m3 dist | 英文 Top-1 | bge-m3 是否匹配 |
|---------|-------------|-------------|-------------|-------------|-----------|-------------|
| 如何创建一个Board | admin-manual | 0.58 | Board | 0.34 | Board | ✅ |
| Card的创建和编辑 | list-view | 0.61 | Card | 0.28 | Card | ✅ |
| 用户权限管理 | user-manual | 0.83 | instance-settings | 0.40 | Board | ❌（但内容相关） |
| 通知和提醒功能 | notifications | 0.86 | Notifications | 0.35 | Notifications | ✅ |
| 导入导出数据 | user-manual | 0.87 | Card | 0.53 | import-export | ❌ |

> MiniLM 时期中文查询的 Top-1 几乎全是导航噪音页（admin-manual、user-manual），因为噪音 chunks 包含大量 URL 链接文本，恰好和中文关键词部分重叠。bge-m3 + 内容清洗后，检索结果全部指向有实际内容的页面。

### 特征分类分布（第三轮最终版）

| 分类 | 特征数 | 特征列表 |
|------|--------|---------|
| Board管理 | 5 | 创建Board、编辑Board、删除Board、导出Board为CSV、配置Board权限 |
| 卡片管理 | 5 | 创建卡片、编辑卡片、移动卡片、删除卡片、配置卡片选项 |
| 列表管理 | 4 | 创建列表、编辑列表名称、删除列表、排序列表 |
| 项目管理 | 2 | 创建项目、配置项目设置 |
| 设置管理 | 2 | 配置个人资料、配置实例设置 |
| 导航与搜索 | 1 | 使用侧边栏导航 |
| 成员与权限 | 1 | 管理用户 |
| 导入导出 | 1 | 导入入门项目 |
| 通知 | 1 | 查看通知 |
| 账号管理 | 1 | 注册账号 |
| 开发者手册 | 1 | 生成API客户端 |

---

## 四、优化效果总结

核心改进按影响排序：

1. **URL 确过滤**（影响最大）：排除无关 dev 运维页面，无关 chunks 从 70→6（仅保留 api+sso），直接消除"导入导出"检索到 web-server-config 的错误
2. **嵌入模型升级**：MiniLM（384维/仅英文）→ bge-m3（1024维/多语言），中文 Top-1 匹配率从 20%→80%（含内容相关），中文查询距离范围从 0.58-0.87 → 0.28-0.53
3. **内容噪声过滤**：每页内容缩减约 50%，噪声 chunks 从 56→0，干净 chunks 占比从 79.4%→100%
4. **检索数量调优**：n=60 → n=20，LLM context 从 ~17,500 tokens → ~10,000 tokens（减少43%），低相关 chunks (dist≥0.5) 从有 → 0
5. **ChromaDB 重复索引修复**：发现旧索引中每个 chunk 存了 3 遍（325 vs 实际 89），原因是 chunk ID 包含随机 hash 导致 upsert 叠加而非替换。修复：重建前先调用 `reset()` 清空
6. **增量爬取+删除能力**：管线可迭代运行，数据可重置
7. **实时进度反馈**：用户体验大幅改善
8. **图片下载**：64 张功能截图可用于后续截图对比

---

## 五、仍待改进

1. **"导入导出"检索偏移**：中文查询"导入导出数据"仍检索到 Card 页面而非 Import/Export 页面（dist=0.53），但 import-export 在 Top-3 中（dist=0.56）。bge-m3 对抽象概念的跨语言匹配仍有偏差。实测发现**中英混合查询可命中**：`"4gaboards import export Board 数据导入导出"` → Top-1 = import-export（dist=0.28）。后续可优化检索查询，加入英文关键词增强
2. **"列表视图操作"检索偏移**：中文查询"列表视图操作"检索到 Card（dist=0.42），"操作"一词偏向了 Card 的操作描述。英文查询"List view operations"可正确命中 list-view（dist=0.39）
3. **是否需要 Reranker**：当前 89 chunks 语料库规模下，Reranker 的边际收益不大。4组"不匹配"中2组实际内容相关，真正的检索错误仅2组，且可通过中英混合查询规避。建议先优化检索查询中的英文关键词，后续语料规模扩大（数百+ chunks）时再考虑加入 Reranker
4. **特征粒度**：部分分类只有 1 个特征（如导航与搜索、成员与权限），可能需要调优提取 prompt 或增加分块粒度
5. **场景步骤可执行性**：生成的步骤描述偏抽象，与实际 Playwright 操作的映射仍需中间转换层（snapshot resolver）
6. **图片与特征关联**：图片仅记录在 CrawledPage 上，尚未与特征/场景关联
7. **ChromaDB 重复索引问题**：由于 `parser.py` 中 chunk ID 包含随机 hash（`uuid.uuid4().hex[:6]`），每次重建索引时同一内容会生成不同 ID，导致 `upsert` 叠加而非替换。必须每次重建前先调用 `VectorStore.reset()` 清空旧数据。已修复但需注意后续维护