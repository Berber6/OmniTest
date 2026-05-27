"use client";

import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Feature, TestScenario } from "@/lib/types";
import { useI18n } from "@/lib/useI18n";

// ── Category color mapping ──

const CATEGORY_COLORS: Record<string, string> = {
  "Board管理": "#3b82f6",
  "List管理": "#10b981",
  "Card管理": "#f59e0b",
  "Member管理": "#ef4444",
  "Settings": "#8b5cf6",
  "Automation": "#6366f1",
};

function getCategoryColor(category: string): string {
  return CATEGORY_COLORS[category] || "#64748b";
}

// ── Build graph data from features + scenarios ──

function buildGraphData(
  features: Feature[],
  scenarios: TestScenario[],
  t: (key: string) => string
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Group features by category
  const categories = new Map<string, Feature[]>();
  features.forEach((f) => {
    if (!categories.has(f.category)) categories.set(f.category, []);
    categories.get(f.category)!.push(f);
  });

  // Category nodes (top row)
  let categoryX = 0;
  const CATEGORY_Y = 0;
  const CATEGORY_SPACING = 280;

  categories.forEach((categoryFeatures, categoryName) => {
    const color = getCategoryColor(categoryName);
    const categoryId = `cat-${categoryName}`;

    nodes.push({
      id: categoryId,
      type: "category",
      position: { x: categoryX, y: CATEGORY_Y },
      data: {
        label: categoryName,
        color,
        featureCount: categoryFeatures.length,
        t,
      },
    });

    // Feature nodes (middle row)
    let featureX = categoryX;
    const FEATURE_Y = 160;
    const FEATURE_SPACING = 220;

    categoryFeatures.forEach((feature) => {
      const featureScenarios = scenarios.filter(
        (s) => s.feature_id === feature.id
      );

      nodes.push({
        id: feature.id,
        type: "feature",
        position: { x: featureX, y: FEATURE_Y },
        data: {
          label: feature.name,
          description: feature.description,
          color,
          scenarioCount: featureScenarios.length,
          featureId: feature.id,
          t,
        },
      });

      edges.push({
        id: `cat-feature-${feature.id}`,
        source: categoryId,
        sourceHandle: "category-source",
        target: feature.id,
        targetHandle: "feature-target",
        style: { stroke: color, strokeWidth: 2 },
      });

      // Scenario nodes (bottom row)
      const SCENARIO_Y = 320;
      const SCENARIO_SPACING = 160;

      featureScenarios.forEach((scenario, idx) => {
        nodes.push({
          id: scenario.id,
          type: "scenario",
          position: {
            x: featureX + idx * SCENARIO_SPACING,
            y: SCENARIO_Y,
          },
          data: {
            label: scenario.name,
            stepCount: scenario.steps.length,
            color,
            scenarioId: scenario.id,
            t,
          },
        });

        edges.push({
          id: `feature-scenario-${scenario.id}`,
          source: feature.id,
          sourceHandle: "feature-source",
          target: scenario.id,
          targetHandle: "scenario-target",
          style: { stroke: color, strokeWidth: 1.5 },
        });
      });

      featureX += FEATURE_SPACING + Math.max(0, featureScenarios.length - 1) * 160;
    });

    categoryX += CATEGORY_SPACING;
  });

  return { nodes, edges };
}

// ── Custom Node Components ──

function CategoryNode({ data }: { data: { label: string; color: string; featureCount: number; t: (key: string) => string } }) {
  return (
    <div
      className="px-4 py-2 rounded-lg border-2 shadow-md min-w-[160px]"
      style={{ borderColor: data.color, backgroundColor: data.color + "15" }}
    >
      <Handle type="source" position={Position.Bottom} id="category-source" />
      <div className="font-semibold text-sm" style={{ color: data.color }}>
        {data.label}
      </div>
      <div className="text-xs text-muted-foreground mt-1">
        {data.featureCount} {data.t("nav.features")}
      </div>
    </div>
  );
}

function FeatureNode({ data }: { data: { label: string; description: string; color: string; scenarioCount: number; featureId: string; t: (key: string) => string } }) {
  return (
    <div
      className="px-3 py-2 rounded-md border shadow-sm min-w-[180px] bg-white hover:shadow-md transition-shadow cursor-pointer"
      style={{ borderColor: data.color }}
    >
      <Handle type="target" position={Position.Top} id="feature-target" />
      <Handle type="source" position={Position.Bottom} id="feature-source" />
      <div className="font-medium text-sm">{data.label}</div>
      <div className="text-xs text-muted-foreground mt-1 line-clamp-2">
        {data.description}
      </div>
      <Badge
        variant="secondary"
        className="mt-2 text-xs"
        style={{ backgroundColor: data.color + "20", color: data.color }}
      >
        {data.scenarioCount} {data.t("nav.scenarios")}
      </Badge>
    </div>
  );
}

function ScenarioNode({ data }: { data: { label: string; stepCount: number; color: string; scenarioId: string; t: (key: string) => string } }) {
  return (
    <div
      className="px-2 py-1.5 rounded border shadow-sm min-w-[140px] bg-gray-50"
      style={{ borderColor: data.color }}
    >
      <Handle type="target" position={Position.Top} id="scenario-target" />
      <div className="text-xs font-medium">{data.label}</div>
      <div className="text-xs text-muted-foreground">{data.stepCount} {data.t("table.steps")}</div>
    </div>
  );
}

const nodeTypes: NodeTypes = {
  category: CategoryNode,
  feature: FeatureNode,
  scenario: ScenarioNode,
};

interface FeatureTreeProps {
  features: Feature[];
  scenarios: TestScenario[];
}

export function FeatureTree({ features, scenarios }: FeatureTreeProps) {
  const { t } = useI18n();

  const { nodes, edges } = useMemo(
    () => buildGraphData(features, scenarios, t),
    [features, scenarios, t]
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (node.data.featureId) {
      window.location.href = `/features/${node.data.featureId}`;
    } else if (node.data.scenarioId) {
      window.location.href = `/scenarios/${node.data.scenarioId}`;
    }
  }, []);

  if (features.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        {t("features.tree.empty")}
      </div>
    );
  }

  return (
    <div className="w-full h-[600px] border rounded-lg bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
        <MiniMap
          nodeStrokeWidth={3}
          zoomable
          pannable
        />
      </ReactFlow>
    </div>
  );
}