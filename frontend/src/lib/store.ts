import { create } from "zustand";
import { AgentStatus, MutationType } from "./types";
import type {
  Feature,
  TestScenario,
  ExecutionRecord,
  MutationResult,
  DashboardStats,
  SystemStatus,
  WebSocketEvent,
  StepProgress,
  CrawlStatus,
  ExtractStatus,
  GenerateStatus,
  AppSetting,
  TokenUsageSummary,
  FeatureFilters,
  ScenarioFilters,
  ExecutionFilters,
  MutationFilters,
} from "./types";
import * as api from "./api";
import { ExecutionWebSocket } from "./api";

interface AppState {
  // Paginated data
  features: Feature[];
  featuresTotal: number;
  featuresPage: number;
  scenarios: TestScenario[];
  scenariosTotal: number;
  scenariosPage: number;
  executions: ExecutionRecord[];
  executionsTotal: number;
  executionsPage: number;
  mutations: MutationResult[];
  mutationsTotal: number;
  mutationsPage: number;

  // Unpaginated full lists (for tree view, dropdowns, stats)
  allFeatures: Feature[];
  allScenarios: TestScenario[];

  // Active filter params
  featureFilters: FeatureFilters;
  scenarioFilters: ScenarioFilters;
  executionFilters: ExecutionFilters;
  mutationFilters: MutationFilters;

  // Other data
  dashboardStats: DashboardStats | null;
  systemStatus: SystemStatus | null;
  crawlStatus: CrawlStatus | null;
  extractStatus: ExtractStatus | null;
  generateStatus: GenerateStatus | null;
  settings: AppSetting[];
  tokenUsageSummary: TokenUsageSummary | null;
  featureCategories: string[];

  // Loading states
  loadingFeatures: boolean;
  loadingScenarios: boolean;
  loadingExecutions: boolean;
  loadingMutations: boolean;
  loadingStats: boolean;
  loadingStatus: boolean;
  loadingSettings: boolean;
  loadingTokenUsage: boolean;
  crawling: boolean;
  extracting: boolean;
  generating: boolean;

  // Errors
  errorFeatures: string | null;
  errorScenarios: string | null;
  errorExecutions: string | null;
  errorMutations: string | null;

  // WebSocket
  wsConnected: boolean;
  ws: ExecutionWebSocket | null;

  // Step progress (real-time per-step updates via WebSocket)
  stepProgress: StepProgress | null;

  // Actions
  fetchFeatures: (filters?: FeatureFilters) => Promise<void>;
  fetchAllFeatures: () => Promise<void>;
  fetchScenarios: (filters?: ScenarioFilters) => Promise<void>;
  fetchAllScenarios: () => Promise<void>;
  fetchExecutions: (filters?: ExecutionFilters) => Promise<void>;
  fetchMutations: (filters?: MutationFilters) => Promise<void>;
  fetchFeatureCategories: () => Promise<void>;
  fetchDashboardStats: () => Promise<void>;
  fetchSystemStatus: () => Promise<void>;
  fetchSettings: () => Promise<void>;
  updateSetting: (key: string, value: string) => Promise<void>;
  fetchTokenUsageSummary: (stage?: string, model?: string, days?: number) => Promise<void>;
  startCrawl: () => Promise<void>;
  startExtractFeatures: () => Promise<void>;
  startGenerateScenarios: () => Promise<void>;
  executeScenario: (scenarioId: string) => Promise<void>;
  runMutation: (scenarioId: string, mutationType: MutationType) => Promise<void>;
  cancelExecution: (executionId: string) => Promise<void>;
  deleteCrawlData: () => Promise<void>;
  deleteFeatures: () => Promise<void>;
  deleteScenarios: () => Promise<void>;
  initWebSocket: () => void;
  disconnectWebSocket: () => void;
  handleWsEvent: (event: WebSocketEvent) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Initial state
  features: [],
  featuresTotal: 0,
  featuresPage: 1,
  scenarios: [],
  scenariosTotal: 0,
  scenariosPage: 1,
  executions: [],
  executionsTotal: 0,
  executionsPage: 1,
  mutations: [],
  mutationsTotal: 0,
  mutationsPage: 1,

