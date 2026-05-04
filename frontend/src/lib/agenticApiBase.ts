/** Agentic FastAPI base (must include `/api` for localhost, or `/re/agentic` with Vercel rewrites). */
function stripTrailingSlash(url: string) {
  return url.replace(/\/$/, '')
}

/**
 * Vercel same-origin proxies for *other* services. If these are pasted into
 * VITE_AGENTIC_API_URL or VITE_API_URL, cart/chat/dashboard would hit the wrong VM.
 */
const NON_AGENTIC_RE_PREFIXES = ['/re/mesh', '/re/fabric', '/re/arch'] as const

function isNonAgenticVercelProxy(url: string): boolean {
  const u = stripTrailingSlash(url.trim())
  return NON_AGENTIC_RE_PREFIXES.some((p) => u === p || u.startsWith(`${p}/`))
}

/** Data Architecture local API (port 8003 in this repo). Must not be used for FeatureOps / semantic drift. */
function isDataArchitectureApiUrl(url: string): boolean {
  const u = stripTrailingSlash(url.trim().toLowerCase())
  if (/:8003(\/|$)/.test(u)) {
    return true
  }
  const arch = (import.meta.env.VITE_DATA_ARCH_API_URL as string | undefined)?.trim()
  if (!arch) {
    return false
  }
  return stripTrailingSlash(arch.toLowerCase()) === u
}

export function getAgenticApiBase(): string {
  const explicit = (import.meta.env.VITE_AGENTIC_API_URL as string | undefined)?.trim()
  if (explicit && !isNonAgenticVercelProxy(explicit)) {
    return stripTrailingSlash(explicit)
  }

  const generic = (import.meta.env.VITE_API_URL as string | undefined)?.trim()
  if (generic && !isNonAgenticVercelProxy(generic) && !isDataArchitectureApiUrl(generic)) {
    return stripTrailingSlash(generic)
  }

  // Prod default matches vercel.json `/re/agentic` rewrite; dev uses local FastAPI `/api`.
  const fallback = import.meta.env.PROD ? '/re/agentic' : '/api'
  return stripTrailingSlash(fallback)
}
