"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ZoomIn, ZoomOut, Maximize2, Minimize2 } from "lucide-react";
import { getScreenshotUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/useI18n";

interface ScreenshotCompareProps {
  expectedScreenshotPath?: string;
  actualScreenshotPath?: string;
  expectedLabel?: string;
  actualLabel?: string;
  diffDescription?: string;
  passed?: boolean;
}

export function ScreenshotCompare({
  expectedScreenshotPath,
  actualScreenshotPath,
  expectedLabel,
  actualLabel,
  diffDescription,
  passed = true,
}: ScreenshotCompareProps) {
  const { t } = useI18n();
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);

  const hasExpected = expectedScreenshotPath;
  const hasActual = actualScreenshotPath;

  const expectedLabelText = expectedLabel ?? t("screenshot.expected");
  const actualLabelText = actualLabel ?? t("screenshot.actual");

  return (
    <Card className={cn("border-l-4", passed ? "border-l-green-500" : "border-l-red-500")}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">{t("screenshot.title")}</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={passed ? "default" : "destructive"}>
              {passed ? t("screenshot.match") : t("screenshot.mismatch")}
            </Badge>
            <div className="flex gap-1">
              <Button
                size="icon"
                variant="outline"
                className="h-7 w-7"
                onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}
              >
                <ZoomOut className="h-3 w-3" />
              </Button>
              <Button
                size="icon"
                variant="outline"
                className="h-7 w-7"
                onClick={() => setZoom(Math.min(3, zoom + 0.25))}
              >
                <ZoomIn className="h-3 w-3" />
              </Button>
              <Button
                size="icon"
                variant="outline"
                className="h-7 w-7"
                onClick={() => setFullscreen(!fullscreen)}
              >
                {fullscreen ? (
                  <Minimize2 className="h-3 w-3" />
                ) : (
                  <Maximize2 className="h-3 w-3" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            "grid gap-4",
            hasExpected && hasActual ? "grid-cols-2" : "grid-cols-1"
          )}
        >
          {/* Expected screenshot */}
          {hasExpected && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-muted-foreground text-center">
                {expectedLabelText}
              </div>
              <div
                className={cn(
                  "relative overflow-hidden rounded-md border bg-gray-50",
                  fullscreen ? "h-[500px]" : "h-[300px]"
                )}
              >
                <img
                  src={getScreenshotUrl(expectedScreenshotPath)}
                  alt={expectedLabelText}
                  className="w-full h-full object-contain transition-transform"
                  style={{ transform: `scale(${zoom})` }}
                />
              </div>
            </div>
          )}

          {/* Actual screenshot */}
          {hasActual && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-muted-foreground text-center">
                {actualLabelText}
              </div>
              <div
                className={cn(
                  "relative overflow-hidden rounded-md border bg-gray-50",
                  fullscreen ? "h-[500px]" : "h-[300px]"
                )}
              >
                <img
                  src={getScreenshotUrl(actualScreenshotPath)}
                  alt={actualLabelText}
                  className="w-full h-full object-contain transition-transform"
                  style={{ transform: `scale(${zoom})` }}
                />
                {/* Diff highlight overlay when not passed */}
                {!passed && (
                  <div className="absolute inset-0 border-2 border-red-500 rounded-md opacity-60" />
                )}
              </div>
            </div>
          )}
        </div>

        {/* Diff description */}
        {diffDescription && !passed && (
          <div className="mt-4 p-3 rounded-md bg-red-50 border border-red-200">
            <h4 className="text-sm font-semibold text-red-800 mb-1">
              {t("screenshot.diffDetected")}
            </h4>
            <p className="text-sm text-red-700">{diffDescription}</p>
          </div>
        )}

        {/* No screenshots available */}
        {!hasExpected && !hasActual && (
          <div className="text-sm text-muted-foreground py-4 text-center">
            {t("screenshot.noScreenshots")}
          </div>
        )}
      </CardContent>
    </Card>
  );
}