# OmniTest 项目概述

## 一、项目简介

OmniTest（智能综合测试平台）是一个全栈 Web 应用测试系统，包含两个独立但衔接的子系统：

- **任务一（RAG 管线）**：从 4gaboards 文档站点爬取文档 → 分块嵌入索引 → RAG 检索 + LLM 生成 → 输出功能特征树和结构化测试场景
- **任务二（Agent 执行）**：LangGraph 状态图驱动 → MCP 协议控制浏览器 → 双策略验证 → 失败反思重试 → 变异测试

目标应用：4gaboards（文档 https://docs.4gaboards.com/，演示 https://demo.4gaboards.com/）

---

## 二、技术栈

### 后端

| 类别 | 技术 | 用途 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | API 服务，WebSocket 实时推送 |
| ORM | SQLAlchemy | SQLite 数据持久化 |
| 数据验证 | Pydantic + pydantic-settings | 数据模型，配置加载 |
| RAG 向量库 | ChromaDB | 文档 chunks 嵌入存储与语义检索 |
| 嵌入模型 | BAAI/bge-m3（1024 维，多语言） | 中英文混合语义编码 |
| 文本分块 | LangChain RecursiveCharacterTextSplitter | Markdown 文档分块 |
| Web 爬取 | crawl4ai | 文档站点爬取与 Markdown 转换 |
| Agent 框架 | LangGraph | 状态图编排（PLAN→EXECUTE→VERIFY→REFLECT） |
| MCP 协议 | mcp SDK | Playwright/Memory/Verify 三服务器通信 |
| LLM 路由 | LiteLLM | 统一 OpenAI 兼容 API 调用 |
| LLM 模型 | DeepSeek-V4-Flash（生成）、GLM-5.1（推理）、Qwen3-VL（视觉） | 多模型分工协作 |
| 浏览器自动化 | Playwright MCP | 浏览器操作执行 |
| 数据库 | SQLite（WAL 模式） | 业务数据持久化 |

### 前端

| 类别 | 技术 | 用途 |
|------|------|------|
| 框架 | Next.js 16 + React 19 | App Router 页面路由 |
| UI 组件 | shadcn/ui + Tailwind CSS v4 | 组件库与样式 |
| 图可视化 | @xyflow/react (React Flow) | 功能特征树展示 |
| 图表 | Recharts | 变异测试统计图表 |
| 状态管理 | Zustand | 全局状态与 API 调用 |
| 实时通信 | WebSocket | 执行进度实时推送 |
| 国际化 | 自定义 i18n（中/英切换） | 双语界面 |

### 部署

| 方式 | 说明 |
|------|------|
| 本地开发 | 后端 uvicorn :8000，前端 next.js :3000（通过 rewrites 反代后端） |
| Docker | docker-compose.yml |

---

## 三、项目架构

```
┌───────────────────────────────────────────────────────────┐
│                      Frontend (Next.js)                    │
│  Dashboard │ Feature Tree │ Scenarios │ Executions │ Mutations │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API + WebSocket
┌──────────────────────┴──────────────────────────────────────┐
│                    Backend (FastAPI)                          │
│                                                              │
│  ┌─────────── Task 1 (RAG Pipeline) ──────────────┐         │
│  │  crawl4ai → parser → ChromaDB → extractor → generator │  │
│  │          (爬取)    (分块)   (检索)    (提取)     (生成) │  │
│  └─────────────────────────┬──────────────────────────┘      │
│                            │ JSON TestScenario                │
│  ┌─────────── Task 2 (Agent Execution) ───────────┐         │
│  │  LangGraph: PLAN → EXECUTE → VERIFY → REFLECT        │  │
│  │  MCP: Playwright + Memory + Verify                    │  │
│  │  双策略验证: 文本(GLM-5.1) + 视觉(Qwen3-VL)           │  │
│  │  变异测试: action / input / step mutations             │  │
│  └─────────────────────────────────────────────────────┘     │
│                                                              │
│  SQLite (业务数据) │ ChromaDB (向量数据) │ LiteLLM (LLM 路由) │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、任务一完成情况

### 管线流程

```
crawl4ai 爬取文档站点
    → 内容噪声过滤（剥离导航栏/侧边栏/页脚）
    → RecursiveCharacterTextSplitter 分块 (chunk_size=1000, overlap=200)
    → bge-m3 嵌入编码 → ChromaDB 存储
    → 多查询 RAG 检索（5 个中英混合查询 × 20 结果，去重合并）
    → DeepSeek-V4-Flash 生成 Feature（15-25 个，中文输出）
    → 逐特征 RAG 检索 + DeepSeek-V4-Flash 生成 TestScenario
    → 粒度校验 + SQLite 持久化
