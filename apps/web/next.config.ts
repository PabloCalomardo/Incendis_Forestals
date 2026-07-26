import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@wip/shared-types", "@wip/config", "@wip/ui"],
};

export default nextConfig;
