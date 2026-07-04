# Web Test Agent — 项目构建计划

> 基于设计规格: `docs/superpowers/specs/2026-05-23-omni_test-design.md`
> 生成日期: 2026-05-23

---

## 1. 项目概览

Web Test Agent 是一个自动化 Web 测试工具，包含两个独立子系统：

- **Subsystem 1 (RAG Pipeline)**：从 4gaboards 用户手册提取功能特征，生成结构化测试场景
- **Subsystem 2 (Agent Execution)**：通过 MCP 驱动的 Agent 执行测试场景，验证结果，支持 Mutation Testing

目标应用: https://demo.4gaboards.com/，文档: https://docs.4gaboards.com/

---

## 2. 技术栈总览

| 层 | 技术 | 作用 |
|---|---|---|
| RAG 框架 | LangChain | 文档解析、向量索引、检索增强 |
| 向量数据库 | ChromaDB | 文档 chunk 向量存储与检索 |
| LLM 路由 | LiteLLM | 统一国内 LLM 接口路由 |
| Agent 编排 | LangGraph | 状态机控制 Agent 流程 |
| Agent 工具 | MCP Protocol | 标准化工具调用协议 |
| 浏览器自动化 | Playwright MCP Server | 浏览器操作 |
| 后端 | FastAPI | Python API 服务 |
| 前端 | Next.js 16 + React 19 | UI 可视化 |
| UI 组件 | shadcn/ui + TailwindCSS | 组件库 + 样式 |
| 可视化 | React Flow | Feature Tree 图形展示 |
| 数据存储 | SQLite + ChromaDB | 结构化数据 + 向量数据 |

LLM 模型分配:
- **Generation**: DeepSeek-V4-Flash（低成本、快速）
- **Vision**: Qwen3-VL-235B-A22B-Instruct（视觉验证）
- **Reasoning**: GLM-5.1（规划、反思、交叉验证）

API Base URL: https://chatbox.isrc.ac.cn/api/v1（OpenAI-compatible）

---

## 3. 构建阶段划分

### Phase 0: 项目基础设施搭建

**目标**: 建立项目骨架、配置开发环境、确保前后端能独立启动运行

| # | 任务 | 详情 | 产出 |
|---|---|---|---|
| 0.1 | 初始化项目结构 | 按照 spec §2.1 创建完整目录结构 | `backend/`, `frontend/`, `docker-compose.yml` |
| 0.2 | 后端骨架搭建 | 创建 FastAPI 入口 `backend/app/main.py`，配置 CORS、路由挂载 | 可启动的空 FastAPI 服务 |
| 0.3 | 配置模块 | 实现 `backend/app/config.py`，支持 LiteLLM 配置、MCP Server 配置、API Key 环境变量 | 配置加载模块 |
| 0.4 | 数据库初始化 | 实现 `backend/app/db/database.py` + `models.py`，SQLite ORM 定义核心表（Feature, TestScenario, Step, ExecutionRecord 等） | SQLite 数据模型 |
| 0.5 | 前端骨架搭建 | Next.js 16 + App Router 初始化，安装 shadcn/ui、React Flow、TailwindCSS | 可启动的空 Next.js 应用 |
| 0.6 | Docker 配置 | 编写 `docker-compose.yml`，定义 backend、frontend、chromadb 服务 | 容器化配置 |
| 0.7 | 依赖管理 | 编写 `backend/requirements.txt` / `pyproject.toml`，`frontend/package.json` | 依赖清单 |

**验证标准**:
- `docker-compose up` 可启动所有服务
- FastAPI `/docs` 可访问 Swagger UI
- Next.js 前端可在浏览器访问

---

### Phase 1: Subsystem 1 — RAG Pipeline（特征提取 + 场景生成）

**目标**: 实现从文档爬取到测试场景生成的完整 RAG Pipeline

