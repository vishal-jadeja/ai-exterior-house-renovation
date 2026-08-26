import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

// "standalone" is for the Docker image (infra/Dockerfile.web copies .next/standalone).
// Vercel does its own output tracing and fails with standalone enabled
// (missing .next/next-server.js.nft.json), so skip it there.
const nextConfig: NextConfig = {
  output: process.env.VERCEL ? undefined : "standalone",
  reactStrictMode: true,
  images: { remotePatterns: [{ protocol: "http", hostname: "**" }, { protocol: "https", hostname: "**" }] },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
