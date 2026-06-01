// TypeScript type definitions matching backend Pydantic models

// ── Task 1: RAG Pipeline Types ──

export interface Feature {
  id: string;
  name: string;
  category: string;
  description: string;
  source_chunks: string[];
}

export interface Step {
  step: number;
  action: string;
  target: string;
  source_chunk_id?: string;
}

export interface Expectation {
  type: "page_content" | "url_change" | "element_exists" | "element_visible" | "toast_message" | "visual_match";
  description: string;
  source_chunk_id?: string;
  reference_image?: string;
}

export interface TestScenario {
  id: string;
  feature_id: string;
  name: string;
  steps: Step[];
  expectations: Expectation[];
}

// ── Task 2: Agent Execution Types ──

export interface Action {
  tool: string;
  args: Record<string, unknown>;
  description: string;
}

export interface PageState {
  url: string;
  title: string;
  text_content: string;
  screenshot_path?: string;
}

export interface StepResult {
  step_number: number;
  action: Action;
  page_state: PageState;
  screenshot_path?: string;
  success: boolean;
  error?: string;
}

export interface VerifyResult {
  passed: boolean;
  reason: string;
  text_match?: boolean;
  visual_match?: boolean;
  details?: string;
}

export interface ExecutionRecord {
  id: string;
  scenario_id: string;
  scenario_name?: string;
  status: AgentStatus;
  plan: Action[];
  executed_steps: StepResult[];
  verification_result: VerifyResult | null;
  screenshots: string[];
  retry_count: number;
  reflection?: string;
  final_result: "pass" | "fail" | "";
  failure_reason?: string;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
}

export enum AgentStatus {
  PENDING = "pending",
  PLANNING = "planning",
  EXECUTING = "executing",
  VERIFYING = "verifying",
  REFLECTING = "reflecting",
  COMPLETED = "completed",
  FAILED = "failed",
}

// ── Mutation Testing Types ──

export enum MutationType {
  ACTION_MUTATION = "action_mutation",
  INPUT_MUTATION = "input_mutation",
  STEP_MUTATION = "step_mutation",
}

export interface MutationResult {
  id: string;
  original_scenario_id: string;
  mutation_type: MutationType;
  mutated_scenario: TestScenario;
  execution: ExecutionRecord;
  detected_error_type?: "execution_exception" | "layout_issue" | "semantic_error" | "none";
  detected_error_description?: string;
}

// ── API Response Wrappers ──

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ── Dashboard Stats ──

export interface DashboardStats {
  feature_count: number;
  scenario_count: number;
  execution_count: number;
  success_rate: number;
  mutation_count: number;
  mutation_detection_rate: number;
  crawled_pages: number;
  chromadb_chunks: number;
  pipeline: {
    crawl: CrawlStatus;
    extract: ExtractStatus;
    generate: GenerateStatus;
  };
}

// ── Agent Status ──

export interface PipelineStepStatus {
  status: "idle" | "crawling" | "extracting" | "generating" | "completed" | "failed";
  step: string;  // sub-step: downloading, parsing, storing, retrieving, llm_call, saving, completed, failed, ""
  features_extracted?: number;
  scenarios_generated?: number;
  pages_crawled?: number;
  total_pages?: number;
  error?: string | null;
}

export interface SystemStatus {
  backend_status: "running" | "stopped" | "error";
  chromadb_status: "connected" | "disconnected";
  active_executions: number;
  features: number;
  scenarios: number;
  crawled_pages: number;
  chromadb_chunks: number;
  pipeline: {
    crawl: PipelineStepStatus;
    extract: PipelineStepStatus;
    generate: PipelineStepStatus;
  };
}

// ── WebSocket Event Types ──

export type WebSocketEvent =
  | { type: "execution_started"; execution_id: string; scenario_id: string }
  | { type: "step_completed"; execution_id: string; step_result: StepResult }
  | { type: "verification_completed"; execution_id: string; verify_result: VerifyResult }
  | { type: "reflection_started"; execution_id: string; retry_count: number }
  | { type: "execution_completed"; execution_id: string; final_result: "pass" | "fail"; failure_reason?: string }
  | { type: "mutation_completed"; mutation_id: string; mutation_result: MutationResult };

// ── Crawl & Generation Status ──

export interface CrawlStatus {
  status: "idle" | "crawling" | "completed" | "failed";
  step?: string;
  pages_crawled?: number;
  total_pages?: number;
  error?: string;
}

export interface ExtractStatus {
  status: "idle" | "extracting" | "completed" | "failed";
  step?: string;
  features_extracted?: number;
  error?: string;
}

export interface GenerateStatus {
  status: "idle" | "generating" | "completed" | "failed";
  step?: string;
  scenarios_generated?: number;
  error?: string;
}

export interface GenerationStatus {
  status: "idle" | "extracting" | "generating" | "completed" | "failed";
  features_extracted?: number;
  scenarios_generated?: number;
  error?: string;
}

// ── Settings & Token Usage Types ──

export interface AppSetting {
  key: string;
  value: string;
  category: string;
  is_secret: boolean;
  description: string;
  is_dynamic: boolean;
}

export interface TokenUsageSummary {
  total_tokens: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost: number;
  currency: string;
  call_count: number;
  per_model: Record<string, {
    tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost: number;
    model_name: string;
    call_count: number;
  }>;
  per_stage: Record<string, {
    tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost: number;
    call_count: number;
  }>;
  period_days: number;
}

export interface TokenUsageDetail {
  id: string;
  model_key: string;
  model_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  pipeline_stage: string;
  cost_estimate: number;
  currency: string;
  timestamp: string | null;
}

// ── Graph (Neo4j) Types ──

export interface GraphNode {
  id: string;
  type: "feature" | "scenario" | "execution" | "mutation";
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface DependencyGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  neo4j_enabled: boolean;
}

export interface FeatureCoverage {
  feature_id: string;
  scenarios: { id: string; name: string; status: string }[];
  executions: { id: string; status: string; final_result: string }[];
  coverage_rate: number;
}

export interface CoverageStats {
  categories: Record<string, {
    feature_count: number;
    scenario_count: number;
    coverage_rate: number;
  }>;
}