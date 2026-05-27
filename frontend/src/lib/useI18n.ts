"use client";

import { useState, useEffect, useCallback } from "react";
import { Locale, t, getLocale, setLocale, toggleLocale } from "@/lib/i18n";

export function useI18n() {
  const [locale, setLocalLocale] = useState<Locale>(getLocale());

  useEffect(() => {
    setLocalLocale(getLocale());
  }, []);

  const switchLocale = useCallback(() => {
    const next = toggleLocale();
    setLocalLocale(next);
    // Force re-render by dispatching a custom event
    window.dispatchEvent(new Event("locale-changed"));
  }, []);

  // Listen for locale changes from other components
  useEffect(() => {
    const handler = () => {
      setLocalLocale(getLocale());
    };
    window.addEventListener("locale-changed", handler);
    return () => window.removeEventListener("locale-changed", handler);
  }, []);

  return {
    locale,
    t,
    switchLocale,
    setLocale: (l: Locale) => {
      setLocale(l);
      setLocalLocale(l);
      window.dispatchEvent(new Event("locale-changed"));
    },
  };
}