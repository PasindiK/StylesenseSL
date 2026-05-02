import { useState } from 'react'
import type { AutoDetectionResponse } from '../types'
import { DATA_ARCH_API_BASE } from '../../../apiBase'

interface UseAutoDetectBaselineResult {
  detectBaseline: (file: File) => Promise<AutoDetectionResponse | null>
  loading: boolean
  result: AutoDetectionResponse | null
  error: string | null
  reset: () => void
}

export function useAutoDetectBaseline(): UseAutoDetectBaselineResult {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AutoDetectionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const detectBaseline = async (file: File): Promise<AutoDetectionResponse | null> => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('upload_file', file)

      const response = await fetch(`${DATA_ARCH_API_BASE}/drift/auto-detect-baseline`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Detection failed: ${response.statusText} - ${errorText}`)
      }

      const data: AutoDetectionResponse = await response.json()
      setResult(data)
      return data
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error during baseline detection'
      setError(errorMsg)
      console.error('[BASELINE AUTO-DETECT] Error:', err)
      return null
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setResult(null)
    setError(null)
  }

  return { detectBaseline, loading, result, error, reset }
}
