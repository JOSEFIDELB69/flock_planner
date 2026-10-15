import type { NextConfig } from "next";

// El navegador habla solo con Next.js; las llamadas /api/v1/* se reenvían al backend FastAPI.
// Así la IA (Claude Code) y cualquier secreto quedan exclusivamente en el backend.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Las operaciones de IA (análisis, backlog) pueden tardar varios minutos: el proxy no debe cortarlas.
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_BASE_URL}/api/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
