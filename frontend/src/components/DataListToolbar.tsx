"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, X } from "lucide-react";
import { useI18n } from "@/lib/useI18n";

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterConfig {
  key: string;
  placeholder: string;
  options: FilterOption[];
}

interface DataListToolbarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  filters?: FilterConfig[];
  filterValues?: Record<string, string>;
  onFilterChange?: (key: string, value: string) => void;
  totalCount?: number;
  totalCountLabel?: string;
}

export function DataListToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder,
  filters = [],
  filterValues = {},
  onFilterChange,
  totalCount,
  totalCountLabel,
}: DataListToolbarProps) {
  const { t, locale } = useI18n();
  const [localSearch, setLocalSearch] = useState(searchValue);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { setLocalSearch(searchValue); }, [searchValue]);

  const handleSearchInput = useCallback((value: string) => {
    setLocalSearch(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onSearchChange(value), 300);
  }, [onSearchChange]);

  // Get display label for a selected filter value
  const getSelectedLabel = (f: FilterConfig, value: string) => {
    if (!value) return "";
    const opt = f.options.find((o) => o.value === value);
    return opt?.label || value;
  };

  return (
    <div className="flex items-center gap-3 py-3 flex-wrap">
      <div className="relative flex-1 min-w-[200px] max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={localSearch}
          onChange={(e) => handleSearchInput(e.target.value)}
          placeholder={searchPlaceholder || t("search.placeholder")}
          className="pl-9 h-9"
        />
      </div>
      {filters.map((f) => {
        const currentVal = filterValues[f.key] || "";
        const selectedLabel = getSelectedLabel(f, currentVal);
        return (
          <div key={f.key} className="flex items-center gap-1">
            <Select
              value={currentVal ? currentVal : "__all__"}
              onValueChange={(v) => { if (v) onFilterChange?.(f.key, v === "__all__" ? "" : v); }}
            >
              <SelectTrigger className="h-9 w-auto min-w-[140px] max-w-[200px] bg-background border-input">
                <SelectValue placeholder={f.placeholder}>
                  {currentVal ? selectedLabel : f.placeholder}
                </SelectValue>
              </SelectTrigger>
              <SelectContent sideOffset={4}>
                <SelectItem value="__all__" className="font-medium text-muted-foreground">
                  {t("filter.all")}
                </SelectItem>
                {f.options.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value} className="py-2">
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {currentVal && (
              <button
                onClick={() => onFilterChange?.(f.key, "")}
                className="h-9 w-9 inline-flex items-center justify-center rounded-md border border-input bg-background hover:bg-muted text-muted-foreground"
                title={locale === "zh" ? "清除筛选" : "Clear filter"}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        );
      })}
      {totalCount !== undefined && totalCountLabel && (
        <span className="text-sm text-muted-foreground ml-auto whitespace-nowrap">
          {t("pagination.total")} {totalCount} {totalCountLabel}
        </span>
      )}
    </div>
  );
}