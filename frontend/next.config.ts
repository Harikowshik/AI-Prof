import type { NextConfig } from "next";

const isNetlify = process.env.NETLIFY === "true";

const nextConfig: NextConfig = {
  // Docker/Render uses standalone; Netlify static export publishes frontend/out
  output: isNetlify ? "export" : "standalone",
  images: { unoptimized: true },
};

export default nextConfig;
