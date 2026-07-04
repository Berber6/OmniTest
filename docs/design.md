# Web Test Agent — Design Spec

> Date: 2026-05-23
> Status: Draft → Approved

## 1. Project Overview

Build a web testing tool that:
- (Task 1) Extracts features from 4gaboards user manual via RAG, generates structured test scenarios
- (Task 2) Executes test scenarios via an MCP-powered Agent, verifies results, supports mutation testing

Target app: https://demo.4gaboards.com/ with docs at https://docs.4gaboards.com/

LLM Models (via LiteLLM unified routing):
- Generation: DeepSeek-V4-Flash (cost-effective, fast)
- Vision: Qwen3-VL-235B-A22B-Instruct (visual verification)
- Reasoning: GLM-5.1 (planning, reflection, cross-validation)
API Base URL: https://chatbox.isrc.ac.cn/api/v1 (OpenAI-compatible)
API Key: user-configured

---

## 2. Architecture: Dual Independent Subsystems

Two independent subsystems connected via standardized JSON test scenario format.

```
Subsystem 1 (RAG Pipeline)          Subsystem 2 (Agent Execution)
┌─────────────────────┐             ┌─────────────────────┐
│ crawl4ai → crawl    │             │ LangGraph state     │
│ parse → chunk       │             │   plan → execute    │
│ ChromaDB → index    │             │   → verify → reflect│
│ LLM → extract feat  │             │                     │
│ LLM → generate scen │────JSON────▶│ MCP Client          │
│                     │             │   Playwright MCP    │
│ ChromaDB + SQLite   │             │   Memory MCP        │
└─────────────────────┘             │   Verify MCP        │
                                    │                     │
                                    │ LiteLLM Router      │
                                    └─────────────────────┘

          Next.js 16 Frontend (shared visualization)
          React Flow + Timeline + Screenshot Compare
```

### 2.1 Project Structure

```
omni_test/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entry
│   │   ├── config.py                # LiteLLM, MCP, global config
│   │   ├── api/
│   │   │   ├── task1_routes.py      # Feature extraction + scenario generation API
│   │   │   ├── task2_routes.py      # Agent execution + verification API
│   │   │   └── common_routes.py     # Shared (status query, result export)
│   │   ├── task1/                   # Subsystem 1: RAG + scenario generation
│   │   │   ├── crawler.py           # 4gaboards doc crawler (crawl4ai)
│   │   │   ├── parser.py            # Doc parse + chunking
│   │   │   ├── vector_store.py      # ChromaDB vector index
│   │   │   ├── extractor.py         # Feature extraction (LLM)
│   │   │   ├── generator.py         # Scenario generation (LLM + RAG)
│   │   │   ├── models.py            # Data models (Feature, TestScenario, Step)
│   │   │   └── granularity.py       # Granularity control logic
│   │   ├── task2/                   # Subsystem 2: Agent execution
│   │   │   ├── agent/
│   │   │   │   ├── graph.py         # LangGraph state graph definition
│   │   │   │   ├── nodes/
│   │   │   │   │   ├── plan.py      # Planning node
│   │   │   │   │   ├── execute.py   # Execution node (MCP calls)
│   │   │   │   │   ├── verify.py    # Verification node (visual + text)
│   │   │   │   │   └── reflect.py   # Reflection node (failure re-planning)
│   │   │   │   ├── state.py         # Agent state definition
│   │   │   │   └── mcp_client.py    # Custom MCP Client implementation
│   │   │   ├── mcp_servers/
│   │   │   │   ├── playwright_mcp/  # Playwright MCP Server (npm package)
│   │   │   │   ├── memory_mcp/      # Custom Memory MCP Server
│   │   │   │   └── verify_mcp/      # Custom Verify MCP Server
│   │   │   ├── mutation.py          # Mutation testing module
│   │   │   └── models.py            # Execution data models
│   │   ├── llm/
│   │   │   ├── router.py            # LiteLLM unified routing
│   │   │   └── prompts/
│   │   │   │   ├── extract_features.py
│   │   │   │   ├── generate_scenarios.py
│   │   │   │   ├── plan_actions.py
│   │   │   │   ├── verify_result.py
│   │   │   │   └── mutation.py
│   │   └── db/
│   │       ├── database.py          # SQLite ORM
│   │       └── models.py            # DB data models
│   ├── requirements.txt
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/                     # Next.js 16 App Router
│   │   │   ├── page.tsx             # Dashboard
│   │   │   ├── features/            # Feature tree page
│   │   │   ├── scenarios/           # Scenario pages
│   │   │   └── executions/          # Execution timeline pages
│   │   ├── components/
│   │   │   ├── FeatureTree.tsx      # React Flow feature tree
│   │   │   ├── ScenarioDetail.tsx   # Expandable/collapsible scenario
│   │   │   ├── ExecutionTimeline.tsx # Execution timeline
│   │   │   ├── ScreenshotCompare.tsx # Screenshot comparison
│   │   │   ├── MutationPanel.tsx    # Mutation testing panel
│   │   │   └── ui/                  # shadcn/ui components
│   │   ├── lib/
│   │   │   ├── api.ts               # API client
│   │   │   └── types.ts             # TypeScript type definitions
│   ├── package.json
│   ├── Dockerfile
│   └── next.config.ts
├── docker-compose.yml
├── docs/
└── README.md
```