| # | 任务 | 详情 | 产出 |
|---|---|---|---|
| 1.1 | 数据模型定义 | 实现 `backend/app/task1/models.py`：Feature, TestScenario, Step, Expectation Pydantic 模型 | 数据模型 |
| 1.2 | 文档爬取模块 | 实现 `backend/app/task1/crawler.py`：使用 crawl4ai 爬取 https://docs.4gaboards.com 全站文档 | 爬取的原始文档数据 |
| 1.3 | 文档解析与分块 | 实现 `backend/app/task1/parser.py`：HTML → Markdown，使用 LangChain RecursiveCharacterTextSplitter（chunk_size=1000, overlap=200） | 分块后的文档 chunk |
| 1.4 | 向量索引构建 | 实现 `backend/app/task1/vector_store.py`：ChromaDB 存储，embedding 使用 sentence-transformers（无外部 API 依赖） | ChromaDB 索引 |
| 1.5 | LLM 路由模块 | 实现 `backend/app/llm/router.py`：LiteLLM 统一路由，配置 DeepSeek-V4-Flash / GLM-5.1 / Qwen3-VL 模型映射 | LiteLLM Router |
| 1.6 | Prompt 模板编写 | 编写 `backend/app/llm/prompts/extract_features.py` 和 `generate_scenarios.py`：包含粒度控制指令 | Prompt 模板 |
| 1.7 | 特征提取模块 | 实现 `backend/app/task1/extractor.py`：RAG 检索 + LLM 生成 Feature Tree，粒度控制在"创建 Board"级别 | Feature Tree JSON |
| 1.8 | 粒度控制模块 | 实现 `backend/app/task1/granularity.py`：自动验证每个 Feature 的 step 数在 1-8 范围内 | 粒度检查逻辑 |
| 1.9 | 测试场景生成 | 实现 `backend/app/task1/generator.py`：基于 Feature + RAG 检索生成 Test Scenario，格式严格遵循 `[step+ expectation?]+` | Test Scenario JSON |
| 1.10 | 幻觉控制机制 | 实现三层幻觉控制：RAG-first（所有 LLM 调用包含检索上下文）、Source grounding（step/expectation 引用 source_chunk_id）、Cross-validation（GLM-5.1 验证步骤与文档匹配） | 幻觉控制逻辑 |
| 1.11 | API 路由 | 实现 `backend/app/api/task1_routes.py`：爬取触发、特征提取、场景生成、结果查询等 API 端点 | REST API |
| 1.12 | 单元测试 | 编写 RAG Pipeline 各模块的单元测试 | 测试用例 |

**验证标准**:
- 调用 API 可完成：爬取 → 解析 → 索引 → 提取特征 → 生成场景
- 输出的 Feature 和 Scenario JSON 符合 spec 定义的数据结构
- 每个 Feature 的 source_chunks 可追溯到原始文档
- Cross-validation 通过率 ≥ 90%

---

### Phase 2: Subsystem 2 — Agent 执行与验证

**目标**: 实现基于 LangGraph + MCP 的测试执行 Agent，包含规划、执行、验证、反思闭环

| # | 任务 | 详情 | 产出 |
|---|---|---|---|
| 2.1 | 数据模型定义 | 实现 `backend/app/task2/models.py`：AgentState, Action, StepResult, PageState, VerifyResult Pydantic/TypedDict 模型 | Agent 数据模型 |
| 2.2 | Agent 状态定义 | 实现 `backend/app/task2/agent/state.py`：AgentState TypedDict，包含 scenario, plan, executed_steps, screenshots, retry_count 等字段 | Agent 状态结构 |
| 2.3 | MCP Client 实现 | 实现 `backend/app/task2/agent/mcp_client.py`：自定义 MCP Client，支持与 Playwright MCP、Memory MCP、Verify MCP 通信 | MCP Client |
| 2.4 | Playwright MCP Server 配置 | 安装配置 `@anthropic-ai/playwright-mcp` npm 包，确保 browser_navigate/click/type/screenshot/get_text 工具可用 | 浏览器自动化工具 |
| 2.5 | Memory MCP Server 开发 | 实现 `backend/app/task2/mcp_servers/memory_mcp/`：store_context、retrieve_context、get_scenario 三个工具 | 执行上下文存储工具 |
| 2.6 | Verify MCP Server 开发 | 实现 `backend/app/task2/mcp_servers/verify_mcp/`：compare_screenshots、check_text_content、check_element_exists 三个工具 | 验证工具 |
| 2.7 | Planning Node | 实现 `backend/app/task2/agent/nodes/plan.py`：GLM-5.1 将场景步骤翻译为 MCP 工具调用序列，参考 Memory MCP 存储的页面结构信息 | 规划节点 |
| 2.8 | Execution Node | 实现 `backend/app/task2/agent/nodes/execute.py`：调用 MCP Client 执行规划动作，收集 screenshots 和 page state | 执行节点 |
| 2.9 | Verification Node | 实现 `backend/app/task2/agent/nodes/verify.py`：双重验证策略——文本验证（browser_get_text，快速低成本）优先，失败则回退到视觉验证（Qwen3-VL 截图判断） | 验证节点 |
| 2.10 | Reflection Node | 实现 `backend/app/task2/agent/nodes/reflect.py`：GLM-5.1 分析失败原因，修订执行计划（最多 3 次重试） | 反思节点 |
| 2.11 | LangGraph 状态图 | 实现 `backend/app/task2/agent/graph.py`：组装 PLAN → EXECUTE → VERIFY → REFLECT 状态图，定义条件边（pass → END, fail → REFLECT） | Agent 状态图 |
| 2.12 | Prompt 模板编写 | 编写 `backend/app/llm/prompts/plan_actions.py`、`verify_result.py` | Prompt 模板 |
| 2.13 | Mutation Testing 模块 | 实现 `backend/app/task2/mutation.py`：Action mutation、Input mutation、Step mutation 三种变异策略，执行变异场景并生成报告 | Mutation Testing 模块 |
| 2.14 | Mutation Prompt | 编写 `backend/app/llm/prompts/mutation.py` | Mutation Prompt |
| 2.15 | API 路由 | 实现 `backend/app/api/task2_routes.py`：执行触发、执行状态查询、变异测试触发、结果导出等 API 端点 | REST API |
| 2.16 | 单元测试 | 编写 Agent 执行流程各节点的单元测试，模拟 MCP 工具调用 | 测试用例 |

