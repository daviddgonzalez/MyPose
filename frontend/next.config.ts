import type { NextConfig } from "next";

/**
 * Rewrites are resolved when Next loads this config (`next dev` / `next build`).
 * `BACKEND_API_URL` must be present at **build time** for production images (Docker, Vercel build).
 * Do not fall back to `localhost` in production — that gets baked into the build and breaks
 * when the backend is on another host. Use `NEXT_PUBLIC_API_URL` for direct browser→API calls
 * if you intentionally skip rewrites.
 */
function getBackendRewriteBase(): string {
  const raw = process.env.BACKEND_API_URL?.trim() ?? "";
  return raw.replace(/\/$/, "");
}

const nextConfig: NextConfig = {
  devIndicators: false,
  async rewrites() {
    const backendUrl = getBackendRewriteBase();

    if (backendUrl.length > 0) {
      return [
        {
          source: "/api/v1/:path*",
          destination: `${backendUrl}/api/v1/:path*`,
        },
        {
          source: "/health",
          destination: `${backendUrl}/health`,
        },
      ];
    }

    // Only `next dev` sets NODE_ENV=development. Treat anything else as a production-ish
    // build so unset NODE_ENV during `docker build` / CI does not hardcode localhost.
    if (process.env.NODE_ENV === "development") {
      const local = "http://localhost:8000";
      return [
        {
          source: "/api/v1/:path*",
          destination: `${local}/api/v1/:path*`,
        },
        {
          source: "/health",
          destination: `${local}/health`,
        },
      ];
    }

    console.warn(
      "[next.config] BACKEND_API_URL unset — omitting API rewrites in this build. " +
        "Set BACKEND_API_URL at build time (or NEXT_PUBLIC_API_URL for direct browser API calls)."
    );

    return [];
  },
};

export default nextConfig;
