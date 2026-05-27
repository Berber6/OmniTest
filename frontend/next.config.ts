import type { NextConfig } from "next";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
      },
      {
        protocol: "https",
        hostname: new URL(API_BASE_URL).hostname,
      },
      {
        protocol: "http",
        hostname: new URL(API_BASE_URL).hostname,
        port: new URL(API_BASE_URL).port || "80",
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE_URL}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${API_BASE_URL}/ws/:path*`,
      },
      {
        source: "/screenshots/:path*",
        destination: `${API_BASE_URL}/api/screenshots/:path*`,
      },
    ];
  },
};

export default nextConfig;