---

## 3. Task 1: RAG + Test Scenario Generation

### 3.1 Data Flow Pipeline

```
4gaboards docs → crawl → parse/chunk → ChromaDB index → RAG retrieval → LLM generation
                                                                    ↓
                                                      Feature tree + Scenario JSON
```

### 3.2 Doc Crawling & Parsing

- **Crawl**: crawl4ai crawls https://docs.4gaboards.com fully
- **Parse**: HTML → Markdown, LangChain RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200)
- **Index**: ChromaDB stores vectors; embedding via sentence-transformers (no embedding API dependency)

### 3.3 Feature Extraction

- Retrieve relevant doc chunks from ChromaDB
- LLM (DeepSeek-V4-Flash, cost-effective) generates feature tree
- **Granularity control**: Prompt instructs "granularity at 'create Board' level — not 'click button' (too fine), not 'Board management' (too coarse)"
- Output structure:

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

### 3.4 Test Scenario Generation

- For each feature, retrieve related doc chunks from ChromaDB
- LLM (DeepSeek-V4-Flash) + RAG generates scenarios
- Format strictly follows `[step+ expectation?]+`

```json
{
  "scenarios": [
    {
      "id": "S1",
      "feature_id": "F1",
      "name": "创建Board - 正常流程",
      "steps": [
        {
          "step": 1,
          "action": "点击页面右上角的'新建Board'按钮",
          "target": "新建Board按钮"
        },
        {
          "step": 2,
          "action": "在弹出的对话框中输入Board名称'TestBoard'",
          "target": "Board名称输入框"
        },
        {
          "step": 3,
          "action": "点击'创建'按钮确认",
          "target": "创建确认按钮"
        }
      ],
      "expectations": [
        {
          "type": "page_content",
          "description": "页面中显示名为'TestBoard'的新Board卡片"
        },
        {
          "type": "url_change",
          "description": "URL可能跳转到新Board的详情页"
        }
      ]
    }
  ]
}
```

### 3.5 Hallucination Control

- **RAG-first**: All LLM calls include retrieved context, reducing hallucination
- **Source grounding**: Each step/expectation references source_chunk_id, traceable to original doc text
- **Cross-validation**: After generation, another LLM (GLM-5.1) verifies steps match doc content
- **Granularity self-check**: Auto-verify step count per feature (1-8 is reasonable range)

---

## 4. Task 2: Agent Execution & Verification

### 4.1 LangGraph State Graph

```
START → PLAN → EXECUTE → VERIFY → [pass?]
                                        ├── yes → END (success)
                                        └── no → REFLECT → re-plan (max 3 retries) → EXECUTE
                                              └── max retries exceeded → END (fail + reason)
```

### 4.2 Agent State

```python
class AgentState(TypedDict):
    scenario: TestScenario            # Test scenario to execute
    plan: list[Action]                # Execution plan
    executed_steps: list[StepResult]  # Executed step results
    current_page_state: PageState     # Current page state
    screenshots: list[str]            # Screenshots during execution
    verification_result: VerifyResult # Verification result
    retry_count: int                  # Retry count (max=3)
    reflection: str                   # Reflection analysis
    final_result: str                 # Final result: pass/fail
    failure_reason: str               # Failure reason
```

### 4.3 MCP Tool Layer

**Playwright MCP Server** (existing npm package `@anthropic-ai/playwright-mcp`):
- `browser_navigate` → Navigate to URL
- `browser_click` → Click element
- `browser_type` → Type text
- `browser_screenshot` → Take screenshot
- `browser_get_text` → Get page text content

**Custom Memory MCP Server** (Python):
- `store_context` → Store execution context (page state, executed steps)
- `retrieve_context` → Retrieve previous execution state info
- `get_scenario` → Get current test scenario details

**Custom Verify MCP Server** (Python):
- `compare_screenshots` → Compare screenshots (expected vs actual)
- `check_text_content` → Check if page text contains expected content
- `check_element_exists` → Check if specific DOM element exists

### 4.4 Planning Node (PLAN)

- Input: test scenario steps
- GLM-5.1 translates each step to MCP tool call sequences
- Example: "click new Board button" → `browser_click(selector="#new-board-btn")`
- Planning references Memory MCP stored page structure info

