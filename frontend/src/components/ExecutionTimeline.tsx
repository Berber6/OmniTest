"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Progress, ProgressTrack, ProgressIndicator } from "@/components/ui/progress";
import {
  CheckCircle2,
  XCircle,
  Clock,
  PlayCircle,
  Eye,
  Loader2,
  RefreshCw,
  Flag,
  Expand,
  Shrink,
} from "lucide-react";
import { AgentStatus } from "@/lib/types";
import type { ExecutionRecord, StepResult, StepProgress } from "@/lib/types";
import { getScreenshotUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/useI18n";
import { useAppStore } from "@/lib/store";

interface ExecutionTimelineProps {
  execution: ExecutionRecord;
}

function StatusIcon({ status }: { status: AgentStatus }) {
  switch (status) {
    case AgentStatus.PENDING:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
    case AgentStatus.PLANNING:
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    case AgentStatus.EXECUTING:
      return <PlayCircle className="h-4 w-4 text-blue-500" />;
    case AgentStatus.VERIFYING:
      return <Eye className="h-4 w-4 text-yellow-500" />;
    case AgentStatus.REFLECTING:
      return <RefreshCw className="h-4 w-4 text-orange-500" />;
    case AgentStatus.COMPLETED:
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case AgentStatus.FAILED:
      return <XCircle className="h-4 w-4 text-red-500" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

// 获取步骤的截图路径：优先 stepResult.screenshot_path，其次 page_state.screenshot_path
function getStepScreenshot(stepResult: StepResult): string | undefined {
  if (stepResult.screenshot_path) return stepResult.screenshot_path;
  if (stepResult.page_state?.screenshot_path) return stepResult.page_state.screenshot_path;
  return undefined;
}

export function ExecutionTimeline({ execution }: ExecutionTimelineProps) {
  const { t } = useI18n();
  const [expandedScreenshot, setExpandedScreenshot] = useState<number | null>(null);
  const stepProgress = useAppStore((s) => s.stepProgress);
  const isExecuting = execution.status === AgentStatus.EXECUTING;
  // Only show progress indicator if the progress event matches this execution
  const currentStepProgress = isExecuting && stepProgress && stepProgress.execution_id === execution.id
    ? stepProgress
    : null;

  return (
    <div className="relative">
      {/* Timeline line */}
      <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-border" />

      {/* Plan node */}
      <div className="relative pl-12 pb-6">
        <div className="absolute left-4 w-4 h-4 rounded-full bg-blue-500 border-2 border-white" />
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="py-3">
            <div className="flex items-center gap-2 mb-2">
              <Flag className="h-4 w-4 text-blue-500" />
              <span className="font-semibold text-sm">{t("timeline.plan")}</span>
              <Badge variant="secondary" className="text-xs">
                {execution.plan.length} {t("timeline.plan.actions")}
              </Badge>
            </div>
            <div className="space-y-1">
              {execution.plan.map((action, i) => (
                <div key={i} className="text-xs text-muted-foreground">
                  <span className="font-mono">{i + 1}.</span>{" "}
                  {action.description} ({action.tool})
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Step nodes */}
      {execution.executed_steps.map((stepResult, i) => {
        const screenshotPath = getStepScreenshot(stepResult);
        const isExpanded = expandedScreenshot === i;

        return (
          <div key={i} className="relative pl-12 pb-6">
            <div
              className={cn(
                "absolute left-4 w-4 h-4 rounded-full border-2 border-white",
                stepResult.success ? "bg-green-500" : "bg-red-500"
              )}
            />
            <Card className={cn("border-l-4", stepResult.success ? "border-l-green-500" : "border-l-red-500")}>
              <CardContent className="py-3">
                <div className="flex items-center gap-2 mb-2">
                  <StatusIcon status={stepResult.success ? AgentStatus.COMPLETED : AgentStatus.FAILED} />
                  <span className="font-semibold text-sm">
                    {t("timeline.step")} {stepResult.step_number}
                  </span>
                  <Badge
                    variant={stepResult.success ? "default" : "destructive"}
                    className="text-xs"
                  >
                    {stepResult.success ? t("timeline.success") : t("timeline.failed")}
                  </Badge>
                </div>

                <div className="space-y-2">
                  <div className="text-sm">
                    <span className="font-medium">{t("timeline.action")}:</span>{" "}
                    {stepResult.done ? (
                      <span className="text-muted-foreground italic">done</span>
                    ) : (
                      <>
                        <span className="font-mono">{stepResult.tool || "-"}</span>
                        {stepResult.args && Object.keys(stepResult.args).length > 0 && (
                          <span className="text-xs text-muted-foreground ml-1">
                            ({JSON.stringify(stepResult.args)})
                          </span>
                        )}
                      </>
                    )}
                  </div>

                  {stepResult.reasoning && (
                    <div className="text-xs text-muted-foreground bg-muted/50 rounded p-2">
                      {stepResult.reasoning}
                    </div>
                  )}

                  {stepResult.error && (
                    <div className="text-sm text-destructive">
                      {t("timeline.error")}: {stepResult.error}
                    </div>
                  )}

                  {/* Page state（旧格式兼容，新架构不产出） */}
                  {stepResult.page_state && (
                    <div className="text-xs text-muted-foreground space-y-1">
                      {stepResult.page_state.url && (
                        <div>
                          {t("timeline.url")}: {stepResult.page_state.url}
                        </div>
                      )}
                      {stepResult.page_state.title && (
                        <div>
                          {t("timeline.title")}: {stepResult.page_state.title}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Screenshot — 每个步骤都可点击查看/放大 */}
                  {screenshotPath && (
                    <div className="mt-2">
                      <div
                        className={cn(
                          "relative overflow-hidden rounded border cursor-pointer group transition-all",
                          isExpanded ? "h-auto" : "h-36 w-48"
                        )}
                        onClick={() => setExpandedScreenshot(isExpanded ? null : i)}
                      >
                        <img
                          src={getScreenshotUrl(screenshotPath)}
                          alt={`${t("timeline.step")} ${stepResult.step_number} screenshot`}
                          className={cn(
                            "object-contain transition-opacity",
                            isExpanded ? "w-full max-h-[500px]" : "w-full h-full object-cover"
                          )}
                        />
                        {/* 悬浮时显示放大/缩小图标 */}
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="bg-black/50 rounded p-1">
                            {isExpanded ? (
                              <Shrink className="h-3 w-3 text-white" />
                            ) : (
                              <Expand className="h-3 w-3 text-white" />
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        );
      })}

      {/* Live progress indicator — shows real-time step progress during execution */}
      {currentStepProgress && (
        <div className="relative pl-12 pb-6">
          <div className="absolute left-4 w-4 h-4 rounded-full bg-blue-500 border-2 border-white animate-pulse" />
          <Card className="border-l-4 border-l-blue-500">
            <CardContent className="py-3">
              <div className="flex items-center gap-3">
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                <span className="text-sm font-medium">
                  {t("timeline.stepProgress")} {currentStepProgress.step_number}/{currentStepProgress.total_steps}
                </span>
                <span className="text-sm text-muted-foreground">
                  {currentStepProgress.action_tool}
                </span>
                <Progress value={(currentStepProgress.step_number / currentStepProgress.total_steps) * 100} className="h-2 w-[120px]">
                  <ProgressTrack>
                    <ProgressIndicator />
                  </ProgressTrack>
                </Progress>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Reflection nodes (if any retries) */}
      {execution.retry_count > 0 && execution.reflection && (
        <div className="relative pl-12 pb-6">
          <div className="absolute left-4 w-4 h-4 rounded-full bg-orange-500 border-2 border-white" />
          <Card className="border-l-4 border-l-orange-500">
            <CardContent className="py-3">
              <div className="flex items-center gap-2 mb-2">
                <RefreshCw className="h-4 w-4 text-orange-500" />
                <span className="font-semibold text-sm">{t("timeline.reflection")}</span>
                <Badge variant="secondary" className="text-xs">
                  {t("timeline.retry")}{execution.retry_count}
                </Badge>
              </div>
              <div className="text-sm text-muted-foreground">
                {execution.reflection}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Verification node */}
      {execution.verification_result && (
        <div className="relative pl-12 pb-6">
          <div
            className={cn(
              "absolute left-4 w-4 h-4 rounded-full border-2 border-white",
              execution.verification_result.passed ? "bg-green-500" : "bg-red-500"
            )}
          />
          <Card
            className={cn(
              "border-l-4",
              execution.verification_result.passed ? "border-l-green-500" : "border-l-red-500"
            )}
          >
            <CardContent className="py-3">
              <div className="flex items-center gap-2 mb-2">
                <Eye className="h-4 w-4" />
                <span className="font-semibold text-sm">{t("timeline.verification")}</span>
                <Badge
                  variant={
                    execution.verification_result.passed ? "default" : "destructive"
                  }
                  className="text-xs"
                >
                  {execution.verification_result.passed ? t("timeline.passed") : t("timeline.failed")}
                </Badge>
              </div>

              <div className="space-y-2">
                <div className="text-sm">
                  <span className="font-medium">{t("timeline.reason")}:</span>{" "}
                  {execution.verification_result.reason}
                </div>

                {execution.verification_result.details && (
                  <div className="text-sm text-muted-foreground">
                    {execution.verification_result.details}
                  </div>
                )}

                <div className="flex gap-4 text-xs text-muted-foreground">
                  {execution.verification_result.text_match !== undefined && (
                    <span>
                      {t("timeline.textMatch")}:{" "}
                      {execution.verification_result.text_match ? t("timeline.yes") : t("timeline.no")}
                    </span>
                  )}
                  {execution.verification_result.details && (
                    <span className="text-xs text-muted-foreground">
                      ({execution.verification_result.details})
                    </span>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Final result node — 只在执行完成/失败时显示 */}
      {(execution.status === AgentStatus.COMPLETED || execution.status === AgentStatus.FAILED) && (
        <div className="relative pl-12">
          <div
            className={cn(
              "absolute left-4 w-4 h-4 rounded-full border-2 border-white",
              execution.final_result === "pass" ? "bg-green-500" : "bg-red-500"
            )}
          />
          <Card
            className={cn(
              "border-l-4",
              execution.final_result === "pass" ? "border-l-green-500" : "border-l-red-500"
            )}
          >
            <CardContent className="py-3">
              <div className="flex items-center gap-2">
                {execution.final_result === "pass" ? (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-500" />
                )}
                <span className="font-semibold">
                  {t("timeline.result")}: {execution.final_result === "pass" ? "PASS" : "FAIL"}
                </span>
                {execution.failure_reason && (
                  <span className="text-sm text-muted-foreground ml-2">
                    -- {execution.failure_reason}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}