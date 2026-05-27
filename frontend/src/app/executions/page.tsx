"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  PlayCircle,
  XCircle,
  CheckCircle2,
  Loader2,
  Eye,
  RefreshCw,
  Clock,
  Trash2,
  CheckSquare,
  X,
  Play,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { AgentStatus } from "@/lib/types";
import { deleteExecution as deleteExecutionApi } from "@/lib/api";
import { useI18n } from "@/lib/useI18n";

function formatDateTime(isoString: string): string {
  let normalized = isoString;
  if (!normalized.endsWith("Z") && !normalized.includes("+") && !normalized.includes("+00:00")) {
    normalized = normalized + "Z";
  }
  const date = new Date(normalized);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

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

export default function ExecutionsPage() {
  const {
    executions,
    loadingExecutions,
    errorExecutions,
    fetchExecutions,
    cancelExecution,
  } = useAppStore();
  const { t } = useI18n();

  // 多选模式：点击"多选"按钮进入，此时按钮变为"批量删除"
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchExecutions();
  }, []);

  // 可删除的记录（已完成或已失败）
  const deletableIds = executions
    .filter((ex) => ex.status === AgentStatus.COMPLETED || ex.status === AgentStatus.FAILED)
    .map((ex) => ex.id);

  const allDeletableSelected = deletableIds.length > 0 && deletableIds.every((id) => selectedIds.has(id));

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (allDeletableSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(deletableIds));
    }
  }

  function enterMultiSelect() {
    setMultiSelectMode(true);
    setSelectedIds(new Set());
  }

  function exitMultiSelect() {
    setMultiSelectMode(false);
    setSelectedIds(new Set());
  }

  async function handleBatchDelete() {
    const count = selectedIds.size;
    const msg = t("executions.batchDeleteConfirm").replace("{count}", String(count));
    if (!confirm(msg)) return;

    for (const id of selectedIds) {
      try {
        await deleteExecutionApi(id);
      } catch (e) {
        console.error(`删除 ${id} 失败:`, e);
      }
    }
    exitMultiSelect();
    fetchExecutions();
  }

  async function handleSingleDelete(id: string) {
    if (!confirm(t("executions.deleteConfirm"))) return;
    try {
      await deleteExecutionApi(id);
      fetchExecutions();
    } catch (e) {
      alert(e instanceof Error ? e.message : t("executions.deleteFail"));
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <Play className="h-6 w-6 text-purple-500" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">
            {t("executions.title")}
          </h2>
          <p className="text-muted-foreground">{t("executions.subtitle")}</p>
        </div>
      </div>

      {loadingExecutions ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : errorExecutions ? (
        <Card>
          <CardContent className="py-8 text-destructive">
            {errorExecutions}
          </CardContent>
        </Card>
      ) : executions.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            <PlayCircle className="h-8 w-8 mx-auto mb-3" />
            {t("executions.empty")}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>{t("executions.records")}</CardTitle>
                <CardDescription>
                  {executions.length} {t("executions.records.desc")}
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {multiSelectMode ? (
                  <>
                    {selectedIds.size > 0 && (
                      <Button
                        size="sm"
                        variant="destructive"
                        className="gap-1"
                        onClick={handleBatchDelete}
                      >
                        <Trash2 className="h-3 w-3" />
                        {t("executions.batchDelete")} ({selectedIds.size})
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1"
                      onClick={exitMultiSelect}
                    >
                      <X className="h-3 w-3" />
                      {t("executions.cancelSelect")}
                    </Button>
                  </>
                ) : (
                  deletableIds.length > 0 && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1"
                      onClick={enterMultiSelect}
                    >
                      <CheckSquare className="h-3 w-3" />
                      {t("executions.multiSelect")}
                    </Button>
                  )
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  {multiSelectMode && (
                    <TableHead className="w-[40px]">
                      <Checkbox
                        checked={allDeletableSelected}
                        onCheckedChange={toggleSelectAll}
                        aria-label={t("executions.selectAll")}
                      />
                    </TableHead>
                  )}
                  <TableHead className="w-[80px]">{t("table.id")}</TableHead>
                  <TableHead className="w-[240px]">{t("table.scenario")}</TableHead>
                  <TableHead>{t("table.status")}</TableHead>
                  <TableHead>{t("table.result")}</TableHead>
                  <TableHead>{t("table.retries")}</TableHead>
                  <TableHead>{t("table.steps")}</TableHead>
                  <TableHead>{t("table.started")}</TableHead>
                  {!multiSelectMode && (
                    <TableHead className="text-right">
                      {t("table.actions")}
                    </TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {executions.map((ex) => {
                  const isDeletable = ex.status === AgentStatus.COMPLETED || ex.status === AgentStatus.FAILED;
                  const isSelected = selectedIds.has(ex.id);

                  return (
                    <TableRow key={ex.id} className={isSelected ? "bg-muted/50" : ""}>
                      {multiSelectMode && (
                        <TableCell>
                          {isDeletable && (
                            <Checkbox
                              checked={isSelected}
                              onCheckedChange={() => toggleSelect(ex.id)}
                            />
                          )}
                        </TableCell>
                      )}
                      <TableCell className="font-mono text-xs">
                        <Link
                          href={`/executions/${ex.id}`}
                          className="hover:underline"
                          title={ex.id}
                        >
                          {ex.id}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/executions/${ex.id}`}
                          className="hover:underline text-sm"
                          title={`${ex.scenario_id}: ${ex.scenario_name || ex.scenario_id}`}
                        >
                          {ex.scenario_name || ex.scenario_id}
                        </Link>
                      </TableCell>
                      <TableCell>{statusBadge(ex.status, t)}</TableCell>
                      <TableCell>
                        {ex.final_result ? (
                          <Badge
                            variant={
                              ex.final_result === "pass"
                                ? "default"
                                : "destructive"
                            }
                          >
                            {ex.final_result === "pass"
                              ? t("executions.detail.pass")
                              : t("executions.detail.fail")}
                          </Badge>
                        ) : (
                          <Badge variant="outline">-</Badge>
                        )}
                      </TableCell>
                      <TableCell>{ex.retry_count}</TableCell>
                      <TableCell>
                        {ex.executed_steps.length}/{Math.max(ex.plan?.length ?? 0, ex.executed_steps.length)}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {ex.started_at ? formatDateTime(ex.started_at) : "-"}
                      </TableCell>
                      {!multiSelectMode && (
                        <TableCell className="text-right">
                          <div className="flex gap-1 justify-end">
                            {ex.status !== AgentStatus.COMPLETED &&
                              ex.status !== AgentStatus.FAILED && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="gap-1"
                                  onClick={() => cancelExecution(ex.id)}
                                >
                                  <XCircle className="h-3 w-3" />
                                  {t("executions.cancel")}
                                </Button>
                              )}
                            {isDeletable && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="gap-1 text-red-600 hover:text-red-700 hover:bg-red-50"
                                onClick={() => handleSingleDelete(ex.id)}
                              >
                                <Trash2 className="h-3 w-3" />
                                {t("executions.delete")}
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}