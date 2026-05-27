# OmniTest

> **OmniTest** — 智能化全维测试平台 (Smart & Comprehensive Testing)
>
> <svg width="28" height="28" viewBox="0 0 32 32"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#3B82F6"/><stop offset="100%" stop-color="#8B5CF6"/></linearGradient></defs><path d="M16 2 L4 8 L4 16 C4 24 16 30 16 30 C16 30 28 24 28 16 L28 8 Z" fill="url(#g)"/><path d="M12 16 L14.5 18.5 L20 12" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>

基于大模型的测试场景生成与智能测试工具。从 Web 应用用户手册中自动提取功能特征、生成结构化测试场景，并通过智能 Agent 自动执行与验证。

**支持中英文切换** — 前端界面支持中文/English一键切换，默认中文显示。

## 架构概览

两个独立子系统通过标准化 JSON 测试场景格式连接：

```
Subsystem 1 (RAG Pipeline)              Subsystem 2 (Agent Execution)
┌──────────────────────┐                ┌──────────────────────┐
│ crawl4ai → 爬取文档  │                │ LangGraph 状态图     │
│ parse → 分块         │                │   plan → execute     │
│ ChromaDB → 向量索引  │                │   → verify → reflect │
│ LLM → 提取功能特征   │                │                      │
│ LLM → 生成测试场景   │────JSON───────▶│ MCP Client           │
│                      │                │   Playwright MCP     │
│ ChromaDB + SQLite    │                │   Memory MCP         │
└──────────────────────┘                │   Verify MCP         │
                                        │                      │
                                        │ LiteLLM Router       │
                                        └──────────────────────┘

        Next.js 16 前端 (共享可视化)
        React Flow + Timeline + Screenshot Compare
```

## 目标应用

- **应用名称**: 4gaboards
- **用户手册**: https://docs.4gaboards.com/
- **Demo 地址**: https://demo.4gaboards.com/

## 技术栈

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
| 可视化 | React Flow (@xyflow/react) | Feature Tree 图形展示 |
| 统计图表 | Recharts | Mutation 统计图表 |
| 状态管理 | Zustand | 前端状态管理 |
| 数据存储 | SQLite + ChromaDB | 结构化数据 + 向量数据 |

### LLM 模型分配

| 任务 | 模型 | 说明 |
|---|---|---|
| Generation | DeepSeek-V4-Flash | 低成本、快速生成 |
| Vision | Qwen3-VL-235B-A22B-Instruct | 视觉验证 |
| Reasoning | GLM-5.1 | 规划、反思、交叉验证 |

API Base URL: `https://chatbox.isrc.ac.cn/api/v1` (OpenAI-compatible)

## 项目结构

```
omni_test/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # LiteLLM、MCP、全局配置
│   │   ├── api/
│   │   │   ├── task1_routes.py      # 功能提取 + 场景生成 API
│   │   │   ├── task2_routes.py      # Agent 执行 + 验证 API
│   │   │   └── common_routes.py     # 共享路由 (状态、导出)
│   │   ├── task1/                   # Subsystem 1: RAG + 场景生成
│   │   │   ├── crawler.py           # 文档爬取 (crawl4ai)
│   │   │   ├── parser.py            # 文档解析 + 分块
│   │   │   ├── vector_store.py      # ChromaDB 向量索引
│   │   │   ├── extractor.py         # 功能特征提取 (LLM)
│   │   │   ├── generator.py         # 场景生成 (LLM + RAG)
│   │   │   ├── models.py            # 数据模型
│   │   │   └── granularity.py       # 粒度控制逻辑
│   │   ├── task2/                   # Subsystem 2: Agent 执行
│   │   │   ├── agent/
│   │   │   │   ├── graph.py         # LangGraph 状态图定义
│   │   │   │   ├── state.py         # Agent 状态定义
│   │   │   │   ├── mcp_client.py    # MCP Client 实现
│   │   │   │   └── nodes/
│   │   │   │       ├── plan.py      # 规划节点
│   │   │   │       ├── execute.py   # 执行节点
│   │   │   │       ├── verify.py    # 验证节点 (文本+视觉双策略)
│   │   │   │       └── reflect.py   # 反思节点 (失败重规划)
│   │   │   ├── mcp_servers/
│   │   │   │   ├── memory_mcp/      # Memory MCP Server
│   │   │   │   └── verify_mcp/      # Verify MCP Server
│   │   │   ├── mutation.py          # 变异测试模块
│   │   │   └── models.py            # 执行数据模型
│   │   ├── llm/
│   │   │   ├── router.py            # LiteLLM 统一路由
│   │   │   └── prompts/             # Prompt 模板
│   │   └── db/
│   │       ├── database.py          # SQLite ORM
│   │       └── models.py            # DB 数据模型
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                     # Next.js App Router
│   │   │   ├── page.tsx             # Dashboard
│   │   │   ├── features/            # Feature Tree 页面
│   │   │   ├── scenarios/           # Scenario 页面
│   │   │   ├── executions/          # Execution Timeline 页面
│   │   │   └── mutations/           # Mutation 面板
│   │   ├── components/
│   │   │   ├── FeatureTree.tsx      # React Flow 特征树
│   │   │   ├── ScenarioDetail.tsx   # 可展开步骤列表
│   │   │   ├── ExecutionTimeline.tsx # 执行时间线
│   │   │   ├── ScreenshotCompare.tsx # 截图对比
│   │   │   ├── MutationPanel.tsx    # 变异测试面板
│   │   │   ├── AppLayout.tsx        # 导航布局
│   │   │   └── ui/                  # shadcn/ui 组件
│   │   ├── lib/
│   │   │   ├── api.ts               # API 客户端
│   │   │   ├── types.ts             # TypeScript 类型
│   │   │   ├── store.ts             # Zustand 状态管理
│   │   │   ├── i18n.ts              # 国际化翻译字典
│   │   │   ├── useI18n.ts           # 中英文切换 Hook
│   │   │   └── utils.ts             # 工具函数
│   ├── package.json
│   └── Dockerfile
├── nginx/
│   ├── omnitest.conf              # Nginx 反向代理配置（参考）
│   └── setup.sh                   # 自动安装脚本（需 sudo）
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── task.md                       # 任务要求
│   ├── design.md                     # 设计规格
│   ├── plans.md                      # 构建计划
│   └── 大作业题目.pdf                # 题目原文
└── CLAUDE.md                         # 开发规则
```