```

### 当前数据

| 项目 | 数值 |
|------|------|
| 爬取页面 | 20 个功能文档页面 |
| 文档 chunks | 89 个（0 噪音，100% 干净） |
| /docs/dev/ 页面 | 2 个保留（api + sso），其余运维页面已排除 |
| 提取特征 | 24 个 |
| 生成场景 | 43 个 |
| 爬取图片 | 64 张功能截图 |
| 总内容字符 | 59,533（噪声占比 <5%） |

### API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/task1/crawl` | 爬取文档（增量模式） |
| DELETE | `/api/task1/crawl` | 删除爬取数据 + 重置 ChromaDB |
| GET | `/api/task1/crawl/status` | 爬取进度 |
| POST | `/api/task1/extract-features` | RAG 检索 + LLM 特征提取 |
| DELETE | `/api/task1/features` | 删除所有特征 |
| POST | `/api/task1/generate-scenarios` | RAG 检索 + LLM 场景生成 |
| DELETE | `/api/task1/scenarios` | 删除所有场景 |
| GET | `/api/task1/features` | 查询特征列表 |
| GET | `/api/task1/scenarios` | 查询场景列表 |

### 已完成的优化（详见 [task1-optimization-summary.md](task1-optimization-summary.md)）

| 序号 | 优化项 | 效果 |
|------|--------|------|
| 1 | 嵌入模型升级：MiniLM → bge-m3 | 中文 Top-1 匹配率 20% → 80%，查询距离 0.58-0.87 → 0.28-0.53 |
| 2 | 内容噪声过滤：四阶段剥离导航/侧边栏/页脚 | 噪声 chunks 56 → 0，干净率 79.4% → 100%，内容缩减约 50% |
| 3 | URL 精确过滤：排除 /docs/dev/ 运维页面 | 无关 chunks 70 → 6（仅保留 api+sso），消除"导入导出"检索错误 |
| 4 | 检索数量调优：n=60 → n=20 | LLM context ~17,500 → ~10,000 tokens（减少 43%），低相关 chunks 消除 |
| 5 | ChromaDB 重复索引修复 | 每次重建前 reset()，chunks 325 → 89（消除 3 倍重复） |
| 6 | 增量爬取 | 重复爬取从 ~5 分钟 → ~2 秒 |
| 7 | 实时进度反馈 | 前端轮询显示爬取页数/特征数/场景数 |
| 8 | 爬取图片下载 | 0 → 64 张功能截图 |
| 9 | 数据管理 DELETE 接口 | 一键删除爬取/特征/场景数据 |

---

## 五、任务二完成情况

### LangGraph 状态图

```
START → PLAN → EXECUTE → VERIFY
                           │
           ┌──── pass ────→ END（成功）
           │
           ┌──── fail + retry < 3 ──→ REFLECT → 修订计划 → EXECUTE（重试）
           │
           └──── fail + retry ≥ 3 ──→ END（失败）
```

### 核心模块

| 模块 | 实现 | 说明 |
|------|------|------|
| **PLAN** | ✅ 完成 | GLM-5.1 将场景步骤翻译为 MCP 工具调用序列；强制包含登录步骤；有硬编码 fallback plan |
| **EXECUTE** | ✅ 完成 | 多进程隔离执行 MCP 工具调用；动态 snapshot ref 解析（中文描述 → eN ref）；每步截图+页面状态 |
| **VERIFY** | ✅ 完成 | 双策略验证：文本验证（GLM-5.1，主策略）+ 视觉验证（Qwen3-VL，fallback）；MCP Verify 工具辅助 |
| **REFLECT** | ✅ 完成 | GLM-5.1 分析失败原因，修订执行计划；URL/凭据自动修正；最多 3 次重试 |
| **MCP Client** | ✅ 完成 | 连接 Playwright MCP、Memory MCP、Verify MCP；优雅降级（服务器不可用时返回结构化错误） |
| **Snapshot Resolver** | ✅ 完成 | 中英文关键词映射 + 评分算法，将人类可读描述映射到 Playwright eN ref |
| **Mutation Testing** | ✅ 完成 | 三种变异策略（action/input/step）；GLM-5.1 生成变异场景；自动执行并分类错误类型 |
| **Memory MCP** | ✅ 完成 | store_context / retrieve_context / get_scenario 三工具；内存+可选 SQLite 持久化 |
| **Verify MCP** | ✅ 完成 | compare_screenshots / check_text_content / check_element_exists 三工具 |

### LLM 模型分工

| 角色 | 模型 | 用途 |
|------|------|------|
| 生成 | DeepSeek-V4-Flash | 特征提取、场景生成 |
| 推理 | GLM-5.1 | 执行规划、文本验证、反思分析、变异生成 |
| 视觉 | Qwen3-VL-235B-A22B-Instruct | 截图视觉验证 |

