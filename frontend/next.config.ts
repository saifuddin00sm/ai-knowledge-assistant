import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",      // <--- Enables static exports
  images: {
    unoptimized: true,   // <--- Required for static exports on manual uploads
  },
};

export default nextConfig;