/**
 * Backend drift detection API helpers.
 * Replaces local drift computation with server-side learned scoring.
 */

export async function detectInternalDrift(
  apiBase: string,
  datasetName: string,
  datasetRows: Record<string, any>[]
): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/detect-internal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_name: datasetName,
      dataset_rows: datasetRows,
    }),
  })

  if (!response.ok) {
    throw new Error(`Internal drift detection failed: ${response.statusText}`)
  }

  return response.json()
}

export async function detectExternalDrift(
  apiBase: string,
  datasetName: string,
  baselineVersion: string,
  currentVersion: string,
  baselineRows: Record<string, any>[],
  currentRows: Record<string, any>[],
  schemaInfo?: Record<string, any>
): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/detect-external`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_name: datasetName,
      baseline_version: baselineVersion,
      current_version: currentVersion,
      baseline_rows: baselineRows,
      current_rows: currentRows,
      schema_info: schemaInfo,
    }),
  })

  if (!response.ok) {
    throw new Error(`External drift detection failed: ${response.statusText}`)
  }

  return response.json()
}

export async function getDriftResult(apiBase: string, runId: string): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/results/${runId}`)

  if (!response.ok) {
    throw new Error(`Failed to retrieve drift result: ${response.statusText}`)
  }

  return response.json()
}

export async function trainDriftScorer(apiBase: string, labeledDriftRuns: any[]): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/train-scorer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      labeled_drift_runs: labeledDriftRuns,
    }),
  })

  if (!response.ok) {
    throw new Error(`Drift scorer training failed: ${response.statusText}`)
  }

  return response.json()
}

export async function getScorerStats(apiBase: string): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/scorer-stats`)

  if (!response.ok) {
    throw new Error(`Failed to get scorer stats: ${response.statusText}`)
  }

  return response.json()
}

export async function labelDriftResult(
  apiBase: string,
  runId: string,
  label: 'low' | 'moderate' | 'high'
): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/label-result?run_id=${runId}&label=${label}`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(`Failed to label drift result: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Convert comprehensive drift result to UI-friendly format.
 */
export function convertDriftResultToUIFormat(
  backendResult: any,
  columnName?: string
): Record<string, any> {
  const result = backendResult.result || backendResult

  // Map backend severity to UI severity
  const severityMap: Record<string, 'LOW' | 'MODERATE' | 'HIGH' | 'NONE'> = {
    low: 'LOW',
    moderate: 'MODERATE',
    high: 'HIGH',
  }

  return {
    drift_run_id: result.drift_run_id,
    column_name: columnName || '',
    baseline_version: result.dataset_version_a,
    current_version: result.dataset_version_b,
    drift_detected: result.drift_detected,
    drift_severity: severityMap[result.severity] || 'NONE',
    score: result.overall_drift_score,
    evidence: result.reasons,
    explanation: `Statistical: ${(result.statistical_drift_score * 100).toFixed(1)}%, Semantic: ${(result.semantic_drift_score * 100).toFixed(1)}%, Behavioral: ${(result.behavioral_drift_score * 100).toFixed(1)}%`,
    recommended_action: result.drift_detected ? 'Review and approve with caution' : 'Safe to proceed',
    detailed_signals: {
      statistical: result.statistical_signals,
      semantic: result.semantic_signals,
      behavioral: result.behavioral_signals,
    },
  }
}

/**
 * Map backend statistical signals to column-level UI results.
 */
export function mapBackendSignalsToUIResults(
  backendResult: any,
  datasetName: string
): Array<Record<string, any>> {
  const result = backendResult.result || backendResult
  const results = []

  if (result.statistical_signals) {
    for (const sig of result.statistical_signals) {
      results.push({
        column_name: sig.column_name,
        field_type: sig.dtype || 'unknown',
        baseline_version: result.dataset_version_a,
        current_version: result.dataset_version_b,
        drift_severity: sig.ks_pvalue && sig.ks_pvalue < 0.05 ? 'MODERATE' : 'LOW',
        score: Math.min(1.0, (sig.ks_statistic || 0) + (sig.chi2_statistic || 0) / 50),
        evidence: [
          sig.ks_pvalue ? `KS test p-value: ${sig.ks_pvalue.toFixed(4)}` : '',
          sig.chi2_pvalue ? `Chi-square p-value: ${sig.chi2_pvalue.toFixed(4)}` : '',
          sig.mean_delta ? `Mean shift: ${sig.mean_delta.toFixed(4)}` : '',
          sig.std_delta ? `Std shift: ${sig.std_delta.toFixed(4)}` : '',
          ...(sig.new_categories || []).map((cat: string) => `New category: ${cat}`),
          ...(sig.missing_categories || []).map((cat: string) => `Missing category: ${cat}`),
        ].filter((s) => s),
        explanation: `Distribution analysis for ${sig.column_name} (${sig.dtype})`,
        recommended_action: 'Review distribution changes',
      })
    }
  }

  return results
}

/**
 * NEW: Call the ML-based drift detector orchestrator.
 * Uses all 4 agents (Profiler, Baseline, Anchor, Scoring).
 * Returns complete drift analysis with profiler, explanations, and row-level results.
 */
export async function detectDriftFull(
  apiBase: string,
  file: File,
  baselineKey?: string
): Promise<any> {
  const formData = new FormData()
  formData.append('file', file)
  if (baselineKey) {
    formData.append('baseline_key', baselineKey)
  }

  const response = await fetch(`${apiBase}/featureops/drift/detect-full`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`Full drift detection failed: ${response.statusText}`)
  }

  return response.json()
}

export async function getPredefinedBaselines(apiBase: string): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/predefined-baselines`)

  if (!response.ok) {
    throw new Error(`Failed to fetch predefined baselines: ${response.statusText}`)
  }

  return response.json()
}

/**
 * Get orchestrator statistics and agent status.
 */
export async function getOrchestratorStats(apiBase: string): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/orchestrator/stats`)

  if (!response.ok) {
    throw new Error(`Failed to get orchestrator stats: ${response.statusText}`)
  }

  return response.json()
}

export async function setOrchestratorBaseline(
  apiBase: string,
  scope: 'internal' | 'external',
  datasetName: string,
  datasetRows: Record<string, any>[]
): Promise<any> {
  const response = await fetch(`${apiBase}/featureops/drift/orchestrator/baselines/${scope}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset_name: datasetName,
      dataset_rows: datasetRows,
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to set ${scope} orchestrator baseline: ${response.statusText}`)
  }

  return response.json()
}
