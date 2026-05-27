"use client";

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
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { MutationType } from "@/lib/types";
import type { MutationResult } from "@/lib/types";
import { useI18n } from "@/lib/useI18n";

const COLORS = ["#3b82f6", "#ef4444", "#f59e0b", "#10b981"];

interface MutationPanelProps {
  mutations: MutationResult[];
}

export function MutationPanel({ mutations }: MutationPanelProps) {
  const { t } = useI18n();

  // Build translated label maps (reactive to locale changes)
  const mutationTypeLabels: Record<string, string> = {
    [MutationType.ACTION_MUTATION]: t("mutation.action"),
    [MutationType.INPUT_MUTATION]: t("mutation.input"),
    [MutationType.STEP_MUTATION]: t("mutation.step"),
  };

  const errorTypeLabels: Record<string, string> = {
    execution_exception: t("error.execution_exception"),
    layout_issue: t("error.layout_issue"),
    semantic_error: t("error.semantic_error"),
    none: t("error.none"),
  };

  // Compute statistics
  const mutationTypeCounts = mutations.reduce(
    (acc, m) => {
      acc[m.mutation_type] = (acc[m.mutation_type] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  const errorTypeCounts = mutations
    .filter((m) => m.detected_error_type && m.detected_error_type !== "none")
    .reduce(
      (acc, m) => {
        const key = m.detected_error_type || "none";
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>
    );

  // Chart data for mutation types
  const mutationTypeChartData = Object.entries(mutationTypeCounts).map(
    ([type, count]) => ({
      name: mutationTypeLabels[type] || type,
      count,
    })
  );

  // Chart data for error types
  const errorTypeChartData = Object.entries(errorTypeCounts).map(
    ([type, count]) => ({
      name: errorTypeLabels[type] || type,
      value: count,
    })
  );

  // Detection rate
  const detectedCount = mutations.filter(
    (m) => m.detected_error_type && m.detected_error_type !== "none"
  ).length;
  const detectionRate =
    mutations.length > 0 ? (detectedCount / mutations.length) * 100 : 0;

  // Execution matrix: mutation type x detected error type
  const matrix: Record<string, Record<string, number>> = {};
  mutations.forEach((m) => {
    const mType = mutationTypeLabels[m.mutation_type] || m.mutation_type;
    const eType = errorTypeLabels[m.detected_error_type || "none"] || m.detected_error_type || "none";
    if (!matrix[mType]) matrix[mType] = {};
    matrix[mType][eType] = (matrix[mType][eType] || 0) + 1;
  });

  const errorTypes = Object.keys(
    mutations.reduce(
      (acc, m) => {
        const eType = errorTypeLabels[m.detected_error_type || "none"] || m.detected_error_type || "none";
        acc[eType] = true;
        return acc;
      },
      {} as Record<string, boolean>
    )
  );

  // Translated "No Error Detected" label for comparison
  const noErrorDetectedLabel = t("error.none");

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("mutations.total")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{mutations.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("mutations.errorsDetected")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">
              {detectedCount}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("mutations.detectionRate")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {detectionRate.toFixed(1)}%
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Mutation type distribution chart */}
      <Card>
        <CardHeader>
          <CardTitle>{t("mutations.typeDistribution")}</CardTitle>
          <CardDescription>
            {t("mutations.typeDistribution.desc")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mutationTypeChartData.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              {t("mutations.noMutations")}
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={mutationTypeChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Error type pie chart */}
      <Card>
        <CardHeader>
          <CardTitle>{t("mutations.errorTypes")}</CardTitle>
          <CardDescription>
            {t("mutations.errorTypes.desc")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {errorTypeChartData.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              {t("mutations.noErrors")}
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={errorTypeChartData}
                  cx="50%"
                  cy="50%"
                  labelLine={true}
                  label={({ name, percent }) =>
                    `${name ?? ""}: ${((percent ?? 0) * 100).toFixed(0)}%`
                  }
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {errorTypeChartData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Execution matrix */}
      <Card>
        <CardHeader>
          <CardTitle>{t("mutations.matrix")}</CardTitle>
          <CardDescription>
            {t("mutations.matrix.desc")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mutations.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              {t("mutations.noResults")}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("table.mutationType")}</TableHead>
                  {errorTypes.map((et) => (
                    <TableHead key={et}>{et}</TableHead>
                  ))}
                  <TableHead>{t("table.total")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(matrix).map(([mType, row]) => (
                  <TableRow key={mType}>
                    <TableCell className="font-medium">{mType}</TableCell>
                    {errorTypes.map((et) => (
                      <TableCell key={et}>
                        {row[et] ? (
                          <Badge
                            variant={
                              et === noErrorDetectedLabel
                                ? "secondary"
                                : "destructive"
                            }
                          >
                            {row[et]}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </TableCell>
                    ))}
                    <TableCell>
                      {Object.values(row).reduce((a, b) => a + b, 0)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Mutation results table */}
      <Card>
        <CardHeader>
          <CardTitle>{t("mutations.results")}</CardTitle>
          <CardDescription>{t("mutations.allResults")}</CardDescription>
        </CardHeader>
        <CardContent>
          {mutations.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              {t("mutations.noResults")}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("table.id")}</TableHead>
                  <TableHead>{t("table.type")}</TableHead>
                  <TableHead>{t("table.originalScenario")}</TableHead>
                  <TableHead>{t("table.executionResult")}</TableHead>
                  <TableHead>{t("table.errorType")}</TableHead>
                  <TableHead>{t("table.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mutations.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-mono text-xs">
                      {m.id}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {mutationTypeLabels[m.mutation_type] || m.mutation_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/scenarios/${m.original_scenario_id}`}
                        className="hover:underline text-sm"
                        title={m.original_scenario_id}
                      >
                        {m.original_scenario_id}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {m.execution.final_result ? (
                        <Badge
                          variant={
                            m.execution.final_result === "pass"
                              ? "default"
                              : "destructive"
                          }
                        >
                          {m.execution.final_result}
                        </Badge>
                      ) : (
                        <Badge variant="outline">-</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {m.detected_error_type && m.detected_error_type !== "none" ? (
                        <Badge variant="destructive">
                          {errorTypeLabels[m.detected_error_type] || m.detected_error_type}
                        </Badge>
                      ) : (
                        <Badge variant="secondary">{t("error.none")}</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {m.execution?.id ? (
                        <Link
                          href={`/executions/${m.execution.id}`}
                          className="hover:underline text-sm text-blue-500"
                        >
                          {t("mutations.viewExecution")}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground text-xs">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}