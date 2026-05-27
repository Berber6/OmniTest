"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  ClipboardList,
  PlayCircle,
  Bug,
  Wifi,
  WifiOff,
  Languages,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/lib/store";
import { useI18n } from "@/lib/useI18n";

const navItems = [
  { href: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { href: "/features", labelKey: "nav.features", icon: GitBranch },
  { href: "/scenarios", labelKey: "nav.scenarios", icon: ClipboardList },
  { href: "/executions", labelKey: "nav.executions", icon: PlayCircle },
  { href: "/mutations", labelKey: "nav.mutations", icon: Bug },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const wsConnected = useAppStore((s) => s.wsConnected);
  const { locale, t, switchLocale } = useI18n();

  return (
    <div className="min-h-screen flex">
      <aside className="w-64 bg-card border-r border-border flex flex-col">
        <div className="p-6 border-b border-border">
          <div className="flex items-center gap-3">
            {/* OmniTest inline SVG logo — shield with checkmark */}
            <svg width="28" height="28" viewBox="0 0 32 32" className="shrink-0">
              <defs>
                <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#3B82F6"/>
                  <stop offset="100%" stopColor="#8B5CF6"/>
                </linearGradient>
              </defs>
              <path d="M16 2 L4 8 L4 16 C4 24 16 30 16 30 C16 30 28 24 28 16 L28 8 Z" fill="url(#logo-g)"/>
              <path d="M12 16 L14.5 18.5 L20 12" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
            </svg>
            <div>
              <h1 className="text-xl font-bold tracking-tight">{t("brand.name")}</h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                {t("brand.tagline")}
              </p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border space-y-3">
          {/* Language toggle */}
          <button
            onClick={switchLocale}
            className="flex items-center gap-2 text-xs text-muted-foreground hover:text-accent-foreground transition-colors w-full"
          >
            <Languages className="h-3.5 w-3.5" />
            <span>{locale === "zh" ? "中文 / English" : "English / 中文"}</span>
          </button>

          {/* WebSocket status */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {wsConnected ? (
              <Wifi className="h-3 w-3 text-green-500" />
            ) : (
              <WifiOff className="h-3 w-3 text-red-500" />
            )}
            {wsConnected ? t("ws.connected") : t("ws.disconnected")}
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <div className="p-8 max-w-7xl">{children}</div>
      </main>
    </div>
  );
}