### 4.5 Verification Node (VERIFY)

- **Text verification**: `browser_get_text` retrieves page text, compare against expectations
- **Visual verification**: `browser_screenshot` captures screenshot, Qwen3-VL-235B-A22B-Instruct judges if page shows expected content
- **Dual strategy**: Text verification first (fast, cheap); if fails, fall back to visual (slower but more accurate)
- Output: pass/fail + detailed reason

### 4.6 Reflection Node (REFLECT)

- When verification fails, GLM-5.1 analyzes failure cause
- Input: execution trace + screenshots + verification result
- Output: revised execution plan (max 3 retries)
- Exceeding max retries → mark as fail with detailed failure reason

### 4.7 Mutation Testing Module

- Mutate test scenario steps to generate mutant scenarios:
  - **Action mutation**: Modify operation target (e.g., click wrong button)
  - **Input mutation**: Modify input values (e.g., enter invalid characters)
  - **Step mutation**: Delete/duplicate/reorder steps
- Execute mutant scenarios, detect if app handles exceptions correctly
- Output mutation report: identify execution exceptions, layout issues, semantic errors

---

## 5. Frontend Visualization & Interaction

### 5.1 Page Routes

| Route | Page | Function |
|-------|------|----------|
| `/` | Dashboard | Project overview, statistics |
| `/features` | FeatureTree | React Flow feature tree graph |
| `/features/[id]` | FeatureDetail | Single feature detail + related scenarios |
| `/scenarios` | ScenarioList | All test scenarios list |
| `/scenarios/[id]` | ScenarioDetail | Single scenario detail (expandable steps) |
| `/executions` | ExecutionList | All execution records |
| `/executions/[id]` | ExecutionDetail | Execution timeline + screenshots |
| `/mutations` | MutationPanel | Mutation testing panel |

### 5.2 Core Components

- **FeatureTree**: React Flow, nodes at Category → Feature → Scenario levels, expandable/collapsible, color-coded by domain
- **ScenarioDetail**: Step list with expandable action/target details, expectations highlighted, source_chunks clickable for doc origin
- **ExecutionTimeline**: Timeline: plan → each step → verify → result; thumbnail screenshots per step; verify node shows pass/fail + reason
- **ScreenshotCompare**: Expected vs actual side-by-side, highlight diff regions, for detailed failure analysis
- **MutationPanel**: Mutation type list, mutation scenario execution matrix, detected error type statistics chart

### 5.3 Real-time Communication

- WebSocket pushes execution status updates during Agent execution
- Frontend updates timeline and screenshots in real time
- User can pause/cancel execution mid-way

---

## 6. Tech Stack Summary

| Layer | Tech | Role |
|-------|------|------|
| RAG framework | LangChain | Doc parsing, vector indexing, retrieval augmentation (LangChain ecosystem aligns with LangGraph) |
| Vector DB | ChromaDB | Doc chunk vector storage & retrieval |
| LLM routing | LiteLLM | Unified interface for domestic LLMs |
| Agent orchestration | LangGraph | State machine controlling Agent flow |
| Agent tools | MCP Protocol | Standardized tool calling protocol |
| Browser automation | Playwright MCP Server | Browser operations |
| Backend | FastAPI | Python API service |
| Frontend | Next.js 16 + React 19 | UI visualization |
| UI components | shadcn/ui + TailwindCSS | Component library + styling |
| Visualization | React Flow | Feature tree graph |
| Data storage | SQLite + ChromaDB | Structured data + vector data |

---

## 7. Key Design Decisions & Rationale

1. **Dual independent subsystems**: Scoring criteria separate Task 1 and Task 2; independent subsystems map to scoring dimensions; each can be optimized separately
2. **MCP + LangGraph hybrid**: MCP is the hottest AI tool protocol; LangGraph provides mature orchestration; domestic LLMs integrate seamlessly via LiteLLM; Playwright MCP ready to use
3. **LiteLLM for model routing**: All models use OpenAI-compatible API at https://chatbox.isrc.ac.cn/api/v1; LiteLLM unifies routing; models assigned per task type (DeepSeek-V4-Flash for generation, GLM-5.1 for reasoning, Qwen3-VL-235B-A22B-Instruct for visual verification)
4. **crawl4ai for doc crawling**: Latest popular AI-aware web crawler, handles dynamic content better than traditional scrapers
5. **Dual verification strategy**: Text-first (fast/cheap), visual-fallback (accurate); matches "verification capability" scoring dimension
6. **Reflection with retry limit**: Max 3 retries prevents infinite loops; detailed failure reason output matches "accurate failure reason analysis" scoring dimension
7. **Source grounding for hallucination control**: Traceability to doc origin; cross-validation with different LLM; matches "correctness & comprehensiveness" scoring dimension