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
  type: "page_content" | "url_change" | "element_exists" | "visual_match";
  description: string;
  source_chunk_id?: string;
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
}

// ── Agent Status ──

export interface SystemStatus {
  backend_status: "running" | "stopped" | "error";
  chromadb_status: "connected" | "disconnected";
  crawl_status: "idle" | "crawling" | "completed" | "failed";
  last_crawl_time?: string;
  active_executions: number;
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
  pages_crawled?: number;
  total_pages?: number;
  error?: string;
}

export interface ExtractStatus {
  status: "idle" | "extracting" | "completed" | "failed";
  features_extracted?: number;
  error?: string;
}

export interface GenerateStatus {
  status: "idle" | "generating" | "completed" | "failed";
  scenarios_generated?: number;
  error?: string;
}

export interface GenerationStatus {
  status: "idle" | "extracting" | "generating" | "completed" | "failed";
  features_extracted?: number;
  scenarios_generated?: number;
  error?: string;
}