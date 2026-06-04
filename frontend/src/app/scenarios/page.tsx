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
import { PlayCircle, ClipboardList, Download, Upload } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { useI18n } from "@/lib/useI18n";
import { ImportExportDialog } from "@/components/ImportExportDialog";
import { DataListToolbar, type FilterConfig } from "@/components/DataListToolbar";
import { PaginationControls } from "@/components/PaginationControls";

export default function ScenariosPage() {
  const {
    scenarios,
    scenariosTotal,
    scenariosPage,
    allFeatures,
    loadingScenarios,
    errorScenarios,
    fetchScenarios,
    fetchAllFeatures,
    executeScenario,
  } = useAppStore();
  const { t } = useI18n();

  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [featureFilter, setFeatureFilter] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchAllFeatures();
  }, []);

  useEffect(() => {
    fetchScenarios({
      search: search || undefined,
      feature_id: featureFilter || undefined,
      page,
      page_size: 20,
    });
  }, [search, featureFilter, page]);

  const getFeatureName = (featureId: string) => {
    const feature = allFeatures.find((f) => f.id === featureId);
    return feature?.name || featureId;
  };

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    setPage(1);
  }, []);

  const handleFilterChange = useCallback((key: string, value: string) => {
    if (key === "feature_id") {
      setFeatureFilter(value);
      setPage(1);
    }
  }, []);

  const handlePageChange = useCallback((p: number) => { setPage(p); }, []);

  const featureFilterConfig: FilterConfig[] = allFeatures.length > 0
    ? [{
        key: "feature_id",
        placeholder: t("filter.feature"),
        options: allFeatures.map((f) => ({ value: f.id, label: f.name })),
      }]
    : [];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ClipboardList className="h-6 w-6 text-green-500" />
          <div>
            <h2 className="text-2xl font-bold tracking-tight">
              {t("scenarios.title")}
            </h2>
            <p className="text-muted-foreground">{t("scenarios.subtitle")}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="gap-1" onClick={() => setExportOpen(true)}>
            <Download className="h-3 w-3" />
            {t("io.export")}
          </Button>
          <Button size="sm" variant="outline" className="gap-1" onClick={() => setImportOpen(true)}>
            <Upload className="h-3 w-3" />
            {t("io.import")}
          </Button>
        </div>
      </div>

      <ImportExportDialog dataType="scenarios" mode="export" open={exportOpen} onOpenChange={setExportOpen} />
      <ImportExportDialog dataType="scenarios" mode="import" open={importOpen} onOpenChange={setImportOpen} />

      <Card>
        <CardContent className="pt-6">
          <DataListToolbar
            searchValue={search}
            onSearchChange={handleSearchChange}
            filters={featureFilterConfig}
            filterValues={{ feature_id: featureFilter }}
            onFilterChange={handleFilterChange}
            totalCount={scenariosTotal}
            totalCountLabel={t("pagination.items")}
          />

          {loadingScenarios ? (
            <div className="space-y-2 mt-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : errorScenarios ? (
            <div className="py-8 text-destructive">{errorScenarios}</div>
          ) : scenarios.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              <ClipboardList className="h-8 w-8 mx-auto mb-3" />
              {t("scenarios.empty")}
            </div>
          ) : (
            <>
              <Table className="mt-2">
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("table.id")}</TableHead>
                    <TableHead>{t("table.name")}</TableHead>
                    <TableHead>{t("table.feature")}</TableHead>
                    <TableHead>{t("table.steps")}</TableHead>
                    <TableHead>{t("table.expectations")}</TableHead>
                    <TableHead className="text-right">{t("table.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scenarios.map((scenario) => (
                    <TableRow key={scenario.id}>
                      <TableCell className="font-mono text-xs">{scenario.id}</TableCell>
                      <TableCell>
                        <Link href={`/scenarios/${scenario.id}`} className="font-medium hover:underline">
                          {scenario.name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {getFeatureName(scenario.feature_id)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{scenario.steps.length}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{scenario.expectations.length}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="secondary" className="gap-1" onClick={() => executeScenario(scenario.id)}>
                          <PlayCircle className="h-3 w-3" />
                          {t("scenarios.execute")}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <PaginationControls page={scenariosPage} pageSize={20} total={scenariosTotal} onPageChange={handlePageChange} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}