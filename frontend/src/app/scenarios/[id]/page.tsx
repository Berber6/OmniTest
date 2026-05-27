"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft } from "lucide-react";
import { ScenarioDetail } from "@/components/ScenarioDetail";
import { getScenarioById } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { useI18n } from "@/lib/useI18n";
import type { TestScenario } from "@/lib/types";

export default function ScenarioDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const { executeScenario } = useAppStore();
  const { t } = useI18n();

  const [scenario, setScenario] = useState<TestScenario | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const s = await getScenarioById(id);
        setScenario(s);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load scenario");
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
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !scenario) {
    return (
      <Card>
        <CardContent className="py-8 text-destructive">
          {error || "Scenario not found"}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/scenarios">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            {t("scenarios.detail.back")}
          </Button>
        </Link>
      </div>

      <ScenarioDetail
        scenario={scenario}
        onExecute={(scenarioId) => executeScenario(scenarioId)}
      />
    </div>
  );
}