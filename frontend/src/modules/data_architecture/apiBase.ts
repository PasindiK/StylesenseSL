/**
 * Data architecture lakehouse API base URL (must include `/api` path prefix).
 *
 * Set in `.env.local` (not committed):
 *   VITE_DATA_ARCH_API_URL=http://127.0.0.1:8003/api
 *
 * Using this avoids depending on the root Vite `/api` proxy so the DA dashboard
 * works when only uvicorn on port 8003 is running.
 */
function normalizeBase(raw: string): string {
  const t = raw.trim().replace(/\/+$/, "");
  return t.endsWith("/api") ? t : `${t}/api`;
}

export const DATA_ARCH_API_BASE = normalizeBase(
  (import.meta.env.VITE_DATA_ARCH_API_URL as string | undefined) ||
    "http://127.0.0.1:8003/api",
);
