import type { NextConfig } from "next";

// In development /api/* goes to the FastAPI app (uvicorn api.main:app --port 8000).
const API = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
    output: "standalone",
    async rewrites() {
        return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
    },
};

export default nextConfig;
