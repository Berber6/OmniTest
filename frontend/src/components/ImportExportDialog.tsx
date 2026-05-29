"use client";

import { useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, Upload, FileText, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { useI18n } from "@/lib/useI18n";
import * as api from "@/lib/api";
import { useAppStore } from "@/lib/store";

type DataType = "features" | "scenarios" | "executions" | "bundle";
type Mode = "export" | "import";

interface ImportExportDialogProps {
  dataType: DataType;
  mode: Mode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ImportExportDialog({
  dataType,
  mode,
  open,
  onOpenChange,
}: ImportExportDialogProps) {
  const { t } = useI18n();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [parsedData, setParsedData] = useState<unknown | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [itemCount, setItemCount] = useState<number>(0);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<api.ImportResult | null>(null);
  const [includeScreenshots, setIncludeScreenshots] = useState(true);
  const [exporting, setExporting] = useState(false);

  const store = useAppStore();

  const typeLabel = t(`io.type${dataType.charAt(0).toUpperCase() + dataType.slice(1)}`);

  function resetState() {
    setParsedData(null);
    setParseError(null);
    setFileName("");
    setItemCount(0);
    setImporting(false);
    setImportResult(null);
  }

  function handleClose() {
    resetState();
    onOpenChange(false);
  }

  // --- Export logic ---
  async function handleExport() {
    setExporting(true);
    try {
      let blob: Blob;
      switch (dataType) {
        case "features":
          blob = await api.exportFeatures();
          break;
        case "scenarios":
          blob = await api.exportScenarios();
          break;
        case "executions":
          blob = await api.exportExecutions(includeScreenshots);
          break;
        case "bundle":
          blob = await api.exportBundle(includeScreenshots);
          break;
      }

      // Trigger download
      const date = new Date().toISOString().slice(0, 10);
      const filename = `omnitest_${dataType}_${date}.json`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  // --- Import logic ---
  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setFileName(file.name);
    setImportResult(null);

    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const text = evt.target?.result as string;
        const parsed = JSON.parse(text);

        // Count items based on data type
        let count = 0;
        if (parsed.type === "bundle" && parsed.data) {
          // Bundle: sum all types
          const data = parsed.data;
          count = (data.features?.length ?? 0) + (data.scenarios?.length ?? 0) + (data.executions?.length ?? 0);
        } else if (parsed.data && Array.isArray(parsed.data)) {
          count = parsed.data.length;
        } else if (Array.isArray(parsed)) {
          count = parsed.length;
        } else if (parsed.data && typeof parsed.data === "object") {
          // Might be a bundle without type field
          const data = parsed.data;
          count = (data.features?.length ?? 0) + (data.scenarios?.length ?? 0) + (data.executions?.length ?? 0);
        }

        setParsedData(parsed);
        setItemCount(count);
        setParseError(null);
      } catch {
        setParseError(t("io.invalidFormat"));
        setParsedData(null);
        setItemCount(0);
      }
    };
    reader.readAsText(file);
  }

  async function handleImport() {
    if (!parsedData) return;
    setImporting(true);

    try {
      let result: api.ImportResult;
      switch (dataType) {
        case "features":
          result = await api.importFeatures(parsedData);
          store.fetchFeatures();
          break;
        case "scenarios":
          result = await api.importScenarios(parsedData);
          store.fetchScenarios();
          break;
        case "executions":
          result = await api.importExecutions(parsedData);
          store.fetchExecutions();
          break;
        case "bundle":
          result = await api.importBundle(parsedData);
          store.fetchFeatures();
          store.fetchScenarios();
          store.fetchExecutions();
          break;
      }
      setImportResult(result);
      store.fetchDashboardStats();
    } catch (e) {
      setImportResult({
        success: false,
        imported_count: 0,
        message: e instanceof Error ? e.message : t("io.importFailed"),
      });
    } finally {
      setImporting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === "export"
              ? t("io.exportTitle").replace("{type}", typeLabel)
              : t("io.importTitle").replace("{type}", typeLabel)}
          </DialogTitle>
          <DialogDescription>
            {mode === "export"
              ? t("io.exportDesc").replace("{type}", typeLabel)
              : t("io.importDesc").replace("{type}", typeLabel)}
          </DialogDescription>
        </DialogHeader>

        {mode === "export" ? (
          <div className="space-y-4">
            {(dataType === "executions" || dataType === "bundle") && (
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="include-screenshots"
                  checked={includeScreenshots}
                  onChange={(e) => setIncludeScreenshots(e.target.checked)}
                  className="rounded border-gray-300"
                />
                <label htmlFor="include-screenshots" className="text-sm">
                  {t("io.includeScreenshots")}
                </label>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {/* Import result already shown */}
            {importResult && (
              <div className="space-y-2">
                {importResult.success ? (
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                    <span className="text-sm font-medium">{t("io.importSuccess")}</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    <span className="text-sm font-medium text-red-600">{t("io.importFailed")}</span>
                  </div>
                )}
                <p className="text-sm">
                  {t("io.imported").replace("{count}", String(importResult.imported_count))}
                </p>
                {(importResult.skipped_count ?? 0) > 0 && (
                  <p className="text-sm text-muted-foreground">
                    {t("io.skipped").replace("{count}", String(importResult.skipped_count ?? 0))}
                  </p>
                )}
                {!importResult.success && importResult.message && (
                  <p className="text-sm text-red-600">{importResult.message}</p>
                )}
              </div>
            )}

            {/* File picker (hidden if result already shown) */}
            {!importResult && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json"
                  className="hidden"
                  onChange={handleFileSelect}
                />
                <Button
                  variant="outline"
                  className="gap-2 w-full"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-4 w-4" />
                  {fileName ? `${fileName}` : t("io.selectFile")}
                </Button>

                {parseError && (
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    <span className="text-sm text-red-600">{parseError}</span>
                  </div>
                )}

                {parsedData && !parseError && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-blue-500" />
                      <Badge variant="secondary">
                        {t("io.itemsFound").replace("{count}", String(itemCount))}
                      </Badge>
                    </div>
                    {dataType !== "executions" && dataType !== "bundle" && (
                      <p className="text-sm text-orange-600">
                        {t("io.replaceWarning").replace("{type}", typeLabel)}
                      </p>
                    )}
                    {dataType === "executions" && (
                      <p className="text-sm text-muted-foreground">
                        {t("io.mergeNote")}
                      </p>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <DialogFooter>
          {mode === "export" ? (
            <Button onClick={handleExport} disabled={exporting} className="gap-2">
              {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {exporting ? t("io.importing") : t("io.export")}
            </Button>
          ) : (
            !importResult && (
              <Button
                onClick={handleImport}
                disabled={!parsedData || importing || !!parseError}
                className="gap-2"
              >
                {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {importing ? t("io.importing") : t("io.confirmImport")}
              </Button>
            )
          )}
          <Button variant="outline" onClick={handleClose}>
            {importResult ? "OK" : "Cancel"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}