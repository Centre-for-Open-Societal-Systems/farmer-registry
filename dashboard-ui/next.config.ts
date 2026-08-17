import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Ships the server and just the traced dependencies, so the runtime image
  // does not need a node_modules install.
  output: "standalone",
  compress: true, // Enable gzip compression
  poweredByHeader: false, // Remove X-Powered-By header for security
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          // Allow embedding in iframes (set frame ancestors as needed)
          { key: 'X-Frame-Options', value: 'ALLOWALL' },
          { key: 'Content-Security-Policy', value: "frame-ancestors *" },
        ],
      },
    ];
  },
};

export default nextConfig;