  allFeatures: [],
  allScenarios: [],

  featureFilters: {},
  scenarioFilters: {},
  executionFilters: {},
  mutationFilters: {},
  featureCategories: [],

  dashboardStats: null,
  systemStatus: null,
  crawlStatus: null,
  extractStatus: null,
  generateStatus: null,
  settings: [],
  tokenUsageSummary: null,

  loadingFeatures: false,
  loadingScenarios: false,
  loadingExecutions: false,
  loadingMutations: false,
  loadingStats: false,
  loadingStatus: false,
  loadingSettings: false,
  loadingTokenUsage: false,
  crawling: false,
  extracting: false,
  generating: false,

  errorFeatures: null,
  errorScenarios: null,
  errorExecutions: null,
  errorMutations: null,

  wsConnected: false,
  ws: null,
  stepProgress: null,

  // Actions
  fetchFeatures: async (filters?: FeatureFilters) => {
    const effectiveFilters = { ...get().featureFilters, ...filters, page_size: 20 };
    if (filters) set({ featureFilters: effectiveFilters });
    set({ loadingFeatures: true, errorFeatures: null });
    try {
      const result = await api.getFeatures(effectiveFilters);
      set({
        features: result.items,
        featuresTotal: result.total,
        featuresPage: result.page,
        loadingFeatures: false,
      });
    } catch (e) {
      set({ errorFeatures: e instanceof Error ? e.message : "Failed", loadingFeatures: false });
    }
  },

  fetchAllFeatures: async () => {
    try {
      const result = await api.getFeatures({ page_size: 500 });
      set({ allFeatures: result.items });
    } catch { /* silent */ }
  },

  fetchScenarios: async (filters?: ScenarioFilters) => {
    const effectiveFilters = { ...get().scenarioFilters, ...filters, page_size: 20 };
    if (filters) set({ scenarioFilters: effectiveFilters });
    set({ loadingScenarios: true, errorScenarios: null });
    try {
      const result = await api.getScenarios(effectiveFilters);
      set({
        scenarios: result.items,
        scenariosTotal: result.total,
        scenariosPage: result.page,
        loadingScenarios: false,
      });
    } catch (e) {
      set({ errorScenarios: e instanceof Error ? e.message : "Failed", loadingScenarios: false });
    }
  },

  fetchAllScenarios: async () => {
    try {
      const result = await api.getScenarios({ page_size: 500 });
      set({ allScenarios: result.items });
    } catch { /* silent */ }
  },

  fetchExecutions: async (filters?: ExecutionFilters) => {
    const effectiveFilters = { ...get().executionFilters, ...filters, page_size: 20 };
    if (filters) set({ executionFilters: effectiveFilters });
    set({ loadingExecutions: true, errorExecutions: null });
    try {
      const result = await api.getExecutions(effectiveFilters);
      set({
        executions: result.items,
        executionsTotal: result.total,
        executionsPage: result.page,
        loadingExecutions: false,
      });
    } catch (e) {
      set({ errorExecutions: e instanceof Error ? e.message : "Failed", loadingExecutions: false });
    }
  },

  fetchMutations: async (filters?: MutationFilters) => {
    const effectiveFilters = { ...get().mutationFilters, ...filters, page_size: 20 };
    if (filters) set({ mutationFilters: effectiveFilters });
    set({ loadingMutations: true, errorMutations: null });
    try {
      const result = await api.getMutations(effectiveFilters);
      set({
        mutations: result.items,
        mutationsTotal: result.total,
        mutationsPage: result.page,
        loadingMutations: false,
      });
    } catch (e) {
      set({ errorMutations: e instanceof Error ? e.message : "Failed", loadingMutations: false });
    }
  },

