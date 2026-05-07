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

    // `next dev` only: implicit local backend when BACKEND_API_URL is unset.
    if (process.env.NODE_ENV !== "production") {
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

    if (process.env.NODE_ENV === "production") {
      console.warn(
        "[next.config] BACKEND_API_URL unset — omitting API rewrites in this production build. " +
          "Set BACKEND_API_URL at build time, or use NEXT_PUBLIC_API_URL so client calls hit the backend directly."
      );
    }

    return [];
  },
};

export default nextConfig;
