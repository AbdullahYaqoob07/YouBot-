import type { NextConfig } from "next";

const backendBase = (
  process.env.YOUBOT_API_BASE_URL ??
  process.env.NEXT_PUBLIC_YOUBOT_API_BASE_URL ??
  "http://127.0.0.1:8000"
).replace(/\/+$/, "")

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${backendBase}/:path*`,
      },
    ]
  },
};

export default nextConfig;