  fetchFeatureCategories: async () => {
    try {
      const result = await api.getFeatureCategories();
      set({ featureCategories: result.data });
    } catch { /* silent */ }
  },

  fetchDashboardStats: async () => {
    set({ loadingStats: true });
    try {
      const stats = await api.getDashboardStats();
      set({ dashboardStats: stats, loadingStats: false });
    } catch {
      set({ loadingStats: false });
    }
  },

  fetchSystemStatus: async () => {
    set({ loadingStatus: true });
    try {
      const status = await api.getStatus();
      set({
        systemStatus: status,
        loadingStatus: false,
        // Also update pipeline step status from system status
        crawlStatus: (status.pipeline?.crawl as CrawlStatus | null) ?? null,
        extractStatus: (status.pipeline?.extract as ExtractStatus | null) ?? null,
        generateStatus: (status.pipeline?.generate as GenerateStatus | null) ?? null,
      });
    } catch {
      set({ loadingStatus: false });
    }
  },

  fetchSettings: async () => {
    set({ loadingSettings: true });
    try {
      const result = await api.getSettings();
      set({ settings: result.data, loadingSettings: false });
    } catch {
      set({ loadingSettings: false });
    }
  },

  updateSetting: async (key: string, value: string) => {
    try {
      await api.updateSetting(key, value);
      // Refresh settings after update
      const result = await api.getSettings();
      set({ settings: result.data });
    } catch (err) {
      console.error(`Failed to update setting '${key}':`, err);
    }
  },

  fetchTokenUsageSummary: async (stage?: string, model?: string, days?: number) => {
    set({ loadingTokenUsage: true });
    try {
      const result = await api.getTokenUsageSummary(stage, model, days);
      set({ tokenUsageSummary: result.data, loadingTokenUsage: false });
    } catch {
      set({ loadingTokenUsage: false });
    }
  },

  startCrawl: async () => {
    set({ crawling: true });
    try {
      // Fire the crawl request (backend runs it async)
      api.crawlDocs().catch(() => {}); // don't block on result
      // Poll status until completed/failed
      while (true) {
        try {
          const status = await api.getCrawlStatus();
          set({ crawlStatus: status });
          if (status.status === "completed" || status.status === "failed") break;
        } catch {
          // ignore polling errors
        }
        get().fetchSystemStatus(); // refresh data counts
        await new Promise((r) => setTimeout(r, 1500));
      }
      set({ crawling: false });
      get().fetchSystemStatus();
      get().fetchDashboardStats();
    } catch (e) {
      set({ crawling: false });
      throw e;
    }
  },

  startExtractFeatures: async () => {
    set({ extracting: true });
    try {
      // Fire the extract request
      api.extractFeatures().catch(() => {});
      // Poll status until completed/failed
      while (true) {
        try {
          const status = await api.getExtractStatus();
          set({ extractStatus: status });
          if (status.status === "completed" || status.status === "failed") break;
        } catch {
          // ignore polling errors
        }
        get().fetchSystemStatus();
        await new Promise((r) => setTimeout(r, 1500));
      }
      set({ extracting: false });
      get().fetchFeatures();
      get().fetchDashboardStats();
    } catch (e) {
      set({ extracting: false });
      throw e;
    }
  },

  startGenerateScenarios: async () => {
    set({ generating: true });
    try {
      // Fire the generate request
      api.generateScenarios().catch(() => {});
      // Poll status until completed/failed
      while (true) {
        try {
          const status = await api.getGenerateStatus();
          set({ generateStatus: status });
          if (status.status === "completed" || status.status === "failed") break;
        } catch {
          // ignore polling errors
        }
        get().fetchSystemStatus();
        await new Promise((r) => setTimeout(r, 1500));
      }
      set({ generating: false });
      get().fetchScenarios();
      get().fetchDashboardStats();
    } catch (e) {
      set({ generating: false });
      throw e;
    }
  },

