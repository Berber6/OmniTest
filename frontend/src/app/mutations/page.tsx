"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Bug, Loader2 } from "lucide-react";
import { MutationPanel } from "@/components/MutationPanel";
import { useAppStore } from "@/lib/store";
import { MutationType } from "@/lib/types";
import { useI18n } from "@/lib/useI18n";
import { DataListToolbar, type FilterConfig } from "@/components/DataListToolbar";
import { PaginationControls } from "@/components/PaginationControls";

const mutationTypeKeys: Record<MutationType, string> = {
  [MutationType.ACTION_MUTATION]: "mutation.action",
  [MutationType.INPUT_MUTATION]: "mutation.input",
  [MutationType.STEP_MUTATION]: "mutation.step",
};

export default function MutationsPage() {
  const {
    mutations,
    mutationsTotal,
    mutationsPage,
    allScenarios,
    loadingMutations,
    fetchMutations,
    fetchAllScenarios,
    runMutation,
  } = useAppStore();

  const { t } = useI18n();

  const [running, setRunning] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [mutationTypeFilter, setMutationTypeFilter] = useState("");
  const [errorTypeFilter, setErrorTypeFilter] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchAllScenarios();
    fetchMutations({ page: 1, page_size: 20 });
  }, []);

  useEffect(() => {
    fetchMutations({
      search: search || undefined,
      mutation_type: mutationTypeFilter || undefined,
      detected_error_type: errorTypeFilter || undefined,
      page,
      page_size: 20,
    });
  }, [search, mutationTypeFilter, errorTypeFilter, page]);

  const handleRunMutation = async (scenarioId: string, mutationType: MutationType) => {
    setRunning(scenarioId + "-" + mutationType);
    try { await runMutation(scenarioId, mutationType); } finally { setRunning(null); }
  };

  const handleSearchChange = useCallback((value: string) => { setSearch(value); setPage(1); }, []);
  const handleFilterChange = useCallback((key: string, value: string) => {
    if (key === "mutation_type") { setMutationTypeFilter(value); setPage(1); }
    if (key === "detected_error_type") { setErrorTypeFilter(value); setPage(1); }
  }, []);
  const handlePageChange = useCallback((p: number) => { setPage(p); }, []);

  const mutationFilterConfigs: FilterConfig[] = [
    {
      key: "mutation_type",
      placeholder: t("filter.mutationType"),
      options: Object.values(MutationType).map((mt) => ({ value: mt, label: t(mutationTypeKeys[mt]) })),
    },
    {
      key: "detected_error_type",
      placeholder: t("filter.errorType"),
      options: [
        { value: "execution_exception", label: "Execution Exception" },
        { value: "layout_issue", label: "Layout Issue" },
        { value: "semantic_error", label: "Semantic Error" },
        { value: "none", label: "None" },
      ],
    },
  ];

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <Bug className="h-6 w-6 text-orange-500" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t("mutations.title")}</h2>
          <p className="text-muted-foreground">{t("mutations.subtitle")}</p>
        </div>
      </div>

      {/* Run mutation controls */}
      <Card>
        <CardHeader>
          <CardTitle>{t("mutations.run")}</CardTitle>
          <CardDescription>{t("mutations.run.desc")}</CardDescription>
        </CardHeader>
        <CardContent>
          {allScenarios.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("mutations.noScenarios")}</p>
          ) : (
            <div className="space-y-4">
              {allScenarios.slice(0, 10).map((scenario) => (
                <div key={scenario.id} className="flex items-center justify-between border rounded-md p-3">
                  <div>
                    <span className="font-medium text-sm">{scenario.name}</span>
                    <span className="text-xs text-muted-foreground ml-2">
                      ({scenario.steps.length} {t("mutations.steps")})
                    </span>
                  </div>
                  <div className="flex gap-2">
                    {Object.values(MutationType).map((mt) => {
                      const isLoading = running === scenario.id + "-" + mt;
                      return (
                        <Button key={mt} size="sm" variant="outline" disabled={isLoading}
                          onClick={() => handleRunMutation(scenario.id, mt)} className="gap-1">
                          {isLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Bug className="h-3 w-3" />}
                          {t(mutationTypeKeys[mt])}
                        </Button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Separator />

      {/* Mutation results with search, filter, pagination */}
      <div>
        <h3 className="text-lg font-semibold mb-4">{t("mutations.results")}</h3>

        <DataListToolbar
          searchValue={search}
          onSearchChange={handleSearchChange}
          filters={mutationFilterConfigs}
          filterValues={{ mutation_type: mutationTypeFilter, detected_error_type: errorTypeFilter }}
          onFilterChange={handleFilterChange}
          totalCount={mutationsTotal}
          totalCountLabel={t("pagination.items")}
        />

        {loadingMutations ? (
          <div className="space-y-4 mt-4">
            {[1, 2, 3].map((i) => (<Skeleton key={i} className="h-32 w-full" />))}
          </div>
        ) : (
          <>
            <MutationPanel mutations={mutations} />
            <PaginationControls page={mutationsPage} pageSize={20} total={mutationsTotal} onPageChange={handlePageChange} />
          </>
        )}
      </div>
    </div>
  );
}