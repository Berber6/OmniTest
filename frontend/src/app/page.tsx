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
  ArrowRight,
  Trash2,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
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
        {/* Dashboard icon */}
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
          <div className="flex items-center gap-0">
            {/* Step 1: Crawl */}
            <div className="flex flex-col items-center gap-2 min-w-[160px]">
              <div className={`flex items-center justify-center w-10 h-10 rounded-full border-2 ${
                crawling ? "border-blue-500 bg-blue-50" :
                crawlStatus?.status === "completed" ? "border-green-500 bg-green-50" :
                crawlStatus?.status === "failed" ? "border-red-500 bg-red-50" :
                "border-muted bg-muted/50"
              }`}>
                {crawling ? <Loader2 className="h-5 w-5 animate-spin text-blue-500" /> :
                 crawlStatus?.status === "completed" ? <CheckCircle2 className="h-5 w-5 text-green-500" /> :
                 crawlStatus?.status === "failed" ? <XCircle className="h-5 w-5 text-red-500" /> :
                 <Globe className="h-5 w-5 text-muted-foreground" />}
              </div>
              <Button onClick={() => startCrawl()} disabled={crawling} variant={crawlStatus?.status === "completed" ? "outline" : "default"} className="gap-2 w-full">
                {crawling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
                {t("quickActions.crawl")}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                {crawling ? `${crawlStatus?.pages_crawled ?? 0}/${crawlStatus?.total_pages ?? "..."}` :
                 crawlStatus?.status === "completed" ? `${crawlStatus?.pages_crawled ?? 0} pages` :
                 crawlStatus?.status === "failed" ? `Failed: ${crawlStatus?.error ?? ""}` :
                 ""}
              </p>
              {crawlStatus?.status === "completed" && !crawling && (
                <Button onClick={() => deleteCrawlData()} variant="destructive" size="xs" className="gap-1 w-full">
                  <Trash2 className="h-3 w-3" />
                  {t("quickActions.deleteCrawl")}
                </Button>
              )}
            </div>

            {/* Arrow 1→2 */}
            <ArrowRight className="h-5 w-5 text-muted-foreground shrink-0 mx-2" />

            {/* Step 2: Extract */}
            <div className="flex flex-col items-center gap-2 min-w-[160px]">
              <div className={`flex items-center justify-center w-10 h-10 rounded-full border-2 ${
                extracting ? "border-blue-500 bg-blue-50" :
                extractStatus?.status === "completed" ? "border-green-500 bg-green-50" :
                extractStatus?.status === "failed" ? "border-red-500 bg-red-50" :
                "border-muted bg-muted/50"
              }`}>
                {extracting ? <Loader2 className="h-5 w-5 animate-spin text-blue-500" /> :
                 extractStatus?.status === "completed" ? <CheckCircle2 className="h-5 w-5 text-green-500" /> :
                 extractStatus?.status === "failed" ? <XCircle className="h-5 w-5 text-red-500" /> :
                 <Sparkles className="h-5 w-5 text-muted-foreground" />}
              </div>
              <Button onClick={() => startExtractFeatures()} disabled={extracting || !crawlStatus || crawlStatus.status !== "completed"} variant={extractStatus?.status === "completed" ? "outline" : "secondary"} className="gap-2 w-full">
                {extracting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {t("quickActions.extract")}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                {extracting ? `Extracting...` :
                 extractStatus?.status === "completed" ? `${extractStatus?.features_extracted ?? 0} features` :
                 extractStatus?.status === "failed" ? `Failed: ${extractStatus?.error ?? ""}` :
                 ""}
              </p>
              {extractStatus?.status === "completed" && !extracting && (
                <Button onClick={() => deleteFeatures()} variant="destructive" size="xs" className="gap-1 w-full">
                  <Trash2 className="h-3 w-3" />
                  {t("quickActions.deleteFeatures")}
                </Button>
              )}
            </div>

            {/* Arrow 2→3 */}
            <ArrowRight className="h-5 w-5 text-muted-foreground shrink-0 mx-2" />

            {/* Step 3: Generate */}
            <div className="flex flex-col items-center gap-2 min-w-[160px]">
              <div className={`flex items-center justify-center w-10 h-10 rounded-full border-2 ${
                generating ? "border-blue-500 bg-blue-50" :
                generateStatus?.status === "completed" ? "border-green-500 bg-green-50" :
                generateStatus?.status === "failed" ? "border-red-500 bg-red-50" :
                "border-muted bg-muted/50"
              }`}>
                {generating ? <Loader2 className="h-5 w-5 animate-spin text-blue-500" /> :
                 generateStatus?.status === "completed" ? <CheckCircle2 className="h-5 w-5 text-green-500" /> :
                 generateStatus?.status === "failed" ? <XCircle className="h-5 w-5 text-red-500" /> :
                 <FileText className="h-5 w-5 text-muted-foreground" />}
              </div>
              <Button onClick={() => startGenerateScenarios()} disabled={generating || !extractStatus || extractStatus.status !== "completed"} variant={generateStatus?.status === "completed" ? "outline" : "secondary"} className="gap-2 w-full">
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                {t("quickActions.generate")}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                {generating ? `Generating...` :
                 generateStatus?.status === "completed" ? `${generateStatus?.scenarios_generated ?? 0} scenarios` :
                 generateStatus?.status === "failed" ? `Failed: ${generateStatus?.error ?? ""}` :
                 ""}
              </p>
              {generateStatus?.status === "completed" && !generating && (
                <Button onClick={() => deleteScenarios()} variant="destructive" size="xs" className="gap-1 w-full">
                  <Trash2 className="h-3 w-3" />
                  {t("quickActions.deleteScenarios")}
                </Button>
              )}
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
                  <TableHead>{t("table.id")}</TableHead>
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
                      <Link href={`/executions/${ex.id}`} className="hover:underline" title={ex.id}>{ex.id.slice(0, 8)}</Link>
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
                    <TableCell className="text-xs text-muted-foreground">{ex.started_at ? new Date(ex.started_at).toLocaleString() : "-"}</TableCell>
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