### API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/task2/execute/{scenario_id}` | 执行测试场景（后台异步） |
| DELETE | `/api/task2/executions/{id}` | 删除执行记录 |
| POST | `/api/task2/executions/{id}/cancel` | 取消执行 |
| GET | `/api/task2/executions` | 查询执行列表 |
| GET | `/api/task2/executions/{id}` | 查询执行详情 |
| POST | `/api/task2/mutation/{scenario_id}` | 变异测试 |
| GET | `/api/task2/mutations` | 查询变异结果 |
| WS | `/api/task2/ws/execution/{id}` | 实时执行进度推送 |
| WS | `/api/task2/ws/executions` | 全局执行事件推送 |

### 已知问题与待改进

| 问题 | 说明 |
|------|------|
| Memory MCP 集成不完整 | 节点主要从 state 读取页面状态，而非通过 MCP 调用 retrieve_context |
| Verify MCP 工具能力有限 | check_element_exists 仅验证选择器语法（无浏览器）；compare_screenshots 仅做大小/二进制比对 |
| 视觉验证 system prompt 被静默忽略 | call_llm_with_vision 不接受 system_prompt 参数，Qwen3-VL 只收到 user message |
| 凭据硬编码在 prompt 中 | 登录邮箱/密码直接写入 plan prompt 文本，而非动态注入 settings |
| 多进程 force exit | 子进程用 os._exit(0) 终止以避免 MCP 清理挂起，绕过了 Python 正常清理流程 |
| 无实时流式进度 | run_agent 用 ainvoke（单次返回），未用 astream_events，前端无法实时看到节点切换 |
| Chrome 版本硬编码 | Playwright 缓存路径包含特定 chromium 版本号，升级后可能失效 |

---

## 六、全局功能

| 功能 | 说明 |
|------|------|
| 系统状态监控 | `/api/status` 检查后端/ChromaDB/爬取状态/活跃执行数 |
| 仪表板统计 | `/api/dashboard/stats` 特征/场景/执行数量、成功率、变异检出率 |
| 截图服务 | `/api/screenshots/{path}` 从磁盘提供截图文件 |
| 数据导出 | `/api/export` 导出全部数据为 JSON |
| WebSocket 实时推送 | `/ws/executions` 每 3 秒广播活跃执行状态 |
| 中英文界面切换 | 前端 i18n，localStorage 持久化语言偏好 |
| Feature Tree 可视化 | React Flow 三层树（分类→特征→场景） |
| Execution Timeline | 时间线 + 每步缩略图 |
| 截图对比 | 期望 vs 实际并排对比 |
| 变异统计面板 | Recharts 图表 + 执行矩阵 + 错误类型分布 |

---

## 七、数据模型

### SQLite 业务表

| 表 | 字段 | 说明 |
|----|------|------|
| features | id, name, category, description, source_chunks(JSON) | RAG 提取的功能特征 |
| test_scenarios | id, feature_id(FK), name, steps_json(JSON), expectations_json(JSON) | LLM 生成的测试场景 |
| execution_records | id, scenario_id(FK), status, started_at, completed_at, retry_count, plan_json, executed_steps_json, verification_result_json, screenshots_json, reflection, final_result, failure_reason | 场景执行完整记录 |
| step_results | id, scenario_id(FK), step_number, action, target, result, screenshot_path | 单步执行结果 |
| mutation_results | id, original_scenario_id(FK), mutation_type, mutation_description, execution_status, detected_error_type, detected_error_description, mutated_scenario_json, execution_record_id(FK) | 变异测试结果 |

### ChromaDB 向量库

| 属性 | 值 |
|------|------|
| Collection | 4gaboards_docs |
| 嵌入模型 | BAAI/bge-m3 |
| 嵌入维度 | 1024 |
| 距离度量 | Cosine similarity |
| 当前 chunks | 89 |
| Metadata | source_url, title, chunk_index, total_chunks_in_page |

---

## 八、关键设计决策

1. **双子系统独立衔接**：任务一和任务二通过 JSON TestScenario 格式连接，互不依赖，可独立迭代
2. **多模型分工**：生成用 DeepSeek（快+便宜），推理用 GLM-5.1（逻辑性强），视觉用 Qwen3-VL（看截图），LiteLLM 统一路由
3. **多进程隔离执行**：MCP 调用在子进程中运行，避免 anyio cancel scope 冲突（MCP SDK 与 LangGraph 的已知兼容问题）
4. **动态 ref 解析**：计划节点输出人类可读描述（如"登录按钮"），执行节点通过 snapshot resolver 实时映射到 Playwright eN ref
5. **溯源设计**：每个 Feature/Step/Expectation 都携带 source_chunks/source_chunk_id，可追溯回原始文档
6. **优雅降级**：MCP 服务器不可用时返回结构化错误而非抛异常，管线继续运行
7. **幻觉控制**：RAG-first（所有特征必须有文档依据）+ source_chunk_id 溯源 + 粒度校验