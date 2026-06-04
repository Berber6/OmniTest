"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
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
  Download,
  Upload,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { AgentStatus } from "@/lib/types";
import { deleteExecution as deleteExecutionApi } from "@/lib/api";
import { useI18n } from "@/lib/useI18n";
import { ImportExportDialog } from "@/components/ImportExportDialog";
import { formatDateTime } from "@/lib/format";
import { DataListToolbar, type FilterConfig } from "@/components/DataListToolbar";
import { PaginationControls } from "@/components/PaginationControls";

function statusBadge(status: AgentStatus, t: (key: string) => string) {
  const key = `status.${status}`;
  switch (status) {
    case AgentStatus.COMPLETED:
      return (
        <Badge variant="default" className="gap-1">
          <CheckCircle2 className="h-3 w-3" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.FAILED:
      return (
        <Badge variant="destructive" className="gap-1">
          <XCircle className="h-3 w-3" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.EXECUTING:
      return (
        <Badge variant="secondary" className="gap-1 animate-pulse">
          <Loader2 className="h-3 w-3 animate-spin" />
          {t(key)}
        </Badge>
      );
    case AgentStatus.PLANNING:
      return (
        <Badge variant="secondary" className="gap-1">
          <Play className="h-3 w-3 text-blue-500" />
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

const STATUS_OPTIONS = [
  AgentStatus.COMPLETED,
  AgentStatus.FAILED,
  AgentStatus.EXECUTING,
  AgentStatus.PLANNING,
  AgentStatus.VERIFYING,
  AgentStatus.REFLECTING,
  AgentStatus.PENDING,
];

export default function ExecutionsPage() {
  const {
    executions,
    executionsTotal,
    executionsPage,
    loadingExecutions,
    errorExecutions,
    fetchExecutions,
    cancelExecution,
  } = useAppStore();
  const { t } = useI18n();

  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  // Multi-select
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchExecutions({
      search: search || undefined,
      status: statusFilter || undefined,
      page,
      page_size: 20,
    });
  }, [search, statusFilter, page]);

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    setPage(1);
  }, []);

  const handleFilterChange = useCallback((key: string, value: string) => {
    if (key === "status") {
      setStatusFilter(value);
      setPage(1);
    }
  }, []);

  const handlePageChange = useCallback((p: number) => { setPage(p); }, []);

  // Status filter config
  const statusFilterConfig: FilterConfig[] = [{
    key: "status",
    placeholder: t("filter.status"),
    options: STATUS_OPTIONS.map((s) => ({ value: s, label: t(`status.${s}`) })),
  }];

  // Deletable records (completed or failed on current page)
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
      try { await deleteExecutionApi(id); } catch (e) { console.error(`Delete ${id} failed:`, e); }
    }
    exitMultiSelect();
    fetchExecutions({ search: search || undefined, status: statusFilter || undefined, page, page_size: 20 });
  }

  async function handleSingleDelete(id: string) {
    if (!confirm(t("executions.deleteConfirm"))) return;
    try {
      await deleteExecutionApi(id);
      fetchExecutions({ search: search || undefined, status: statusFilter || undefined, page, page_size: 20 });
    } catch (e) {
      alert(e instanceof Error ? e.message : t("executions.deleteFail"));
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Play className="h-6 w-6 text-purple-500" />
          <div>
            <h2 className="text-2xl font-bold tracking-tight">{t("executions.title")}</h2>
            <p className="text-muted-foreground">{t("executions.subtitle")}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="gap-1" onClick={() => setExportOpen(true)}>
            <Download className="h-3 w-3" />{t("io.export")}
          </Button>
          <Button size="sm" variant="outline" className="gap-1" onClick={() => setImportOpen(true)}>
            <Upload className="h-3 w-3" />{t("io.import")}
          </Button>
        </div>
      </div>

      <ImportExportDialog dataType="executions" mode="export" open={exportOpen} onOpenChange={setExportOpen} />
      <ImportExportDialog dataType="executions" mode="import" open={importOpen} onOpenChange={setImportOpen} />

      <Card>
        <CardContent className="pt-6">
          <DataListToolbar
            searchValue={search}
            onSearchChange={handleSearchChange}
            filters={statusFilterConfig}
            filterValues={{ status: statusFilter }}
            onFilterChange={handleFilterChange}
            totalCount={executionsTotal}
            totalCountLabel={t("pagination.items")}
          />

          {multiSelectMode && (
            <div className="flex items-center gap-2 mt-2">
              {selectedIds.size > 0 && (
                <Button size="sm" variant="destructive" className="gap-1" onClick={handleBatchDelete}>
                  <Trash2 className="h-3 w-3" />
                  {t("executions.batchDelete")} ({selectedIds.size})
                </Button>
              )}
              <Button size="sm" variant="outline" className="gap-1" onClick={exitMultiSelect}>
                <X className="h-3 w-3" />{t("executions.cancelSelect")}
              </Button>
            </div>
          )}

          {!multiSelectMode && deletableIds.length > 0 && (
            <div className="mt-2">
              <Button size="sm" variant="outline" className="gap-1" onClick={enterMultiSelect}>
                <CheckSquare className="h-3 w-3" />{t("executions.multiSelect")}
              </Button>
            </div>
          )}

          {loadingExecutions ? (
            <div className="space-y-2 mt-4">
              {[1, 2, 3].map((i) => (<Skeleton key={i} className="h-12 w-full" />))}
            </div>
          ) : errorExecutions ? (
            <div className="py-8 text-destructive">{errorExecutions}</div>
          ) : executions.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              <PlayCircle className="h-8 w-8 mx-auto mb-3" />{t("executions.empty")}
            </div>
          ) : (
            <>
              <Table className="mt-2">
                <TableHeader>
                  <TableRow>
                    {multiSelectMode && (
                      <TableHead className="w-[40px]">
                        <Checkbox checked={allDeletableSelected} onCheckedChange={toggleSelectAll} aria-label={t("executions.selectAll")} />
                      </TableHead>
                    )}
                    <TableHead className="w-[160px]">{t("table.id")}</TableHead>
                    <TableHead className="w-[240px]">{t("table.scenario")}</TableHead>
                    <TableHead>{t("table.status")}</TableHead>
                    <TableHead>{t("table.result")}</TableHead>
                    <TableHead>{t("table.retries")}</TableHead>
                    <TableHead>{t("table.steps")}</TableHead>
                    <TableHead>{t("table.started")}</TableHead>
                    {!multiSelectMode && <TableHead className="text-right">{t("table.actions")}</TableHead>}
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
                            {isDeletable && <Checkbox checked={isSelected} onCheckedChange={() => toggleSelect(ex.id)} />}
                          </TableCell>
                        )}
                        <TableCell className="font-mono text-xs">
                          <Link href={`/executions/${ex.id}`} className="hover:underline" title={ex.id}>{ex.id}</Link>
                        </TableCell>
                        <TableCell>
                          <Link href={`/executions/${ex.id}`} className="hover:underline text-sm" title={`${ex.scenario_id}: ${ex.scenario_name || ex.scenario_id}`}>
                            {ex.scenario_name || ex.scenario_id}
                          </Link>
                        </TableCell>
                        <TableCell>{statusBadge(ex.status, t)}</TableCell>
                        <TableCell>
                          {ex.final_result ? (
                            <Badge variant={ex.final_result === "pass" ? "default" : "destructive"}>
                              {ex.final_result === "pass" ? t("executions.detail.pass") : t("executions.detail.fail")}
                            </Badge>
                          ) : <Badge variant="outline">-</Badge>}
                        </TableCell>
                        <TableCell>{ex.retry_count}</TableCell>
                        <TableCell>{ex.executed_steps.length}/{Math.max(ex.plan?.length ?? 0, ex.executed_steps.length)}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{ex.started_at ? formatDateTime(ex.started_at) : "-"}</TableCell>
                        {!multiSelectMode && (
                          <TableCell className="text-right">
                            <div className="flex gap-1 justify-end">
                              {ex.status !== AgentStatus.COMPLETED && ex.status !== AgentStatus.FAILED && (
                                <Button size="sm" variant="outline" className="gap-1" onClick={() => cancelExecution(ex.id)}>
                                  <XCircle className="h-3 w-3" />{t("executions.cancel")}
                                </Button>
                              )}
                              {isDeletable && (
                                <Button size="sm" variant="outline" className="gap-1 text-red-600 hover:text-red-700 hover:bg-red-50" onClick={() => handleSingleDelete(ex.id)}>
                                  <Trash2 className="h-3 w-3" />{t("executions.delete")}
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
              <PaginationControls page={executionsPage} pageSize={20} total={executionsTotal} onPageChange={handlePageChange} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}