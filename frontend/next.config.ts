import type { NextConfig } from "next";

// In development /api/* goes to the FastAPI app (uvicorn api.main:app --port 8000).
const API = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
    output: "standalone",
    // A batch can include 50 emails, each requiring model extraction.
    experimental: { proxyTimeout: 300_000 },
    async rewrites() {
        return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
    },
};

export default nextConfig;
