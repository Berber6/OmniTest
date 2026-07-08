"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Settings,
  DollarSign,
  BarChart3,
  Loader2,
  Save,
  Eye,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { useI18n } from "@/lib/useI18n";
import * as api from "@/lib/api";
import type { TokenUsageDetail } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { DataListToolbar } from "@/components/DataListToolbar";
import { PaginationControls } from "@/components/PaginationControls";

export default function SettingsPage() {
  const {
    settings,
    loadingSettings,
    tokenUsageSummary,
    loadingTokenUsage,
    fetchSettings,
    updateSetting,
    fetchTokenUsageSummary,
  } = useAppStore();

  const { t } = useI18n();
  const [tokenDetails, setTokenDetails] = useState<TokenUsageDetail[]>([]);
  const [tokenDetailTotal, setTokenDetailTotal] = useState(0);
  const [tokenDetailPage, setTokenDetailPage] = useState(1);
  const [tokenDetailSearch, setTokenDetailSearch] = useState("");
  const [tokenDetailStage, setTokenDetailStage] = useState("");

  const fetchTokenDetails = useCallback((page?: number, search?: string, stage?: string) => {
    const p = page ?? tokenDetailPage;
    const s = search ?? tokenDetailSearch;
    const st = stage ?? tokenDetailStage;
    api.getTokenUsageDetail({
      page: p, page_size: 20,
      search: s || undefined, stage: st || undefined,
    }).then((result) => {
      if (result.success) {
        setTokenDetails(result.items);
        setTokenDetailTotal(result.total);
        setTokenDetailPage(result.page);
      }
    });
  }, [tokenDetailPage, tokenDetailSearch, tokenDetailStage]);

  useEffect(() => {
    fetchSettings();
    fetchTokenUsageSummary();
    fetchTokenDetails(1);
  }, []);

  const handleUpdate = async (key: string, value: string) => {
    await updateSetting(key, value);
  };

  // Group settings by category
  const grouped = settings.reduce<Record<string, typeof settings>>((acc, s) => {
    if (!acc[s.category]) acc[s.category] = [];
    acc[s.category].push(s);
    return acc;
  }, {});

  const categoryLabels: Record<string, string> = {
    llm: "LLM 模型",
    crawl: "爬取配置",
    execution: "执行配置",
    auth: "登录凭据",
    cost: "成本系数",
    neo4j: "Neo4j",
    static: "静态配置（仅环境变量）",
  };

  const summary = tokenUsageSummary;

  // Stage labels for token usage
  const stageLabels: Record<string, string> = {
    extract: "特征提取",
    generate: "场景生成",
    plan: "规划",
    verify_text: "文本验证",
    verify_visual: "视觉验证",
    reflect: "反思",
    mutation: "变异生成",
    unknown: "其他",
  };

  // Model labels
  const modelLabels: Record<string, string> = {
    deepseek_v4_flash: "DeepSeek-V4-Flash",
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="h-6 w-6 text-blue-500" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t("settings.title")}</h2>
          <p className="text-muted-foreground">{t("settings.subtitle")}</p>
        </div>
      </div>

      <Tabs defaultValue="config">
        <TabsList>
          <TabsTrigger value="config" className="gap-2">
            <Settings className="h-4 w-4" />
            {t("settings.config")}
          </TabsTrigger>
          <TabsTrigger value="cost" className="gap-2">
            <DollarSign className="h-4 w-4" />
            {t("settings.costCoeff")}
          </TabsTrigger>
          <TabsTrigger value="tokens" className="gap-2">
            <BarChart3 className="h-4 w-4" />
            {t("settings.tokenUsage")}
          </TabsTrigger>
        </TabsList>

        {/* ── Configuration Tab ── */}
        <TabsContent value="config" className="space-y-4">
          {loadingSettings ? (
            <div className="space-y-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-40 w-full" />)}</div>
          ) : (
            Object.entries(grouped).filter(([cat]) => cat !== "cost" && cat !== "static").map(([category, items]) => (
              <Card key={category}>
                <CardHeader>
                  <CardTitle className="text-lg">{categoryLabels[category] || category}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {items.map((setting) => (
                    <SettingRow key={setting.key} setting={setting} onUpdate={handleUpdate} tFn={t} />
                  ))}
                </CardContent>
              </Card>
            ))
          )}
          {/* Static settings (read-only) */}
          {grouped.static && grouped.static.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">{categoryLabels.static}</CardTitle>
                <CardDescription>{t("settings.staticDesc")}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {grouped.static.map((setting) => (
                  <div key={setting.key} className="flex items-center gap-4">
                    <span className="text-sm font-medium min-w-[140px]">{setting.key}</span>
                    <div className="flex-1">
                      <Input value={setting.value} disabled className="bg-muted" />
                    </div>
                    <Badge variant="outline">{t("settings.readonly")}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Cost Coefficient Tab ── */}
        <TabsContent value="cost" className="space-y-4">
          {loadingSettings ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>{t("settings.costCoeffTitle")}</CardTitle>
                <CardDescription>{t("settings.costCoeffDesc")}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Currency selector */}
                <div className="flex items-center gap-4">
                  <span className="text-sm font-medium min-w-[140px]">{t("settings.currency")}</span>
                  <div className="flex-1">
                    <CurrencySelect
                      current={settings.find(s => s.key === "cost_currency")?.value || "USD"}
                      onUpdate={handleUpdate}
                    />
                  </div>
                </div>

                {/* Per-model cost coefficients */}
                {(["deepseek_v4_flash"] as const).map((mk) => (
                  <div key={mk} className="border rounded-lg p-4 space-y-2">
                    <h4 className="text-sm font-semibold">{modelLabels[mk] || mk}</h4>
                    <div className="grid grid-cols-2 gap-3">
                      <SettingRow
                        setting={settings.find(s => s.key === `cost_per_1m_tokens.${mk}.prompt`)!}
                        onUpdate={handleUpdate}
                        labelOverride={t("settings.promptCost")}
                        tFn={t}
                      />
                      <SettingRow
                        setting={settings.find(s => s.key === `cost_per_1m_tokens.${mk}.completion`)!}
                        onUpdate={handleUpdate}
                        labelOverride={t("settings.completionCost")}
                        tFn={t}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Token Usage Tab ── */}
        <TabsContent value="tokens" className="space-y-4">
          {loadingTokenUsage ? (
            <Skeleton className="h-60 w-full" />
          ) : !summary ? (
            <Card>
              <CardContent className="py-8">
                <p className="text-muted-foreground text-center">{t("settings.noTokenData")}</p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Summary cards */}
              <div className="grid gap-4 md:grid-cols-4">
                <StatMiniCard
                  title={t("settings.totalTokens")}
                  value={summary.total_tokens.toLocaleString()}
                  icon={BarChart3}
                />
                <StatMiniCard
                  title={t("settings.totalPromptTokens")}
                  value={summary.total_prompt_tokens.toLocaleString()}
                  icon={Eye}
                />
                <StatMiniCard
                  title={t("settings.totalCost")}
                  value={`${summary.total_cost.toFixed(4)} ${summary.currency}`}
                  icon={DollarSign}
                />
                <StatMiniCard
                  title={t("settings.callCount")}
                  value={summary.call_count.toString()}
                  icon={Settings}
                />
              </div>

              {/* Call detail table */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">{t("settings.callDetail")}</CardTitle>
                  <CardDescription>{t("settings.callDetailDesc")}</CardDescription>
                </CardHeader>
                <CardContent>
                  <DataListToolbar
                    searchValue={tokenDetailSearch}
                    onSearchChange={(v) => { setTokenDetailSearch(v); setTokenDetailPage(1); fetchTokenDetails(1, v, tokenDetailStage); }}
                    searchPlaceholder={t("search.placeholder")}
                    filters={[{
                      key: "stage",
                      placeholder: t("filter.status"),
                      options: [
                        { value: "extract", label: stageLabels.extract || "extract" },
                        { value: "generate", label: stageLabels.generate || "generate" },
                        { value: "plan", label: stageLabels.plan || "plan" },
                        { value: "verify_text", label: stageLabels.verify_text || "verify_text" },
                        { value: "verify_visual", label: stageLabels.verify_visual || "verify_visual" },
                        { value: "reflect", label: stageLabels.reflect || "reflect" },
                        { value: "mutation", label: stageLabels.mutation || "mutation" },
                      ],
                    }]}
                    filterValues={{ stage: tokenDetailStage }}
                    onFilterChange={(key, value) => {
                      if (key === "stage") { setTokenDetailStage(value); setTokenDetailPage(1); fetchTokenDetails(1, tokenDetailSearch, value); }
                    }}
                    totalCount={tokenDetailTotal}
                    totalCountLabel={t("pagination.items")}
                  />
                  {tokenDetails.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4">{t("settings.noTokenData")}</p>
                  ) : (
                    <>
                      <div className="overflow-x-auto mt-2">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b">
                              <th className="py-2 px-2 text-left font-medium">{t("settings.colTime")}</th>
                              <th className="py-2 px-2 text-left font-medium">{t("settings.colStage")}</th>
                              <th className="py-2 px-2 text-left font-medium">{t("settings.colModel")}</th>
                              <th className="py-2 px-2 text-right font-medium">{t("settings.colDuration")}</th>
                              <th className="py-2 px-2 text-right font-medium">{t("settings.colPrompt")}</th>
                              <th className="py-2 px-2 text-right font-medium">{t("settings.colCompletion")}</th>
                              <th className="py-2 px-2 text-right font-medium">{t("settings.colCost")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tokenDetails.map((r) => (
                              <tr key={r.id} className="border-b last:border-0 hover:bg-muted/50">
                                <td className="py-2 px-2 text-xs text-muted-foreground whitespace-nowrap">
                                  {r.timestamp ? formatDateTime(r.timestamp) : "-"}
                                </td>
                                <td className="py-2 px-2">
                                  <Badge variant="outline" className="text-xs">
                                    {stageLabels[r.pipeline_stage] || r.pipeline_stage}
                                  </Badge>
                                </td>
                                <td className="py-2 px-2 font-medium">{modelLabels[r.model_key] || r.model_name}</td>
                                <td className="py-2 px-2 text-right">{r.duration_seconds.toFixed(1)}s</td>
                                <td className="py-2 px-2 text-right">{r.prompt_tokens.toLocaleString()}</td>
                                <td className="py-2 px-2 text-right">{r.completion_tokens.toLocaleString()}</td>
                                <td className="py-2 px-2 text-right font-medium">
                                  {r.currency === "USD" ? "$" : "¥"}{r.cost_estimate.toFixed(4)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <PaginationControls
                        page={tokenDetailPage}
                        pageSize={20}
                        total={tokenDetailTotal}
                        onPageChange={(p) => { setTokenDetailPage(p); fetchTokenDetails(p); }}
                      />
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Per-stage breakdown */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">{t("settings.perStage")}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {Object.entries(summary.per_stage).sort((a, b) => b[1].cost - a[1].cost).map(([stage, data]) => (
                      <div key={stage} className="flex items-center gap-3 py-2 border-b last:border-0">
                        <span className="text-sm font-medium min-w-[100px]">{stageLabels[stage] || stage}</span>
                        <span className="text-sm text-muted-foreground flex-1">
                          {data.tokens.toLocaleString()} tokens · {data.call_count} calls
                        </span>
                        <Badge variant="secondary">
                          {data.cost.toFixed(4)} {summary.currency}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Helper components ──

function SettingRow({
  setting,
  onUpdate,
  labelOverride,
  tFn,
}: {
  setting: { key: string; value: string; is_secret: boolean; description: string; is_dynamic: boolean };
  onUpdate: (key: string, value: string) => Promise<void>;
  labelOverride?: string;
  tFn: (key: string) => string;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(setting.value);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onUpdate(setting.key, editValue);
    setSaving(false);
    setEditing(false);
  };

  return (
    <div className="flex items-center gap-4">
      <span className="text-sm font-medium min-w-[140px]">{labelOverride || setting.key}</span>
      <div className="flex-1">
        {editing ? (
          <Input
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            type={setting.is_secret ? "password" : "text"}
            disabled={saving}
          />
        ) : (
          <Input
            value={setting.value}
            readOnly
            type={setting.is_secret ? "password" : "text"}
            className="bg-muted cursor-default"
          />
        )}
      </div>
      {setting.is_dynamic ? (
        editing ? (
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSave} disabled={saving} className="gap-1">
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              {saving ? "..." : tFn("settings.save")}
            </Button>
            <Button size="sm" variant="outline" onClick={() => { setEditing(false); setEditValue(setting.value); }}>
              {tFn("settings.cancel")}
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)} className="gap-1">
            {tFn("settings.edit")}
          </Button>
        )
      ) : (
        <Badge variant="outline">{tFn("settings.readonly")}</Badge>
      )}
      {setting.description && (
        <span className="text-xs text-muted-foreground max-w-[200px]">{setting.description}</span>
      )}
    </div>
  );
}

function CurrencySelect({
  current,
  onUpdate,
}: {
  current: string;
  onUpdate: (key: string, value: string) => Promise<void>;
}) {
  const currencies = ["USD", "CNY"];
  return (
    <div className="flex gap-2">
      {currencies.map((c) => (
        <Button
          key={c}
          size="sm"
          variant={current === c ? "default" : "outline"}
          onClick={() => onUpdate("cost_currency", c)}
        >
          {c}
        </Button>
      ))}
    </div>
  );
}

function StatMiniCard({
  title,
  value,
  icon: Icon,
}: {
  title: string;
  value: string;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}