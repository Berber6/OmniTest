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
  DependencyGraph,
  FeatureCoverage,
  CoverageStats,
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
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const errorBody = await res.text();
    throw new Error(
      `API error ${res.status}: ${errorBody || res.statusText}`
    );
  }

  return res.json() as Promise<T>;
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

export async function getFeatures(): Promise<Feature[]> {
  return fetchApi<Feature[]>("/api/task1/features");
}

export async function getFeatureById(id: string): Promise<Feature> {
  return fetchApi<Feature>(`/api/task1/features/${id}`);
}

export async function getScenarios(): Promise<TestScenario[]> {
  return fetchApi<TestScenario[]>("/api/task1/scenarios");
}

export async function getScenariosByFeature(
  featureId: string
): Promise<TestScenario[]> {
  return fetchApi<TestScenario[]>(
    `/api/task1/scenarios?feature_id=${featureId}`
  );
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

export async function getExecutions(): Promise<ExecutionRecord[]> {
  return fetchApi<ExecutionRecord[]>("/api/task2/executions");
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

export async function getMutations(): Promise<MutationResult[]> {
  return fetchApi<MutationResult[]>("/api/task2/mutations");
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
  const url = `${getApiBaseUrl()}/api/export?format=${format}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  return res.blob();
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
  const res = await fetch(`${getApiBaseUrl()}/api/io/export/features`);
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  return res.blob();
}

export async function exportScenarios(): Promise<Blob> {
  const res = await fetch(`${getApiBaseUrl()}/api/io/export/scenarios`);
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  return res.blob();
}

export async function exportExecutions(includeScreenshots: boolean = true): Promise<Blob> {
  const res = await fetch(`${getApiBaseUrl()}/api/io/export/executions?include_screenshots=${includeScreenshots}`);
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  return res.blob();
}

export async function exportBundle(includeScreenshots: boolean = true): Promise<Blob> {
  const res = await fetch(`${getApiBaseUrl()}/api/io/export/all?include_screenshots=${includeScreenshots}`);
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  return res.blob();
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
  return fetchApi<{ success: boolean; data: AppSetting[]; total: number }>("/api/settings/");
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
  stage?: string,
  model?: string,
  limit?: number
): Promise<{ success: boolean; data: TokenUsageDetail[]; total: number }> {
  const params = new URLSearchParams();
  if (stage) params.set("stage", stage);
  if (model) params.set("model", model);
  if (limit) params.set("limit", String(limit));
  return fetchApi<{ success: boolean; data: TokenUsageDetail[]; total: number }>(`/api/settings/token-usage/detail?${params}`);
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
  // 相对文件路径 — 通过 Nginx /screenshots/ 直接 serve 或 fallback 到后端 API
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
    // Nginx 反向代理: /ws/ 代理到后端 8000，无需直连后端端口
    // 无 Nginx 时（开发环境）: Next.js rewrite 无法代理 WS，需直连 8000
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = window.location.host; // includes port if non-standard
    const explicitPort = window.location.port;
    // 通过 Nginx (8080) 或标准端口访问时用同源 WS；3000 时直连后端 8000
    const useProxy = !explicitPort || explicitPort === "8080" || explicitPort === "80" || explicitPort === "443";
    const wsUrl = useProxy
      ? `${wsProto}//${wsHost}/ws/executions`
      : `${wsProto}//${window.location.hostname}:8000/ws/executions`;
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