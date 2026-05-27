"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft, PlayCircle } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { getFeatureById, getScenariosByFeature } from "@/lib/api";
import { useI18n } from "@/lib/useI18n";
import type { Feature, TestScenario } from "@/lib/types";

export default function FeatureDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const { executeScenario, scenarios } = useAppStore();
  const { t } = useI18n();

  const [feature, setFeature] = useState<Feature | null>(null);
  const [featureScenarios, setFeatureScenarios] = useState<TestScenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const f = await getFeatureById(id);
        const sc = await getScenariosByFeature(id);
        setFeature(f);
        setFeatureScenarios(sc);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load feature");
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
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !feature) {
    return (
      <div className="text-destructive">
        {error || "Feature not found"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/features">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            {t("features.detail.back")}
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-xl">{feature.name}</CardTitle>
              <CardDescription>
                {t("features.detail.category")}: {feature.category} | {t("table.id")}: {feature.id}
              </CardDescription>
            </div>
            <Badge variant="outline">{feature.category}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <h4 className="font-semibold text-sm mb-2">
              {t("features.detail.description")}
            </h4>
            <p className="text-sm text-muted-foreground">
              {feature.description}
            </p>
          </div>
          <Separator />
          <div>
            <h4 className="font-semibold text-sm mb-2">
              {t("features.detail.sourceChunks")}
            </h4>
            <div className="flex gap-2 flex-wrap">
              {feature.source_chunks.map((chunk, i) => (
                <Badge key={i} variant="secondary" className="text-xs">
                  {chunk}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Related Scenarios */}
      <Card>
        <CardHeader>
          <CardTitle>{t("features.detail.relatedScenarios")}</CardTitle>
          <CardDescription>
            {t("features.detail.relatedScenarios.desc")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {featureScenarios.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("features.detail.noScenarios")}
            </p>
          ) : (
            <div className="space-y-4">
              {featureScenarios.map((scenario) => (
                <Card key={scenario.id} className="border-l-4 border-l-blue-500">
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <Link
                          href={`/scenarios/${scenario.id}`}
                          className="font-semibold hover:underline"
                        >
                          {scenario.name}
                        </Link>
                        <p className="text-xs text-muted-foreground">
                          {t("table.id")}: {scenario.id} | {scenario.steps.length} {t("table.steps")} |{" "}
                          {scenario.expectations.length} {t("features.detail.expectations")}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        className="gap-1"
                        onClick={() => executeScenario(scenario.id)}
                      >
                        <PlayCircle className="h-3 w-3" />
                        {t("features.detail.execute")}
                      </Button>
                    </div>
                    <div className="space-y-1">
                      {scenario.steps.map((step) => (
                        <div
                          key={step.step}
                          className="text-sm flex items-start gap-2"
                        >
                          <Badge
                            variant="outline"
                            className="text-xs shrink-0"
                          >
                            {step.step}
                          </Badge>
                          <span className="text-muted-foreground">
                            {step.action}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            ({t("features.detail.target")}: {step.target})
                          </span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}