**验证标准**:
- LangGraph 状态图可完整运行 PLAN → EXECUTE → VERIFY → END/REFLECT 循环
- 验证 Node 同时支持文本验证和视觉验证
- 反思重试最多 3 次，超出后输出详细失败原因
- Mutation Testing 可生成变异场景并输出报告
- 整个 Agent 流程可端到端执行一个测试场景

---

### Phase 3: 前端可视化与交互

**目标**: 实现完整的前端可视化界面，覆盖 Feature Tree、场景详情、执行 Timeline、Screenshot 对比、Mutation 面板

| # | 任务 | 详情 | 产出 |
|---|---|---|---|
| 3.1 | TypeScript 类型定义 | 实现 `frontend/src/lib/types.ts`：定义 Feature, TestScenario, Step, ExecutionRecord, MutationResult 等类型 | 类型系统 |
| 3.2 | API Client | 实现 `frontend/src/lib/api.ts`：封装所有后端 API 调用，包含 WebSocket 连接 | API 客户端 |
| 3.3 | Dashboard 页面 | 实现 `frontend/src/app/page.tsx`：项目概览、统计数据（Feature 数量、Scenario 数量、执行成功率等） | 首页 |
| 3.4 | Feature Tree 页面 | 实现 `frontend/src/app/features/` + `FeatureTree.tsx`：React Flow 图形，Category → Feature → Scenario 三级节点，可展开/折叠，按领域颜色编码 | Feature Tree 可视化 |
| 3.5 | Feature Detail 页面 | 实现 `frontend/src/app/features/[id]/`：单个 Feature 详情 + 关联 Scenario 列表 | Feature 详情页 |
| 3.6 | Scenario 列表与详情 | 实现 `frontend/src/app/scenarios/` + `ScenarioDetail.tsx`：可展开/折叠的步骤列表，action/target 详情，expectation 高亮，source_chunks 可点击追溯文档来源 | Scenario 页面 |
| 3.7 | Execution Timeline | 实现 `frontend/src/app/executions/` + `ExecutionTimeline.tsx`：Timeline 展示 plan → 各 step → verify → result，每步附带缩略截图，verify node 显示 pass/fail + 原因 | 执行 Timeline |
| 3.8 | Screenshot Compare | 实现 `ScreenshotCompare.tsx`：期望 vs 实际并排对比，高亮差异区域 | 截图对比组件 |
| 3.9 | Mutation Panel | 实现 `frontend/src/app/mutations/` + `MutationPanel.tsx`：变异类型列表、变异场景执行矩阵、检测到的错误类型统计图表 | Mutation 面板 |
| 3.10 | WebSocket 实时更新 | 前端 WebSocket 连接，Agent 执行过程中实时更新 Timeline 和截图，支持暂停/取消执行 | 实时通信 |
| 3.11 | 共享 API 路由 | 实现 `backend/app/api/common_routes.py`：状态查询、结果导出等共享 API | 共享 API |

**验证标准**:
- 所有页面路由可访问且正确渲染
- Feature Tree 使用 React Flow 正确展示三级结构
- 执行 Timeline 实时更新，截图缩略图正确显示
- Screenshot Compare 可并排对比并高亮差异
- WebSocket 连接稳定，暂停/取消功能可用

---

### Phase 4: 系统集成与端到端测试

**目标**: 将两个子系统与前端完整集成，进行端到端验证

