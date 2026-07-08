import type {
  Feature,
  TestScenario,
  ExecutionRecord,
  MutationResult,
  DashboardStats,
  SystemStatus,
  ApiResponse,
  PaginatedResponse,
  WebSocketEvent,
  CrawlStatus,
  ExtractStatus,
  GenerateStatus,
  MutationType,
  AppSetting,
  TokenUsageSummary,
  TokenUsageDetail,
  TokenUsageDetailFilters,
  DependencyGraph,
  FeatureCoverage,
  CoverageStats,
  FeatureFilters,
  ScenarioFilters,
  ExecutionFilters,
  MutationFilters,
} from "./types";

// Browser uses same-origin requests (Next.js rewrites proxy to backend)
// Server-side uses direct backend URL
const API_BASE_URL_BROWSER = "";
const API_BASE_URL_SERVER =
  process.env.NEXT_PUBLIC_API_BACKEND_URL || "http://localhost:8000";

function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return API_BASE_URL_BROWSER;
  }
  return API_BASE_URL_SERVER;
}

// ── Generic fetch helper ──

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${getApiBaseUrl()}${endpoint}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string> | undefined),
  };
  // 加 Authorization（仅浏览器端；登录接口本身不需要）
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("omnitest_token");
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }
  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    // token 失效 — 清理并跳登录（fetchApi 非 React 组件，用 window.location）
    if (typeof window !== "undefined") {
      localStorage.removeItem("omnitest_token");
      localStorage.removeItem("omnitest_username");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const errorBody = await res.text();
    throw new Error(
      `API error ${res.status}: ${errorBody || res.statusText}`
    );
  }

  return res.json() as Promise<T>;
}

// Blob fetch with the same auth-header + 401-redirect semantics as fetchApi.
// Export endpoints return file downloads (not JSON), so they can't use fetchApi.
async function fetchBlob(endpoint: string): Promise<Blob> {
  const url = `${getApiBaseUrl()}${endpoint}`;
  const headers: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("omnitest_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(url, { headers });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("omnitest_token");
      localStorage.removeItem("omnitest_username");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
  return res.blob();
}

// ── Auth ──

export async function login(
  username: string,
  password: string
): Promise<{ access_token: string; username: string }> {
  // OAuth2PasswordRequestForm 需要 form-urlencoded
  const body = new URLSearchParams({ username, password });
  const url = `${getApiBaseUrl()}/api/login`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    throw new Error(`Login failed: ${res.status}`);
  }
  return res.json();
}

// ── Task 1: RAG Pipeline ──

