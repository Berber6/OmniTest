"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  XCircle,
  CheckCircle2,
  PlayCircle,
  Loader2,
  Eye,
  RefreshCw,
  Clock,
} from "lucide-react";
import { ExecutionTimeline } from "@/components/ExecutionTimeline";
import { ScreenshotCompare } from "@/components/ScreenshotCompare";
import { getExecutionById } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { AgentStatus } from "@/lib/types";
import { useI18n } from "@/lib/useI18n";

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m ${s}s`;
}
import type { ExecutionRecord } from "@/lib/types";

function statusBadge(status: AgentStatus, t: (key: string) => string) {
  const key = `status.${status}`;
  switch (status) {
    case AgentStatus.COMPLETED:
      return (
        <Badge variant="default" className="gap-1">
          <CheckCircle2 className="h-3 w-3 text-green-500" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.FAILED:
      return (
        <Badge variant="destructive" className="gap-1">
          <XCircle className="h-3 w-3 text-red-500" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.EXECUTING:
      return (
        <Badge variant="secondary" className="gap-1">
          <PlayCircle className="h-3 w-3 text-blue-500" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.PLANNING:
      return (
        <Badge variant="secondary" className="gap-1">
          <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.VERIFYING:
      return (
        <Badge variant="secondary" className="gap-1">
          <Eye className="h-3 w-3 text-yellow-500" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.REFLECTING:
      return (
        <Badge variant="secondary" className="gap-1">
          <RefreshCw className="h-3 w-3 text-orange-500" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.PENDING:
      return (
        <Badge variant="outline" className="gap-1">
          <Clock className="h-3 w-3 text-gray-500" />
          {t(key)}
        </Badge>
      );
    default:
      return <Badge variant="outline">{t(key)}</Badge>;
  }
}

export default function ExecutionDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const { cancelExecution } = useAppStore();
  const { t } = useI18n();

  const [execution, setExecution] = useState<ExecutionRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const ex = await getExecutionById(id);
        setExecution(ex);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load execution");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !execution) {
    return (
      <Card>
        <CardContent className="py-8 text-destructive">
          {error || "Execution not found"}
        </CardContent>
      </Card>
    );
  }

  // 获取最后一步的截图路径（实际结果）
  const lastStepScreenshot = execution.executed_steps.length > 0
    ? execution.executed_steps[execution.executed_steps.length - 1].screenshot_path
      || execution.executed_steps[execution.executed_steps.length - 1].page_state?.screenshot_path
    : undefined;

  // 获取计划相关的截图（预期结果）：优先使用最后一个截图（通常是最终验证截图）
  const planScreenshot = execution.screenshots.length > 0
    ? execution.screenshots[execution.screenshots.length - 1]
    : undefined;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/executions">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="h-4 w-4" />
              {t("executions.detail.back")}
            </Button>
          </Link>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">
              {t("executions.detail.title")}
            </h2>
            <p className="text-sm text-muted-foreground">
              ID: {execution.id} | Scenario: {execution.scenario_name || execution.scenario_id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge(execution.status, t)}
          {execution.status !== AgentStatus.COMPLETED &&
            execution.status !== AgentStatus.FAILED && (
              <Button
                size="sm"
                variant="destructive"
                className="gap-1"
                onClick={() => cancelExecution(execution.id)}
              >
                <XCircle className="h-3 w-3" />
                {t("executions.cancel")}
              </Button>
            )}
        </div>
      </div>

      {/* Overview card */}
      <Card>
        <CardHeader>
          <CardTitle>{t("executions.detail.overview")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-4">
            <div>
              <div className="text-sm font-medium text-muted-foreground">
                {t("executions.detail.result")}
              </div>
              {execution.final_result ? (
                <Badge
                  variant={
                    execution.final_result === "pass" ? "default" : "destructive"
                  }
                  className="text-sm mt-1"
                >
                  {execution.final_result === "pass"
                    ? t("executions.detail.pass")
                    : t("executions.detail.fail")}
                </Badge>
              ) : (
                <Badge variant="outline" className="text-sm mt-1">-</Badge>
              )}
            </div>
            <div>
              <div className="text-sm font-medium text-muted-foreground">
                {t("executions.detail.retryCount")}
              </div>
              <div className="text-sm font-semibold mt-1">
                {execution.retry_count}
              </div>
            </div>
            <div>
              <div className="text-sm font-medium text-muted-foreground">
                {t("executions.detail.stepsExecuted")}
              </div>
              <div className="text-sm font-semibold mt-1">
                {execution.executed_steps.length}/{Math.max(execution.plan?.length ?? 0, execution.executed_steps.length)}
              </div>
            </div>
            <div>
              <div className="text-sm font-medium text-muted-foreground">
                {t("executions.detail.duration")}
              </div>
              <div className="text-sm font-semibold mt-1">
                {execution.completed_at && execution.duration_seconds != null
                  ? formatDuration(execution.duration_seconds)
                  : t("executions.detail.inProgress")}
              </div>
            </div>
          </div>

          {execution.failure_reason && (
            <div className="mt-4 p-3 rounded-md bg-red-50 border border-red-200">
              <h4 className="text-sm font-semibold text-red-800">
                {t("executions.detail.failureReason")}
              </h4>
              <p className="text-sm text-red-700">{execution.failure_reason}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Separator />

      {/* Execution Timeline */}
      <div>
        <h3 className="text-lg font-semibold mb-4">
          {t("executions.detail.timeline")}
        </h3>
        <ExecutionTimeline execution={execution} />
      </div>

      <Separator />

      {/* Screenshot Compare */}
      <div>
        <h3 className="text-lg font-semibold mb-4">
          {t("executions.detail.screenshots")}
        </h3>
        <ScreenshotCompare
          expectedScreenshotPath={planScreenshot}
          actualScreenshotPath={lastStepScreenshot}
          passed={execution.verification_result?.passed ?? execution.final_result === "pass"}
          diffDescription={execution.verification_result?.reason}
        />
      </div>
    </div>
  );
}