| # | 任务 | 详情 | 产出 |
|---|---|---|---|
| 4.1 | 子系统对接 | 确保 Subsystem 1 生成的 JSON 场景可被 Subsystem 2 直接消费，数据格式完全兼容 | 集成验证 |
| 4.2 | 端到端流程测试 | 执行完整流程：爬取文档 → 提取特征 → 生成场景 → Agent 执行 → 前端展示 | 端到端测试结果 |
| 4.3 | Mutation Testing 端到端 | 生成变异场景 → 执行 → 前端展示变异报告 | 端到端变异测试 |
| 4.4 | 性能优化 | LLM 调用并发优化、前端加载性能优化、WebSocket 消息频率控制 | 性能优化 |
| 4.5 | 错误处理与日志 | 完善全局错误处理、LLM 调用失败重试、MCP 连接异常处理、日志系统 | 错误处理机制 |
| 4.6 | Docker 生产配置 | 完善 Dockerfile、环境变量配置、健康检查、资源限制 | 生产级 Docker 配置 |

**验证标准**:
- 从文档爬取到前端展示的完整流程可顺利运行
- Mutation Testing 端到端流程可顺利运行
- 所有异常场景有合理的错误处理和日志记录
- Docker 部署可稳定运行

---

## 4. 关键设计决策备忘

| 决策 | 原因 |
|---|---|
| 双独立子系统 | 对应评分维度，可独立优化 |
| MCP + LangGraph 混合 | MCP 是热门 AI 工具协议，LangGraph 提供成熟编排，国内 LLM 通过 LiteLLM 无缝集成 |
| LiteLLM 路由 | 所有模型使用 OpenAI-compatible API，LiteLLM 统一路由，按任务类型分配模型 |
| crawl4ai 爬取 | AI-aware 爬虫，处理动态内容优于传统 scraper |
| 双重验证策略 | 文本优先（快/便宜），视觉回退（准确），匹配"验证能力"评分维度 |
| 反思 + 重试上限 | 最多 3 次避免无限循环，详细失败原因匹配"准确失败原因分析"评分维度 |
| Source grounding 幻觉控制 | 可追溯到文档原文，不同 LLM 交叉验证，匹配"正确性与全面性"评分维度 |

---

## 5. 风险与应对

| 风险 | 影响 | 应对策略 |
|---|---|---|
| 国内 LLM API 不稳定 | Agent 执行中断 | LiteLLM 配置 fallback 模型，增加调用重试机制 |
| crawl4ai 爬取动态页面失败 | 特征提取缺失 | 备选方案：手动下载文档 + Playwright 渲染爬取 |
| Playwright MCP 兼容性问题 | 浏览器操作失败 | 提前验证 MCP Server 可用性，必要时直接使用 Playwright Python API |
| ChromaDB 向量检索质量不足 | 场景生成质量差 | 调整 chunk_size/overlap 参数，优化 embedding 模型选择 |
| 前端实时更新延迟 | 用户体验差 | WebSocket 消息精简，关键节点推送，非关键信息轮询 |
| Mutation Testing 执行时间过长 | 测试效率低 | 并行执行变异场景，设置超时阈值 |

---

## 6. 依赖清单

### 后端核心依赖

```
fastapi
uvicorn
langchain
langchain-community
langgraph
chromadb
crawl4ai
litellm
sentence-transformers
pydantic
sqlalchemy
websockets
mcp              # MCP Python SDK
```

### MCP Server 依赖

```
# Playwright MCP: @anthropic-ai/playwright-mcp (npm)
# Memory MCP / Verify MCP: 自定义 Python MCP Server
```

### 前端核心依赖

```
next@16
react@19
react-dom@19
reactflow
shadcn/ui
tailwindcss
lucide-react      # 图标库
recharts           # 统计图表
zustand            # 状态管理
socket.io-client   # WebSocket 客户端
```

---

## 7. 开发顺序建议

```
Phase 0 (基础设施) ──→ Phase 1 (RAG Pipeline) ──→ Phase 2 (Agent 执行) ──→ Phase 3 (前端) ──→ Phase 4 (集成)
      │                      │                        │                    │                   │
      └── 项目骨架            └── 文档 → 场景           └── 场景 → 执行      └── 可视化展示      └── 端到端验证
```

Phase 1 和 Phase 2 可部分并行开发（数据模型定义、LLM Router、Prompt 模板可共享），但核心逻辑需按序完成以确保 JSON 格式兼容。

Phase 3 可在 Phase 2 基础模块完成后开始（先开发静态页面，后接入实时数据）。

---

## 8. Milestone 检查点

| Milestone | 预期完成阶段 | 检查内容 |
|---|---|---|
| M1: 项目骨架可运行 | Phase 0 | `docker-compose up` 成功，前后端可访问 |
| M2: RAG Pipeline 端到端 | Phase 1 | 从文档爬取到场景生成完整流程可运行 |
| M3: Agent 端到端执行 | Phase 2 | 一个测试场景可被 Agent 规划→执行→验证→反思 |
| M4: 前端完整可视化 | Phase 3 | 所有页面正确渲染，实时更新可用 |
| M5: 系统完整可用 | Phase 4 | 从文档爬取到前端展示的完整链路可运行 |