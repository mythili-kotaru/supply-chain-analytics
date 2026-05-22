/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy API calls to local backend services during dev.
  //
  // WHY rewrites instead of route files?
  // next.config rewrites fire at the edge before any route.ts is evaluated.
  // They are the correct Next.js 14 pattern for proxying to external services.
  //
  // IMPORTANT: destination must include the full path prefix that FastAPI expects.
  // FastAPI mounts all routes at /api/dashboard/... so the destination must
  // preserve that prefix: http://localhost:8003/api/dashboard/:path*
  async rewrites() {
    return [
      {
        source: "/api/dashboard/:path*",
        destination: "http://localhost:8003/api/dashboard/:path*",
      },
      {
        source: "/api/allocation/:path*",
        destination: "http://localhost:8001/:path*",
      },
      {
        source: "/api/replenishment/:path*",
        destination: "http://localhost:8002/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
