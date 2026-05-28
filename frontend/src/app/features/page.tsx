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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { GitBranch, Network, Download, Upload } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { FeatureTree } from "@/components/FeatureTree";
import { useI18n } from "@/lib/useI18n";
import { ImportExportDialog } from "@/components/ImportExportDialog";

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
    features,
    loadingFeatures,
    errorFeatures,
    scenarios,
    fetchFeatures,
    fetchScenarios,
  } = useAppStore();
  const { t } = useI18n();

  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    fetchFeatures();
    fetchScenarios();
  }, []);

  // Group features by category
  const groupedFeatures = features.reduce(
    (acc, f) => {
      if (!acc[f.category]) acc[f.category] = [];
      acc[f.category].push(f);
      return acc;
    },
    {} as Record<string, typeof features>
  );

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GitBranch className="h-6 w-6 text-blue-500" />
          <div>
            <h2 className="text-2xl font-bold tracking-tight">
              {t("features.title")}
            </h2>
            <p className="text-muted-foreground">{t("features.subtitle")}</p>
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
              ) : features.length === 0 ? (
                <div className="text-center text-muted-foreground py-4">
                  {t("features.tree.empty")}
                </div>
              ) : (
                <FeatureTree features={features} scenarios={scenarios} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="list">
          {loadingFeatures ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : features.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                {t("features.list.empty")}
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedFeatures).map(([category, catFeatures]) => (
                <Card key={category}>
                  <CardHeader>
                    <CardTitle
                      className="flex items-center gap-2"
                      style={{ color: getCategoryColor(category) }}
                    >
                      <GitBranch className="h-4 w-4" />
                      {category}
                    </CardTitle>
                    <CardDescription>
                      {catFeatures.length} {t("features.list.categoryCount")}
                    </CardDescription>
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
                          const featureScenarios = scenarios.filter(
                            (s) => s.feature_id === feature.id
                          );
                          return (
                            <TableRow key={feature.id}>
                              <TableCell className="font-mono text-xs">
                                {feature.id}
                              </TableCell>
                              <TableCell>
                                <Link
                                  href={`/features/${feature.id}`}
                                  className="font-medium hover:underline"
                                >
                                  {feature.name}
                                </Link>
                              </TableCell>
                              <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                                {feature.description}
                              </TableCell>
                              <TableCell>
                                <Badge variant="secondary">
                                  {featureScenarios.length}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {feature.source_chunks.length} {t("features.list.chunks")}
                              </TableCell>
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