  executeScenario: async (scenarioId: string) => {
    try {
      const result = await api.executeScenario(scenarioId);
      if (result.data) {
        set((state) => ({
          executions: [result.data!, ...state.executions],
        }));
      }
      // Refresh stats; execution updates will flow via WebSocket
      get().fetchDashboardStats();
    } catch (e) {
      throw e;
    }
  },

  runMutation: async (scenarioId: string, mutationType: MutationType) => {
    try {
      const result = await api.runMutation(scenarioId, mutationType);
      if (result.data) {
        set((state) => ({
          mutations: [result.data!, ...state.mutations],
        }));
      }
      get().fetchDashboardStats();
    } catch (e) {
      throw e;
    }
  },

  deleteCrawlData: async () => {
    if (!window.confirm("确定要删除所有爬取数据吗？此操作不可恢复。")) {
      return;
    }
    try {
      await api.deleteCrawlData();
      set({ crawlStatus: null });
      get().fetchSystemStatus();
    } catch (e) {
      throw e;
    }
  },

  deleteFeatures: async () => {
    if (!window.confirm("确定要删除所有特征数据吗？此操作不可恢复。")) {
      return;
    }
    try {
      await api.deleteFeatures();
      set({ extractStatus: null, features: [] });
      get().fetchDashboardStats();
    } catch (e) {
      throw e;
    }
  },

  deleteScenarios: async () => {
    if (!window.confirm("确定要删除所有场景数据吗？此操作不可恢复。")) {
      return;
    }
    try {
      await api.deleteScenarios();
      set({ generateStatus: null, scenarios: [] });
      get().fetchDashboardStats();
    } catch (e) {
      throw e;
    }
  },

  cancelExecution: async (executionId: string) => {
    try {
      await api.cancelExecution(executionId);
      set((state) => ({
        executions: state.executions.map((ex) =>
          ex.id === executionId
            ? { ...ex, status: AgentStatus.FAILED as AgentStatus, failure_reason: "Cancelled by user" }
            : ex
        ),
      }));
    } catch (e) {
      throw e;
    }
  },

  initWebSocket: () => {
    const ws = new ExecutionWebSocket();
    ws.on("connected", () => set({ wsConnected: true }));
    ws.on("disconnected", () => set({ wsConnected: false }));
    ws.on("message", (data) => {
      if (data) get().handleWsEvent(data as WebSocketEvent);
    });
    ws.connect();
    set({ ws });
  },

  disconnectWebSocket: () => {
    const ws = get().ws;
    if (ws) {
      ws.disconnect();
      set({ ws: null, wsConnected: false });
    }
  },

  handleWsEvent: (event: WebSocketEvent) => {
    switch (event.type) {
      case "execution_started":
        get().fetchExecutions();
        break;
      case "step_progress":
        // Update real-time step progress indicator
        set({ stepProgress: {
          execution_id: event.execution_id,
          step_number: event.step_number,
          total_steps: event.total_steps,
          action_tool: event.action_tool,
          success: event.success,
        }});
        break;
      case "step_completed":
        // Refresh from API to get updated steps with screenshots
        get().fetchExecutions();
        break;
      case "verification_completed":
        get().fetchExecutions();
        break;
      case "reflection_started":
        set((state) => ({
          executions: state.executions.map((ex) =>
            ex.id === event.execution_id
              ? { ...ex, retry_count: event.retry_count, status: AgentStatus.REFLECTING }
              : ex
          ),
        }));
        break;
      case "execution_completed":
        // Refresh full execution data from API (plan, steps, screenshots now available)
        // Clear step progress since execution is done
        set({ stepProgress: null });
        get().fetchExecutions();
        get().fetchDashboardStats();
        break;
      case "mutation_completed":
        set((state) => ({
          mutations: [event.mutation_result, ...state.mutations],
        }));
        get().fetchDashboardStats();
        break;
    }
  },
}));