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
  CrawlStatus,
  ExtractStatus,
  GenerateStatus,
  AppSetting,
  TokenUsageSummary,
} from "./types";
import * as api from "./api";
import { ExecutionWebSocket } from "./api";

interface AppState {
  // Data
  features: Feature[];
  scenarios: TestScenario[];
  executions: ExecutionRecord[];
  mutations: MutationResult[];
  dashboardStats: DashboardStats | null;
  systemStatus: SystemStatus | null;
  crawlStatus: CrawlStatus | null;
  extractStatus: ExtractStatus | null;
  generateStatus: GenerateStatus | null;
  settings: AppSetting[];
  tokenUsageSummary: TokenUsageSummary | null;

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

  // Actions
  fetchFeatures: () => Promise<void>;
  fetchScenarios: () => Promise<void>;
  fetchExecutions: () => Promise<void>;
  fetchMutations: () => Promise<void>;
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
  scenarios: [],
  executions: [],
  mutations: [],
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

  // Actions
  fetchFeatures: async () => {
    set({ loadingFeatures: true, errorFeatures: null });
    try {
      const features = await api.getFeatures();
      set({ features, loadingFeatures: false });
    } catch (e) {
      set({
        errorFeatures: e instanceof Error ? e.message : "Failed to fetch features",
        loadingFeatures: false,
      });
    }
  },

  fetchScenarios: async () => {
    set({ loadingScenarios: true, errorScenarios: null });
    try {
      const scenarios = await api.getScenarios();
      set({ scenarios, loadingScenarios: false });
    } catch (e) {
      set({
        errorScenarios: e instanceof Error ? e.message : "Failed to fetch scenarios",
        loadingScenarios: false,
      });
    }
  },

  fetchExecutions: async () => {
    set({ loadingExecutions: true, errorExecutions: null });
    try {
      const executions = await api.getExecutions();
      set({ executions, loadingExecutions: false });
    } catch (e) {
      set({
        errorExecutions: e instanceof Error ? e.message : "Failed to fetch executions",
        loadingExecutions: false,
      });
    }
  },

  fetchMutations: async () => {
    set({ loadingMutations: true, errorMutations: null });
    try {
      const mutations = await api.getMutations();
      set({ mutations, loadingMutations: false });
    } catch (e) {
      set({
        errorMutations: e instanceof Error ? e.message : "Failed to fetch mutations",
        loadingMutations: false,
      });
    }
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
    try {
      await api.deleteCrawlData();
      set({ crawlStatus: null });
      get().fetchSystemStatus();
    } catch (e) {
      throw e;
    }
  },

  deleteFeatures: async () => {
    try {
      await api.deleteFeatures();
      set({ extractStatus: null, features: [] });
      get().fetchDashboardStats();
    } catch (e) {
      throw e;
    }
  },

  deleteScenarios: async () => {
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