## Task 1: RAG + 测试场景生成

### 数据流

```
4gaboards docs → 爬取 → 解析/分块 → ChromaDB 索引 → RAG 检索 → LLM 生成
                                                            ↓
                                              Feature Tree + Scenario JSON
```

### 功能特征提取

- 从 ChromaDB 检索相关文档 chunks
- DeepSeek-V4-Flash 生成 Feature Tree
- 粒度控制在"创建 Board"级别 (不过细如"点击按钮"，也不过粗如"Board 管理")
- 输出格式:

```json
{
  "features": [
    {
      "id": "F1",
      "name": "创建Board",
      "category": "Board管理",
      "description": "用户可以通过点击新建按钮创建一个新的Board",
      "source_chunks": ["chunk_id_1", "chunk_id_3"]
    }
  ]
}
```

### 测试场景生成

- 对每个功能特征，检索相关文档 chunks
- DeepSeek-V4-Flash + RAG 生成场景，格式遵循 `[step+ expectation?]+`

```json
{
  "scenarios": [
    {
      "id": "S1",
      "feature_id": "F1",
      "name": "创建Board - 正常流程",
      "steps": [
        {"step": 1, "action": "点击页面右上角的'新建Board'按钮", "target": "新建Board按钮", "source_chunk_id": "chunk_1"},
        {"step": 2, "action": "在弹出的对话框中输入Board名称'TestBoard'", "target": "Board名称输入框", "source_chunk_id": "chunk_2"},
        {"step": 3, "action": "点击'创建'按钮确认", "target": "创建确认按钮", "source_chunk_id": "chunk_3"}
      ],
      "expectations": [
        {"type": "page_content", "description": "页面中显示名为'TestBoard'的新Board卡片", "source_chunk_id": "chunk_4"}
      ]
    }
  ]
}
```

### 幻觉控制

- **RAG-first**: 所有 LLM 调用包含检索上下文，减少幻觉
- **Source grounding**: 每个 step/expectation 引用 source_chunk_id，可追溯到原文
- **Cross-validation**: GLM-5.1 交叉验证步骤与文档是否匹配
- **Granularity self-check**: 自动验证 step 数在 1-8 范围内

## Task 2: Agent 执行与验证

### LangGraph 状态图

```
START → PLAN → EXECUTE → VERIFY → [pass?]
                                    ├── yes → END (success)
                                    └── no → REFLECT → re-plan (max 3 retries) → EXECUTE
                                          └── max retries exceeded → END (fail + reason)
```

### MCP 工具层

| MCP Server | 工具 | 说明 |
|---|---|---|
| Playwright MCP | browser_navigate, browser_click, browser_type, browser_screenshot, browser_get_text | 浏览器自动化 |
| Memory MCP | store_context, retrieve_context, get_scenario | 执行上下文存储 |
| Verify MCP | compare_screenshots, check_text_content, check_element_exists | 验证工具 |

### 验证双策略

- **文本验证优先**: browser_get_text 获取页面文本，对比 expectations (快速、低成本)
- **视觉验证回退**: browser_screenshot 截图后，Qwen3-VL 判断页面是否显示预期内容 (更准确)

### 变异测试

