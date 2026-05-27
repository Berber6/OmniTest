"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Bug, Loader2, PlayCircle } from "lucide-react";
import { MutationPanel } from "@/components/MutationPanel";
import { useAppStore } from "@/lib/store";
import { MutationType } from "@/lib/types";
import { useI18n } from "@/lib/useI18n";

const mutationTypeKeys: Record<MutationType, string> = {
  [MutationType.ACTION_MUTATION]: "mutation.action",
  [MutationType.INPUT_MUTATION]: "mutation.input",
  [MutationType.STEP_MUTATION]: "mutation.step",
};

export default function MutationsPage() {
  const {
    mutations,
    scenarios,
    loadingMutations,
    fetchMutations,
    fetchScenarios,
    runMutation,
  } = useAppStore();

  const { t } = useI18n();

  const [running, setRunning] = useState<string | null>(null);

  useEffect(() => {
    fetchMutations();
    fetchScenarios();
  }, []);

  const handleRunMutation = async (
    scenarioId: string,
    mutationType: MutationType
  ) => {
    setRunning(scenarioId + "-" + mutationType);
    try {
      await runMutation(scenarioId, mutationType);
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <Bug className="h-6 w-6 text-orange-500" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t("mutations.title")}</h2>
          <p className="text-muted-foreground">
            {t("mutations.subtitle")}
          </p>
        </div>
      </div>

      {/* Run mutation controls */}
      <Card>
        <CardHeader>
          <CardTitle>{t("mutations.run")}</CardTitle>
          <CardDescription>
            {t("mutations.run.desc")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {scenarios.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("mutations.noScenarios")}
            </p>
          ) : (
            <div className="space-y-4">
              {scenarios.slice(0, 10).map((scenario) => (
                <div
                  key={scenario.id}
                  className="flex items-center justify-between border rounded-md p-3"
                >
                  <div>
                    <span className="font-medium text-sm">
                      {scenario.name}
                    </span>
                    <span className="text-xs text-muted-foreground ml-2">
                      ({scenario.steps.length} {t("mutations.steps")})
                    </span>
                  </div>
                  <div className="flex gap-2">
                    {Object.values(MutationType).map((mt) => {
                      const isLoading =
                        running === scenario.id + "-" + mt;
                      return (
                        <Button
                          key={mt}
                          size="sm"
                          variant="outline"
                          disabled={isLoading}
                          onClick={() => handleRunMutation(scenario.id, mt)}
                          className="gap-1"
                        >
                          {isLoading ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Bug className="h-3 w-3" />
                          )}
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

      {/* Mutation Panel */}
      <div>
        <h3 className="text-lg font-semibold mb-4">{t("mutations.results")}</h3>
        {loadingMutations ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : (
          <MutationPanel mutations={mutations} />
        )}
      </div>
    </div>
  );
}