"use client";

import { useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  GitBranch,
  ClipboardList,
  PlayCircle,
  Bug,
  Globe,
  Sparkles,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Loader,
  Eye,
  RefreshCw,
  LayoutDashboard,
  Trash2,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { formatDateTime } from "@/lib/format";
import { AgentStatus } from "@/lib/types";
import { useI18n } from "@/lib/useI18n";
import Link from "next/link";

function StatCard({
  title,
  value,
  icon: Icon,
  description,
  loading,
}: {
  title: string;
  value: number | string;
  icon: React.ElementType;
  description: string;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <div className="text-2xl font-bold">{value}</div>
        )}
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </CardContent>
    </Card>
  );
}

// Sub-step label map
const STEP_LABELS: Record<string, string> = {
  downloading: "quickActions.step.downloading",
  parsing: "quickActions.step.parsing",
  storing: "quickActions.step.storing",
  retrieving: "quickActions.step.retrieving",
  llm_call: "quickActions.step.llm_call",
  saving: "quickActions.step.saving",
  completed: "quickActions.step.saving", // last step done
};

function StepProgress({
  status,
  step,
  isActive,
  dataCount,
  dataLabel,
  onDelete,
  deleteLabel,
}: {
  status: string;
  step: string;
  isActive: boolean;
  dataCount: number | undefined;
  dataLabel: string;
  onDelete?: () => void;
  deleteLabel?: string;
}) {
  const { t } = useI18n();

  // Progress percentage based on sub-step
  const progressMap: Record<string, number> = {
    downloading: 20,
    parsing: 50,
    storing: 80,
    retrieving: 20,
    llm_call: 60,
    saving: 90,
    completed: 100,
  };
  const progress = isActive ? (progressMap[step] ?? 30) : (status === "completed" ? 100 : 0);

  return (
    <div className="space-y-1">
      {isActive && step && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-blue-600">
            {t(STEP_LABELS[step] ?? step)}
          </p>
          <Progress value={progress} className="h-1.5" />
        </div>
      )}
      {!isActive && status !== "crawling" && status !== "extracting" && status !== "generating" && (
        (dataCount ?? 0) > 0 ? (
          <p className="text-xs text-muted-foreground">
            {dataCount} {dataLabel}
          </p>
        ) : status === "failed" ? (
          <p className="text-xs text-red-500">Failed</p>
        ) : (
          <p className="text-xs text-muted-foreground">-</p>
        )
      )}
      {status === "completed" && !isActive && onDelete && deleteLabel && (
        <Button onClick={onDelete} variant="destructive" size="xs" className="gap-1 w-full mt-1">
          <Trash2 className="h-3 w-3" />
          {deleteLabel}
        </Button>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const {
    dashboardStats,
    loadingStats,
    executions,
    loadingExecutions,
    crawling,
    extracting,
    generating,
    crawlStatus,
    extractStatus,
    generateStatus,
    fetchDashboardStats,
    fetchExecutions,
    startCrawl,
    startExtractFeatures,
    startGenerateScenarios,
    deleteCrawlData,
    deleteFeatures,
    deleteScenarios,
    initWebSocket,
  } = useAppStore();

  const { t } = useI18n();

  useEffect(() => {
    fetchDashboardStats();
    fetchExecutions();
    initWebSocket();
  }, []);

  // Data counts from dashboard stats (fast endpoint, loaded on init)
  const crawledPages = dashboardStats?.crawled_pages ?? 0;
  const chromadbChunks = dashboardStats?.chromadb_chunks ?? 0;
  const featureCount = dashboardStats?.feature_count ?? 0;
  const scenarioCount = dashboardStats?.scenario_count ?? 0;

  // Pipeline status: prefer polling status (real-time during execution),
  // fallback to dashboard stats (available on initial page load)
  const crawlPipeline = crawlStatus ?? dashboardStats?.pipeline?.crawl ?? null;
  const extractPipeline = extractStatus ?? dashboardStats?.pipeline?.extract ?? null;
  const generatePipeline = generateStatus ?? dashboardStats?.pipeline?.generate ?? null;

  // Enable buttons based on existing data (not just status)
  const canExtract = crawling ? false : (crawledPages > 0 || (crawlPipeline?.status === "completed"));
  const canGenerate = extracting ? false : (featureCount > 0 || (extractPipeline?.status === "completed"));

  const recentExecutions = executions.slice(0, 10);

  function statusIcon(status: AgentStatus) {
    const cls = "h-3 w-3";
    switch (status) {
      case AgentStatus.COMPLETED:
        return <CheckCircle2 className={`${cls} text-green-500`} />;
      case AgentStatus.FAILED:
        return <XCircle className={`${cls} text-red-500`} />;
      case AgentStatus.EXECUTING:
        return <PlayCircle className={`${cls} text-blue-500`} />;
      case AgentStatus.PLANNING:
        return <Loader className={`${cls} text-blue-500 animate-spin`} />;
      case AgentStatus.VERIFYING:
        return <Eye className={`${cls} text-yellow-500`} />;
      case AgentStatus.REFLECTING:
        return <RefreshCw className={`${cls} text-orange-500`} />;
      default:
        return <Clock className={`${cls} text-muted-foreground`} />;
    }
  }

  function statusBadge(status: AgentStatus) {
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      [AgentStatus.PENDING]: "outline",
      [AgentStatus.PLANNING]: "secondary",
      [AgentStatus.EXECUTING]: "secondary",
      [AgentStatus.VERIFYING]: "secondary",
      [AgentStatus.REFLECTING]: "secondary",
      [AgentStatus.COMPLETED]: "default",
      [AgentStatus.FAILED]: "destructive",
    };
    const statusKey = status.toLowerCase() as string;
    return (
      <Badge variant={variants[status] || "outline"} className="gap-1">
        {statusIcon(status)}
        {t(`status.${statusKey}`)}
      </Badge>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <LayoutDashboard className="h-6 w-6 text-blue-500" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t("dashboard.title")}</h2>
          <p className="text-muted-foreground">{t("dashboard.subtitle")}</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title={t("stat.features")}
          value={dashboardStats?.feature_count ?? 0}
          icon={GitBranch}
          description={t("stat.features.desc")}
          loading={loadingStats}
        />
        <StatCard
          title={t("stat.scenarios")}
          value={dashboardStats?.scenario_count ?? 0}
          icon={ClipboardList}
          description={t("stat.scenarios.desc")}
          loading={loadingStats}
        />
        <StatCard
          title={t("stat.successRate")}
          value={dashboardStats ? `${(dashboardStats.success_rate ?? 0).toFixed(1)}%` : "0%"}
          icon={PlayCircle}
          description={t("stat.successRate.desc")}
          loading={loadingStats}
        />
        <StatCard
          title={t("stat.mutations")}
          value={dashboardStats?.mutation_count ?? 0}
          icon={Bug}
          description={t("stat.mutations.desc")}
          loading={loadingStats}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("quickActions.title")}</CardTitle>
          <CardDescription>{t("quickActions.desc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 md:grid-cols-3">
            {/* Step 1: Crawl */}
            <div className="flex flex-col gap-3 p-4 rounded-lg border bg-card">
              <div className="flex items-center gap-2">
                <div className={`flex items-center justify-center w-8 h-8 rounded-full border-2 ${
                  crawling ? "border-blue-500 bg-blue-50" :
                  crawlPipeline?.status === "completed" ? "border-green-500 bg-green-50" :
                  crawlPipeline?.status === "failed" ? "border-red-500 bg-red-50" :
                  crawledPages > 0 ? "border-green-500 bg-green-50" :
                  "border-muted bg-muted/50"
                }`}>
                  {crawling ? <Loader2 className="h-4 w-4 animate-spin text-blue-500" /> :
                   (crawlPipeline?.status === "completed" || crawledPages > 0) ? <CheckCircle2 className="h-4 w-4 text-green-500" /> :
                   crawlPipeline?.status === "failed" ? <XCircle className="h-4 w-4 text-red-500" /> :
                   <Globe className="h-4 w-4 text-muted-foreground" />}
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold">{t("quickActions.crawl")}</h3>
                  {crawledPages > 0 && !crawling && (
                    <p className="text-xs text-muted-foreground">
                      {crawledPages} {t("quickActions.crawlPages")}
                      {chromadbChunks > 0 && ` · ${chromadbChunks} ${t("quickActions.chunksStored")}`}
                    </p>
                  )}
                </div>
              </div>
              <Button
                onClick={() => startCrawl()}
                disabled={crawling}
                variant={crawledPages > 0 ? "outline" : "default"}
                className="gap-2"
              >
                {crawling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
                {crawling ? t("quickActions.crawling") : t("quickActions.crawl")}
              </Button>
              <StepProgress
                status={crawlPipeline?.status ?? "idle"}
                step={crawlPipeline?.step ?? ""}
                isActive={crawling}
                dataCount={crawlPipeline?.pages_crawled ?? crawledPages}
                dataLabel={t("quickActions.pages")}
                onDelete={crawlPipeline?.status === "completed" ? deleteCrawlData : undefined}
                deleteLabel={t("quickActions.deleteCrawl")}
              />
            </div>

            {/* Step 2: Extract */}
            <div className="flex flex-col gap-3 p-4 rounded-lg border bg-card">
              <div className="flex items-center gap-2">
                <div className={`flex items-center justify-center w-8 h-8 rounded-full border-2 ${
                  extracting ? "border-blue-500 bg-blue-50" :
                  extractPipeline?.status === "completed" ? "border-green-500 bg-green-50" :
                  extractPipeline?.status === "failed" ? "border-red-500 bg-red-50" :
                  featureCount > 0 ? "border-green-500 bg-green-50" :
                  "border-muted bg-muted/50"
                }`}>
                  {extracting ? <Loader2 className="h-4 w-4 animate-spin text-blue-500" /> :
                   (extractPipeline?.status === "completed" || featureCount > 0) ? <CheckCircle2 className="h-4 w-4 text-green-500" /> :
                   extractPipeline?.status === "failed" ? <XCircle className="h-4 w-4 text-red-500" /> :
                   <Sparkles className="h-4 w-4 text-muted-foreground" />}
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold">{t("quickActions.extract")}</h3>
                  {featureCount > 0 && !extracting && (
                    <p className="text-xs text-muted-foreground">
                      {featureCount} {t("quickActions.features")}
                    </p>
                  )}
                </div>
              </div>
              <Button
                onClick={() => startExtractFeatures()}
                disabled={extracting || !canExtract}
                variant={featureCount > 0 ? "outline" : "secondary"}
                className="gap-2"
              >
                {extracting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {extracting ? t("quickActions.extracting") : t("quickActions.extract")}
              </Button>
              <StepProgress
                status={extractPipeline?.status ?? "idle"}
                step={extractPipeline?.step ?? ""}
                isActive={extracting}
                dataCount={extractPipeline?.features_extracted ?? featureCount}
                dataLabel={t("quickActions.features")}
                onDelete={extractPipeline?.status === "completed" ? deleteFeatures : undefined}
                deleteLabel={t("quickActions.deleteFeatures")}
              />
            </div>

            {/* Step 3: Generate */}
            <div className="flex flex-col gap-3 p-4 rounded-lg border bg-card">
              <div className="flex items-center gap-2">
                <div className={`flex items-center justify-center w-8 h-8 rounded-full border-2 ${
                  generating ? "border-blue-500 bg-blue-50" :
                  generatePipeline?.status === "completed" ? "border-green-500 bg-green-50" :
                  generatePipeline?.status === "failed" ? "border-red-500 bg-red-50" :
                  scenarioCount > 0 ? "border-green-500 bg-green-50" :
                  "border-muted bg-muted/50"
                }`}>
                  {generating ? <Loader2 className="h-4 w-4 animate-spin text-blue-500" /> :
                   (generatePipeline?.status === "completed" || scenarioCount > 0) ? <CheckCircle2 className="h-4 w-4 text-green-500" /> :
                   generatePipeline?.status === "failed" ? <XCircle className="h-4 w-4 text-red-500" /> :
                   <FileText className="h-4 w-4 text-muted-foreground" />}
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-semibold">{t("quickActions.generate")}</h3>
                  {scenarioCount > 0 && !generating && (
                    <p className="text-xs text-muted-foreground">
                      {scenarioCount} {t("quickActions.scenarios")}
                    </p>
                  )}
                </div>
              </div>
              <Button
                onClick={() => startGenerateScenarios()}
                disabled={generating || !canGenerate}
                variant={scenarioCount > 0 ? "outline" : "secondary"}
                className="gap-2"
              >
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                {generating ? t("quickActions.generating") : t("quickActions.generate")}
              </Button>
              <StepProgress
                status={generatePipeline?.status ?? "idle"}
                step={generatePipeline?.step ?? ""}
                isActive={generating}
                dataCount={generatePipeline?.scenarios_generated ?? scenarioCount}
                dataLabel={t("quickActions.scenarios")}
                onDelete={generatePipeline?.status === "completed" ? deleteScenarios : undefined}
                deleteLabel={t("quickActions.deleteScenarios")}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("recentExecutions.title")}</CardTitle>
          <CardDescription>{t("recentExecutions.desc")}</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingExecutions ? (
            <div className="space-y-2">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-10 w-full" />))}</div>
          ) : recentExecutions.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">{t("recentExecutions.empty")}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[140px]">{t("table.id")}</TableHead>
                  <TableHead>{t("table.scenario")}</TableHead>
                  <TableHead>{t("table.status")}</TableHead>
                  <TableHead>{t("table.result")}</TableHead>
                  <TableHead>{t("table.retries")}</TableHead>
                  <TableHead>{t("table.started")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentExecutions.map((ex) => (
                  <TableRow key={ex.id}>
                    <TableCell className="font-mono text-xs">
                      <Link href={`/executions/${ex.id}`} className="hover:underline" title={ex.id}>{ex.id.length > 17 ? ex.id.slice(0, 17) + "…" : ex.id}</Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/scenarios/${ex.scenario_id}`} className="hover:underline" title={`${ex.scenario_id}: ${ex.scenario_name || ex.scenario_id}`}>
                        {ex.scenario_name || ex.scenario_id}
                      </Link>
                    </TableCell>
                    <TableCell>{statusBadge(ex.status)}</TableCell>
                    <TableCell>
                      {ex.final_result ? (
                        <Badge variant={ex.final_result === "pass" ? "default" : "destructive"}>
                          {ex.final_result === "pass" ? t("executions.detail.pass") : t("executions.detail.fail")}
                        </Badge>
                      ) : (
                        <Badge variant="outline">-</Badge>
                      )}
                    </TableCell>
                    <TableCell>{ex.retry_count}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{ex.started_at ? formatDateTime(ex.started_at) : "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}