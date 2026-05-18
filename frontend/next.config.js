/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow API calls to local backend services during dev
  async rewrites() {
    return [
      {
        source: "/api/dashboard/:path*",
        destination: "http://localhost:8003/:path*", // dashboard FastAPI (Day 2)
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
