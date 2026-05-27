import type { Metadata } from "next";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppLayout } from "@/components/AppLayout";

export const metadata: Metadata = {
  title: "OmniTest - 智能化全维测试平台",
  description: "基于大模型的测试场景生成与智能执行工具",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">
        <TooltipProvider>
          <AppLayout>{children}</AppLayout>
        </TooltipProvider>
      </body>
    </html>
  );
}