export async function crawlDocs(url: string = "https://docs.4gaboards.com"): Promise<ApiResponse<CrawlStatus>> {
  return fetchApi<ApiResponse<CrawlStatus>>("/api/task1/crawl", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function getCrawlStatus(): Promise<CrawlStatus> {
  return fetchApi<CrawlStatus>("/api/task1/crawl/status");
}

export async function getExtractStatus(): Promise<ExtractStatus> {
  return fetchApi<ExtractStatus>("/api/task1/extract/status");
}

export async function getGenerateStatus(): Promise<GenerateStatus> {
  return fetchApi<GenerateStatus>("/api/task1/generate/status");
}

export async function extractFeatures(): Promise<ApiResponse<Feature[]>> {
  return fetchApi<ApiResponse<Feature[]>>("/api/task1/extract-features", {
    method: "POST",
  });
}

export async function generateScenarios(featureIds?: string[]): Promise<
  ApiResponse<TestScenario[]>
> {
  const body = featureIds ? JSON.stringify({ feature_ids: featureIds }) : JSON.stringify({});
  return fetchApi<ApiResponse<TestScenario[]>>(
    "/api/task1/generate-scenarios",
    { method: "POST", body }
  );
}

export async function deleteCrawlData(): Promise<ApiResponse<null>> {
  return fetchApi<ApiResponse<null>>("/api/task1/crawl", { method: "DELETE" });
}

export async function deleteFeatures(): Promise<ApiResponse<null>> {
  return fetchApi<ApiResponse<null>>("/api/task1/features", { method: "DELETE" });
}

export async function deleteScenarios(): Promise<ApiResponse<null>> {
  return fetchApi<ApiResponse<null>>("/api/task1/scenarios", { method: "DELETE" });
}

export async function getFeatures(filters?: FeatureFilters): Promise<PaginatedResponse<Feature>> {
  const params = new URLSearchParams();
  if (filters?.category) params.set("category", filters.category);
  if (filters?.search) params.set("search", filters.search);
  if (filters?.page) params.set("page", String(filters.page));
  if (filters?.page_size) params.set("page_size", String(filters.page_size));
  const qs = params.toString();
  return fetchApi<PaginatedResponse<Feature>>(`/api/task1/features${qs ? `?${qs}` : ""}`);
}

export async function getFeatureCategories(): Promise<{ success: boolean; data: string[] }> {
  return fetchApi<{ success: boolean; data: string[] }>("/api/task1/features/categories");
}

export async function getFeatureById(id: string): Promise<Feature> {
  return fetchApi<Feature>(`/api/task1/features/${id}`);
}

export async function getScenarios(filters?: ScenarioFilters): Promise<PaginatedResponse<TestScenario>> {
  const params = new URLSearchParams();
  if (filters?.feature_id) params.set("feature_id", filters.feature_id);
  if (filters?.search) params.set("search", filters.search);
  if (filters?.page) params.set("page", String(filters.page));
  if (filters?.page_size) params.set("page_size", String(filters.page_size));
  const qs = params.toString();
  return fetchApi<PaginatedResponse<TestScenario>>(`/api/task1/scenarios${qs ? `?${qs}` : ""}`);
}

export async function getScenariosByFeature(featureId: string): Promise<TestScenario[]> {
  // Backward compat for feature detail page — fetch all scenarios for one feature
  const result = await getScenarios({ feature_id: featureId, page_size: 500 });
  return result.items;
}

export async function getScenarioById(id: string): Promise<TestScenario> {
  return fetchApi<TestScenario>(`/api/task1/scenarios/${id}`);
}

// ── Task 2: Agent Execution ──

export async function executeScenario(
  scenarioId: string
): Promise<ApiResponse<ExecutionRecord>> {
  return fetchApi<ApiResponse<ExecutionRecord>>(
    `/api/task2/execute/${scenarioId}`,
    { method: "POST" }
  );
}

export async function getExecutions(filters?: ExecutionFilters): Promise<PaginatedResponse<ExecutionRecord>> {
  const params = new URLSearchParams();
  if (filters?.scenario_id) params.set("scenario_id", filters.scenario_id);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.search) params.set("search", filters.search);
  if (filters?.page) params.set("page", String(filters.page));
  if (filters?.page_size) params.set("page_size", String(filters.page_size));
  const qs = params.toString();
  return fetchApi<PaginatedResponse<ExecutionRecord>>(`/api/task2/executions${qs ? `?${qs}` : ""}`);
}

export async function getExecutionById(id: string): Promise<ExecutionRecord> {
  return fetchApi<ExecutionRecord>(`/api/task2/executions/${id}`);
}

export async function cancelExecution(
  executionId: string
): Promise<ApiResponse<null>> {
  return fetchApi<ApiResponse<null>>(
    `/api/task2/executions/${executionId}/cancel`,
    { method: "POST" }
  );
}

export async function deleteExecution(
  executionId: string
): Promise<ApiResponse<null>> {
  return fetchApi<ApiResponse<null>>(
    `/api/task2/executions/${executionId}`,
    { method: "DELETE" }
  );
}

// ── Mutation Testing ──

export async function runMutation(
  scenarioId: string,
  mutationType: MutationType
): Promise<ApiResponse<MutationResult>> {
  return fetchApi<ApiResponse<MutationResult>>(
    `/api/task2/mutation/${scenarioId}`,
    {
      method: "POST",
      body: JSON.stringify({ mutation_type: mutationType }),
    }
  );
}

export async function getMutations(filters?: MutationFilters): Promise<PaginatedResponse<MutationResult>> {
  const params = new URLSearchParams();
  if (filters?.original_scenario_id) params.set("original_scenario_id", filters.original_scenario_id);
  if (filters?.mutation_type) params.set("mutation_type", filters.mutation_type);
  if (filters?.detected_error_type) params.set("detected_error_type", filters.detected_error_type);
  if (filters?.search) params.set("search", filters.search);
  if (filters?.page) params.set("page", String(filters.page));
  if (filters?.page_size) params.set("page_size", String(filters.page_size));
  const qs = params.toString();
  return fetchApi<PaginatedResponse<MutationResult>>(`/api/task2/mutations${qs ? `?${qs}` : ""}`);
}

export async function getMutationById(id: string): Promise<MutationResult> {
  return fetchApi<MutationResult>(`/api/task2/mutations/${id}`);
}

// ── Common / Shared ──

export async function getStatus(): Promise<SystemStatus> {
  return fetchApi<SystemStatus>("/api/status");
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return fetchApi<DashboardStats>("/api/dashboard/stats");
}

export async function exportResults(format: string = "json"): Promise<Blob> {
  return fetchBlob(`/api/export?format=${format}`);
}

// ── Import/Export (per-type) ──

export interface ImportResult {
  success: boolean;
  imported_count: number;
  skipped_count?: number;
  message: string;
  results?: Record<string, unknown>;
  errors?: string[];
}

export async function exportFeatures(): Promise<Blob> {
  return fetchBlob("/api/io/export/features");
}

export async function exportScenarios(): Promise<Blob> {
  return fetchBlob("/api/io/export/scenarios");
}

export async function exportExecutions(includeScreenshots: boolean = true): Promise<Blob> {
  return fetchBlob(`/api/io/export/executions?include_screenshots=${includeScreenshots}`);
}

export async function exportBundle(includeScreenshots: boolean = true): Promise<Blob> {
  return fetchBlob(`/api/io/export/all?include_screenshots=${includeScreenshots}`);
}

export async function importFeatures(data: unknown): Promise<ImportResult> {
  return fetchApi<ImportResult>("/api/io/import/features", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function importScenarios(data: unknown): Promise<ImportResult> {
  return fetchApi<ImportResult>("/api/io/import/scenarios", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function importExecutions(data: unknown): Promise<ImportResult> {
  return fetchApi<ImportResult>("/api/io/import/executions", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function importBundle(data: unknown): Promise<ImportResult> {
  return fetchApi<ImportResult>("/api/io/import/bundle", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Screenshots ──

// ── Settings ──

export async function getSettings(): Promise<{ success: boolean; data: AppSetting[]; total: number }> {
  return fetchApi<{ success: boolean; data: AppSetting[]; total: number }>("/api/settings");
}

export async function updateSetting(key: string, value: string): Promise<{ success: boolean; data: AppSetting; message: string }> {
  return fetchApi<{ success: boolean; data: AppSetting; message: string }>(`/api/settings/${key}?value=${encodeURIComponent(value)}`, {
    method: "PUT",
  });
}

export async function getAvailableModels(): Promise<{
  success: boolean;
  data: {
    current: Record<string, string>;
    fallbacks: Record<string, string[]>;
    available_models: Record<string, string>;
  };
}> {
  return fetchApi("/api/settings/models");
}

export async function getTokenUsageSummary(
  stage?: string,
  model?: string,
  days?: number
): Promise<{ success: boolean; data: TokenUsageSummary }> {
  const params = new URLSearchParams();
  if (stage) params.set("stage", stage);
  if (model) params.set("model", model);
  if (days) params.set("days", String(days));
  return fetchApi<{ success: boolean; data: TokenUsageSummary }>(`/api/settings/token-usage/summary?${params}`);
}

export async function getTokenUsageDetail(
  filters?: TokenUsageDetailFilters
): Promise<{ success: boolean; items: TokenUsageDetail[]; total: number; page: number; page_size: number }> {
  const params = new URLSearchParams();
  if (filters?.stage) params.set("stage", filters.stage);
  if (filters?.model) params.set("model", filters.model);
  if (filters?.search) params.set("search", filters.search);
  if (filters?.page) params.set("page", String(filters.page));
  if (filters?.page_size) params.set("page_size", String(filters.page_size));
  const qs = params.toString();
  return fetchApi<{ success: boolean; items: TokenUsageDetail[]; total: number; page: number; page_size: number }>(`/api/settings/token-usage/detail${qs ? `?${qs}` : ""}`);
}

// ── Graph (Neo4j) ──

export async function getDependencyGraph(): Promise<{ success: boolean; data: DependencyGraph } | null> {
  try {
    return await fetchApi<{ success: boolean; data: DependencyGraph }>("/api/graph/dependency-graph");
  } catch {
    return null;
  }
}

export async function getFeatureCoverage(featureId: string): Promise<{ success: boolean; data: FeatureCoverage } | null> {
  try {
    return await fetchApi<{ success: boolean; data: FeatureCoverage }>(`/api/graph/feature-coverage/${featureId}`);
  } catch {
    return null;
  }
}

export async function getCoverageStats(): Promise<{ success: boolean; data: CoverageStats } | null> {
  try {
    return await fetchApi<{ success: boolean; data: CoverageStats }>("/api/graph/coverage-stats");
  } catch {
    return null;
  }
}

export function getScreenshotUrl(path: string): string {
  if (!path) return "";
  // base64 data URI — 直接作为 img src 使用
  if (path.startsWith("data:image")) return path;
  // 超长字符串（很可能是 base64 但没有 data: 前缀）— 补上前缀直接使用
  if (path.length > 200 && !path.startsWith("/") && !path.startsWith("http")) {
    return `data:image/png;base64,${path}`;
  }
  // HTTP URL — 直接使用
  if (path.startsWith("http")) return path;
  // 文件名/相对路径 → 经 Next.js rewrites 代理到后端 /api/screenshots/
  return `/screenshots/${encodeURIComponent(path)}`;
}

// ── WebSocket Connection ──

export class ExecutionWebSocket {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<(data: unknown) => void>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private maxReconnectAttempts = 5;
  private reconnectAttempts = 0;

  connect(): void {
    // 同源 WS — Next.js rewrites 代理 /ws/ 到后端
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = window.location.host;
    const token = localStorage.getItem("omnitest_token") || "";
    const wsUrl = `${wsProto}//${wsHost}/ws/executions?token=${encodeURIComponent(token)}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.emit("connected", null);
    };

    this.ws.onmessage = (event) => {
      try {
        const data: WebSocketEvent = JSON.parse(event.data);
        this.emit(data.type, data);
        this.emit("message", data);
      } catch {
        // ignore non-JSON messages
      }
    };

    this.ws.onclose = () => {
      this.emit("disconnected", null);
      this.attemptReconnect();
    };

    this.ws.onerror = () => {
      this.emit("error", null);
    };
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, 2000 * this.reconnectAttempts);
  }

  on(eventType: string, callback: (data: unknown) => void): void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);
  }

  off(eventType: string, callback: (data: unknown) => void): void {
    this.listeners.get(eventType)?.delete(callback);
  }

  private emit(eventType: string, data: unknown): void {
    this.listeners.get(eventType)?.forEach((cb) => cb(data));
  }

  disconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
    this.listeners.clear();
  }
}