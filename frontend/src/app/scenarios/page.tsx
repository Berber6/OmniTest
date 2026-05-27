"use client";

import { useEffect } from "react";
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
import { PlayCircle, ClipboardList } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { useI18n } from "@/lib/useI18n";

export default function ScenariosPage() {
  const {
    scenarios,
    loadingScenarios,
    errorScenarios,
    features,
    fetchScenarios,
    fetchFeatures,
    executeScenario,
  } = useAppStore();
  const { t } = useI18n();

  useEffect(() => {
    fetchScenarios();
    fetchFeatures();
  }, []);

  const getFeatureName = (featureId: string) => {
    const feature = features.find((f) => f.id === featureId);
    return feature?.name || featureId;
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <ClipboardList className="h-6 w-6 text-green-500" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">
            {t("scenarios.title")}
          </h2>
          <p className="text-muted-foreground">{t("scenarios.subtitle")}</p>
        </div>
      </div>

      {loadingScenarios ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : errorScenarios ? (
        <Card>
          <CardContent className="py-8 text-destructive">
            {errorScenarios}
          </CardContent>
        </Card>
      ) : scenarios.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            <ClipboardList className="h-8 w-8 mx-auto mb-3" />
            {t("scenarios.empty")}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{t("scenarios.all")}</CardTitle>
            <CardDescription>
              {scenarios.length} {t("scenarios.all.desc")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
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
                    <TableCell className="font-mono text-xs">
                      {scenario.id}
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/scenarios/${scenario.id}`}
                        className="font-medium hover:underline"
                      >
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
                      <Badge variant="outline">
                        {scenario.expectations.length}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="secondary"
                        className="gap-1"
                        onClick={() => executeScenario(scenario.id)}
                      >
                        <PlayCircle className="h-3 w-3" />
                        {t("scenarios.execute")}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}