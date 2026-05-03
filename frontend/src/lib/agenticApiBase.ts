/** Agentic FastAPI base (must include `/api` for localhost, or `/re/agentic` with Vercel rewrites). */
export function getAgenticApiBase(): string {
  const a = import.meta.env.VITE_AGENTIC_API_URL as string | undefined
  const b = import.meta.env.VITE_API_URL as string | undefined
  return (a || b || '/api').replace(/\/$/, '')
}