| 变异类型 | 说明 |
|---|---|
| Action mutation | 修改操作目标 (如点击错误按钮) |
| Input mutation | 修改输入值 (如输入无效字符) |
| Step mutation | 删除/重复/重排序步骤 |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- npm

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，设置 LLM API Key
# LLM_API_KEY=your_api_key_here
```

### 本地开发

**后端**:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --workers 4
```

**前端**:

```bash
cd frontend
npm install
npm run dev
```

**Nginx 反向代理**（统一入口，无需分别访问前后端端口）:

```bash
# 启动 Nginx
~/local/nginx/sbin/nginx

# 重载配置
~/local/nginx/sbin/nginx -s reload

# 停止
~/local/nginx/sbin/nginx -s stop
```

Nginx 配置文件: `~/local/nginx/conf/nginx.conf`，监听 **8080 端口**，统一代理：

- `/` → 前端 (Next.js 3000)
- `/api/` → 后端 API (FastAPI 8000)
- `/screenshots/` → 截图文件（Nginx 直接从磁盘 serve，比走 FastAPI 更快）
- `/ws/` → WebSocket 实时推送

访问 **http://localhost:8080** 即可使用全部功能，无需分别访问 3000 和 8000。

### Docker 部署

```bash
docker-compose up --build
```

- 前端 + Nginx: http://localhost:8080
- 后端: http://localhost:8000
- ChromaDB: http://localhost:8001

## API 端点

### Task 1 - RAG Pipeline

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/task1/crawl` | 爬取文档网站，解析分块存入 ChromaDB |
| POST | `/api/task1/extract-features` | 从 ChromaDB chunks 提取功能特征 |
| POST | `/api/task1/generate-scenarios` | 根据功能特征生成测试场景 |
| GET | `/api/task1/features` | 获取所有功能特征 |
| GET | `/api/task1/features/{id}` | 获取单个功能特征 |
| GET | `/api/task1/scenarios` | 获取所有测试场景 |
| GET | `/api/task1/scenarios/{id}` | 获取单个测试场景 |

### Task 2 - Agent Execution

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/task2/execute/{scenario_id}` | 执行测试场景 |
| GET | `/api/task2/executions` | 获取执行记录列表 |
| GET | `/api/task2/executions/{id}` | 获取单个执行记录 |
| POST | `/api/task2/mutation/{scenario_id}` | 对场景执行变异测试 |
| GET | `/api/task2/mutations` | 获取变异测试结果 |
| WS | `/api/task2/ws/execution/{id}` | 实时执行进度推送 |

### Common

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/status` | 系统状态 (特征数、场景数、执行数、变异数) |
| GET | `/api/export/results` | 导出全部结果 |

## 前端页面

| 路由 | 页面 | 功能 |
|---|---|---|
| `/` | Dashboard | 项目概览、统计数据、快捷操作 |
| `/features` | FeatureTree | React Flow 三级树 (Category → Feature → Scenario) |
| `/features/[id]` | FeatureDetail | 功能详情 + 关联场景列表 |
| `/scenarios` | ScenarioList | 所有测试场景列表 |
| `/scenarios/[id]` | ScenarioDetail | 可展开步骤列表、expectation 高亮 |
| `/executions` | ExecutionList | 执行记录列表 |
| `/executions/[id]` | ExecutionDetail | 执行时间线 + 截图对比 |
| `/mutations` | MutationPanel | 变异类型统计、执行矩阵、错误类型图表 |

## 国际化 (i18n)

前端支持中英文一键切换：

- 默认语言：中文 (zh)
- 点击侧边栏底部「中文 / English」按钮可切换语言
- 语言偏好自动保存到 `localStorage`
- 所有页面文本（标题、描述、按钮、表格、状态标签等）均实时切换
- 翻译字典位于 `frontend/src/lib/i18n.ts`

## 品牌 & Icon

- **项目名称**: OmniTest — 体现测试"智能、快速、全面" (Omni = 全维度)
- **Logo**: 盾牌 + 对勾 + 闪电，渐变色蓝紫 (#3B82F6 → #8B5CF6)
- **Favicon**: `frontend/public/favicon.svg`

## 关键设计决策

| 决策 | 原因 |
|---|---|
| 双独立子系统 | 对应评分维度，可独立优化 |
| MCP + LangGraph 混合 | MCP 是标准化 AI 工具协议；LangGraph 提供成熟状态机编排 |
| LiteLLM 路由 | 统一国内 LLM OpenAI-compatible 接口，按任务类型分配模型 |
| 双重验证策略 | 文本优先 (快/便宜)，视觉回退 (准确) |
| 反思 + 重试上限 | 最多 3 次避免无限循环，详细失败原因输出 |
| Source grounding 幻觉控制 | 可追溯到文档原文，不同 LLM 交叉验证 |