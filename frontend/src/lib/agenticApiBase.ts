/** Agentic FastAPI base (must include `/api` for localhost, or `/re/agentic` with Vercel rewrites). */
function stripTrailingSlash(url: string) {
  return url.replace(/\/$/, '')
}

/** True when VITE_API_URL was pointed at the data-mesh proxy — must not drive cart/chat/dashboard. */
function looksLikeMeshApiBase(url: string) {
  return /(^|\/)re\/mesh(\/|$)/.test(url) || /\/mesh\/?$/.test(url)
}

export function getAgenticApiBase(): string {
  const explicit = import.meta.env.VITE_AGENTIC_API_URL as string | undefined
  if (explicit) return stripTrailingSlash(explicit)

  const generic = import.meta.env.VITE_API_URL as string | undefined
  if (generic && !looksLikeMeshApiBase(generic)) {
    return stripTrailingSlash(generic)
  }

  // Prod default matches vercel.json `/re/agentic` rewrite; dev uses local FastAPI `/api`.
  const fallback = import.meta.env.PROD ? '/re/agentic' : '/api'
  return stripTrailingSlash(fallback)
}
