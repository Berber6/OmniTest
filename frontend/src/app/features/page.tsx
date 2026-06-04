"use client";

import { useEffect, useState, useCallback } from "react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { GitBranch, Download, Upload } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { FeatureTree } from "@/components/FeatureTree";
import { useI18n } from "@/lib/useI18n";
import { ImportExportDialog } from "@/components/ImportExportDialog";
import { DataListToolbar, type FilterConfig } from "@/components/DataListToolbar";

function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    "Board管理": "#3b82f6",
    "List管理": "#10b981",
    "Card管理": "#f59e0b",
    "Member管理": "#ef4444",
    "Settings": "#8b5cf6",
    "Automation": "#6366f1",
  };
  return colors[category] || "#64748b";
}

export default function FeaturesPage() {
  const {
    allFeatures,
    allScenarios,
    featureCategories,
    loadingFeatures,
    errorFeatures,
    fetchAllFeatures,
    fetchAllScenarios,
    fetchFeatureCategories,
  } = useAppStore();
  const { t } = useI18n();

  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  useEffect(() => {
    fetchAllFeatures();
    fetchAllScenarios();
    fetchFeatureCategories();
  }, []);

  const handleSearchChange = useCallback((value: string) => { setSearch(value); }, []);
  const handleFilterChange = useCallback((key: string, value: string) => {
    if (key === "category") setCategoryFilter(value);
  }, []);

  // Filter features client-side (no pagination, show all)
  const filteredFeatures = allFeatures.filter((f) => {
    if (categoryFilter && f.category !== categoryFilter) return false;
    if (search) {
      const term = search.toLowerCase();
      return f.name.toLowerCase().includes(term) || f.description.toLowerCase().includes(term);
    }
    return true;
  });

  // Group filtered features by category
  const groupedFeatures = filteredFeatures.reduce(
    (acc, f) => {
      if (!acc[f.category]) acc[f.category] = [];
      acc[f.category].push(f);
      return acc;
    },
    {} as Record<string, typeof filteredFeatures>
  );

  const categoryFilterConfig: FilterConfig[] = featureCategories.length > 0
    ? [{
        key: "category",
        placeholder: t("filter.category"),
        options: featureCategories.map((c) => ({ value: c, label: c })),
      }]
    : [];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GitBranch className="h-6 w-6 text-blue-500" />
          <div>
            <h2 className="text-2xl font-bold tracking-tight">{t("features.title")}</h2>
            <p className="text-muted-foreground">{t("features.subtitle")}</p>
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

      <ImportExportDialog dataType="features" mode="export" open={exportOpen} onOpenChange={setExportOpen} />
      <ImportExportDialog dataType="features" mode="import" open={importOpen} onOpenChange={setImportOpen} />

      <Tabs defaultValue="tree">
        <TabsList>
          <TabsTrigger value="tree">{t("features.treeView")}</TabsTrigger>
          <TabsTrigger value="list">{t("features.listView")}</TabsTrigger>
        </TabsList>

        <TabsContent value="tree">
          <Card>
            <CardHeader>
              <CardTitle>{t("features.tree.title")}</CardTitle>
              <CardDescription>{t("features.tree.desc")}</CardDescription>
            </CardHeader>
            <CardContent>
              {loadingFeatures ? (
                <Skeleton className="h-[600px] w-full" />
              ) : errorFeatures ? (
                <div className="text-destructive py-4">{errorFeatures}</div>
              ) : allFeatures.length === 0 ? (
                <div className="text-center text-muted-foreground py-4">{t("features.tree.empty")}</div>
              ) : (
                <FeatureTree features={allFeatures} scenarios={allScenarios} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="list">
          <DataListToolbar
            searchValue={search}
            onSearchChange={handleSearchChange}
            searchPlaceholder={t("search.placeholder")}
            filters={categoryFilterConfig}
            filterValues={{ category: categoryFilter }}
            onFilterChange={handleFilterChange}
            totalCount={filteredFeatures.length}
            totalCountLabel={t("pagination.items")}
          />

          {loadingFeatures ? (
            <div className="space-y-4 mt-4">
              {[1, 2, 3].map((i) => (<Skeleton key={i} className="h-32 w-full" />))}
            </div>
          ) : filteredFeatures.length === 0 ? (
            <Card className="mt-4">
              <CardContent className="py-8 text-center text-muted-foreground">{t("features.list.empty")}</CardContent>
            </Card>
          ) : (
            <div className="space-y-4 mt-4">
              {Object.entries(groupedFeatures).map(([category, catFeatures]) => (
                <Card key={category}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2" style={{ color: getCategoryColor(category) }}>
                      <GitBranch className="h-4 w-4" />
                      {category}
                    </CardTitle>
                    <CardDescription>{catFeatures.length} {t("features.list.categoryCount")}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t("table.id")}</TableHead>
                          <TableHead>{t("table.name")}</TableHead>
                          <TableHead>{t("table.description")}</TableHead>
                          <TableHead>{t("table.scenario")}</TableHead>
                          <TableHead>{t("table.sources")}</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {catFeatures.map((feature) => {
                          const featureScenarios = allScenarios.filter((s) => s.feature_id === feature.id);
                          return (
                            <TableRow key={feature.id}>
                              <TableCell className="font-mono text-xs">{feature.id}</TableCell>
                              <TableCell>
                                <Link href={`/features/${feature.id}`} className="font-medium hover:underline">{feature.name}</Link>
                              </TableCell>
                              <TableCell className="text-sm text-muted-foreground max-w-xs truncate">{feature.description}</TableCell>
                              <TableCell><Badge variant="secondary">{featureScenarios.length}</Badge></TableCell>
                              <TableCell className="text-xs text-muted-foreground">{feature.source_chunks.length} {t("features.list.chunks")}</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}