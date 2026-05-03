/**
 * Data architecture lakehouse API base URL.
 *
 * Local / direct backend examples (`.env.local`):
 *   VITE_DATA_ARCH_API_URL=http://127.0.0.1:8003/api
 *   or http://127.0.0.1:8003 — we append `/api` when needed.
 *
 * Vercel: use the rewrite prefix only:
 *   VITE_DATA_ARCH_API_URL=/re/arch
 *   (do not add `/api`; vercel.json already forwards to `.../api/<path>`.)
 *
 * Using this avoids depending on the root Vite `/api` proxy so the DA dashboard
 * works when only uvicorn on port 8003 is running.
 */
function normalizeBase(raw: string): string {
  const t = raw.trim().replace(/\/+$/, "")
  if (t.endsWith("/api")) return t
  // Vercel `vercel.json` maps `/re/arch/<path>` → `http://<vm>:8003/api/<path>`.
  // Base must be `/re/arch` only; appending `/api` here produced `/re/arch/api/...` and a
  // double `/api/api/` on the origin (404).
  if (t.startsWith("/re/")) return t
  return `${t}/api`
}

export const DATA_ARCH_API_BASE = normalizeBase(
  (import.meta.env.VITE_DATA_ARCH_API_URL as string | undefined) ||
    "http://127.0.0.1:8003/api",
);
