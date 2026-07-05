"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  ChevronDown,
  ChevronUp,
  PlayCircle,
  Eye,
  Target,
} from "lucide-react";
import type { TestScenario } from "@/lib/types";
import { useI18n } from "@/lib/useI18n";

interface ScenarioDetailProps {
  scenario: TestScenario;
  onExecute?: (scenarioId: string) => void;
}

export function ScenarioDetail({ scenario, onExecute }: ScenarioDetailProps) {
  const { t } = useI18n();
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const toggleStep = (stepNumber: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepNumber)) {
        next.delete(stepNumber);
      } else {
        next.add(stepNumber);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedSteps(new Set(scenario.steps.map((s) => s.step)));
  };

  const collapseAll = () => {
    setExpandedSteps(new Set());
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-lg">{scenario.name}</h3>
          <p className="text-sm text-muted-foreground">
            {t("scenarioDetail.feature")}: {scenario.feature_id} | {scenario.steps.length} {t("scenarioDetail.steps")} |{" "}
            {scenario.expectations.length} {t("scenarioDetail.expectations")}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={expandAll}
            className="gap-1"
          >
            <ChevronDown className="h-3 w-3" />
            {t("scenarioDetail.expandAll")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={collapseAll}
            className="gap-1"
          >
            <ChevronUp className="h-3 w-3" />
            {t("scenarioDetail.collapseAll")}
          </Button>
          {onExecute && (
            <Button
              size="sm"
              onClick={() => onExecute(scenario.id)}
              className="gap-1"
            >
              <PlayCircle className="h-3 w-3" />
              {t("scenarioDetail.execute")}
            </Button>
          )}
        </div>
      </div>

      <Separator />

      {/* Steps */}
      <div className="space-y-2">
        <h4 className="font-semibold text-sm flex items-center gap-2">
          <Target className="h-4 w-4" />
          {t("scenarioDetail.steps")}
        </h4>
        {scenario.steps.map((step) => {
          const isExpanded = expandedSteps.has(step.step);
          return (
            <Card key={step.step} className="border-l-4 border-l-blue-400">
              <CardContent className="py-3">
                <div
                  className="flex items-center gap-3 cursor-pointer"
                  onClick={() => toggleStep(step.step)}
                >
                  <Badge variant="outline" className="text-xs font-mono">
                    {t("scenarioDetail.step")} {step.step}
                  </Badge>
                  <span className="text-sm font-medium">{step.action}</span>
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
                {isExpanded && (
                  <div className="mt-3 ml-8 space-y-2">
                    <div className="text-sm">
                      <span className="font-medium text-muted-foreground">
                        {t("scenarioDetail.action")}:
                      </span>{" "}
                      {step.action}
                    </div>
                    <div className="text-sm">
                      <span className="font-medium text-muted-foreground">
                        {t("scenarioDetail.target")}:
                      </span>{" "}
                      {step.target}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Expectations */}
      {scenario.expectations.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-semibold text-sm flex items-center gap-2">
            <Eye className="h-4 w-4" />
            {t("scenarioDetail.expectations")}
          </h4>
          {scenario.expectations.map((exp, i) => (
            <Card
              key={i}
              className={
                exp.type === "visual_match"
                  ? "border-l-4 border-l-purple-400"
                  : "border-l-4 border-l-green-400"
              }
            >
              <CardContent className="py-3">
                <div className="flex items-center gap-3">
                  <Badge
                    variant={exp.type === "visual_match" ? "default" : "secondary"}
                    className="text-xs"
                  >
                    {exp.type === "visual_match" ? "🔍 visual_match" : exp.type}
                  </Badge>
                  <span className="text-sm">{exp.description}</span>
                </div>
                {exp.type === "visual_match" && exp.reference_image && (
                  <div className="mt-2">
                    <p className="text-xs text-muted-foreground mb-1">
                      {t("scenarioDetail.referenceImage")}
                    </p>
                    <img
                      src={`/api/reference-images/${encodeURIComponent(exp.reference_image)}`}
                      alt={exp.description}
                      className="max-w-xs rounded border shadow-sm"
                      style={{ maxHeight: "200px" }}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Source chunks info */}
      <div className="text-xs text-muted-foreground">
        {t("scenarioDetail.scenarioId")}: {scenario.id}
      </div>
    </div>
  );
}