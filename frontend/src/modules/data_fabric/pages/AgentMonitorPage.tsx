import { useEffect, useMemo, useState } from 'react'

type Props = {
  loading: boolean
  overview: any
  lineage: any
  agentStatus?: any
  agentBusy?: boolean
  runAgentNow?: () => Promise<void>
  safeDate: (value?: string) => string
}

type AgentStatusResponse = {
  agent_active: boolean
  last_run?: {
    source?: string
    saved_at?: string
    report?: Record<string, unknown>
  } | null
  coverage?: {
    ensemble?: number
    static?: number
    behavioral_updates?: number
    total_relationships?: number
  }
  drift_changes?: Array<{
    relationship_key: string
    left_dataset: string
    right_dataset: string
    left_column: string
    right_column: string
    before_confidence: number
    after_confidence: number
    delta: number
  }>
  merge_suggestions?: Array<{
    left_dataset: string
    right_dataset: string
    best_confidence: number
    best_decision: string
    relationship_key: string
    reason?: string
  }>
  generated_at?: string
}

const API_BASE =
  (typeof import.meta !== 'undefined' && (import.meta.env.VITE_API_URL as string)) ||
  'http://127.0.0.1:8002/api'

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${path} failed (${response.status})${text ? `: ${text}` : ''}`)
  }
  return (await response.json()) as T
}

function inferConfidenceSource(row: any): 'ensemble' | 'ml_single' | 'static' {
  const backendSource = String(row?.confidence_source || row?.feature_vector?.confidence_source || '').trim()
  if (backendSource === 'ensemble' || backendSource === 'ml_single' || backendSource === 'static') {
    return backendSource
  }
  const featureVector = row?.feature_vector || {}
  const modelsUsed = featureVector?.models_used || {}
  const hasLr = typeof modelsUsed?.LR === 'number'
  const hasSecondary = Object.entries(modelsUsed).some(
    ([key, value]) => key !== 'LR' && typeof value === 'number'
  )
  if (hasLr && hasSecondary) return 'ensemble'
  if (hasLr || hasSecondary) return 'ml_single'
  return 'static'
}

function downloadBlob(fileName: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export default function AgentMonitorPage({
  loading,
  overview,
  lineage,
  safeDate,
}: Props) {
  const [agentStatus, setAgentStatus] = useState<AgentStatusResponse | null>(null)
  const [agentBusy, setAgentBusy] = useState(false)

  async function fetchAgentStatus() {
    try {
      const data = await fetchJson<AgentStatusResponse>('/data-fabric/agent/status')
      setAgentStatus(data)
    } catch {
      // Keep fallback summary rendering from overview/lineage even if status API fails.
    }
  }

  async function runAgentNow() {
    setAgentBusy(true)
    try {
      await fetchJson('/data-fabric/agent/run-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'manual' }),
      })
      await fetchAgentStatus()
    } finally {
      setAgentBusy(false)
    }
  }

  useEffect(() => {
    void fetchAgentStatus()
  }, [overview?.last_refreshed])

  if (!overview) {
    return (
      <section className="df-tab-content">
        <article className="glass-card df-state-card">
          <h3>{loading ? 'Loading Agent Monitor...' : 'No Agent Data Loaded Yet'}</h3>
          <p className="muted-text">
            {loading
              ? 'Fetching behavior, drift, and confidence recommendation signals...'
              : 'Use "Refresh Live Data" to populate the agent monitor.'}
          </p>
        </article>
      </section>
    )
  }

  const relationshipRows = overview?.relationships || []
  const agentSummary = useMemo(() => {
    const behavioralTimestamps = relationshipRows
      .map((row: any) => row?.feature_vector?.behavioral_updated_at)
      .filter((ts: any) => typeof ts === 'string' && ts.trim().length > 0)

    const lastBehavioralUpdate = behavioralTimestamps.length
      ? behavioralTimestamps.sort((a: string, b: string) => (a > b ? -1 : 1))[0]
      : undefined

    const ensembleRows = relationshipRows.filter((row: any) => inferConfidenceSource(row) === 'ensemble').length
    const staticRows = relationshipRows.length - ensembleRows
    const ensembleConf = relationshipRows
      .filter((row: any) => inferConfidenceSource(row) === 'ensemble')
      .map((row: any) => Number(row?.confidence || 0))
      .filter((value: number) => Number.isFinite(value))
    const staticConf = relationshipRows
      .filter((row: any) => inferConfidenceSource(row) === 'static')
      .map((row: any) => Number(row?.confidence || 0))
      .filter((value: number) => Number.isFinite(value))

    const avgEnsembleConfidence =
      ensembleConf.length > 0 ? ensembleConf.reduce((sum: number, v: number) => sum + v, 0) / ensembleConf.length : null
    const avgStaticConfidence =
      staticConf.length > 0 ? staticConf.reduce((sum: number, v: number) => sum + v, 0) / staticConf.length : null

    let higherAvgSource: 'ensemble' | 'static' | 'equal' | 'n/a' = 'n/a'
    if (avgEnsembleConfidence !== null && avgStaticConfidence !== null) {
      if (Math.abs(avgEnsembleConfidence - avgStaticConfidence) < 1e-9) higherAvgSource = 'equal'
      else higherAvgSource = avgEnsembleConfidence > avgStaticConfidence ? 'ensemble' : 'static'
    } else if (avgEnsembleConfidence !== null) {
      higherAvgSource = 'ensemble'
    } else if (avgStaticConfidence !== null) {
      higherAvgSource = 'static'
    }

    const topDrift = [...relationshipRows]
      .filter((row: any) => Number(row?.drift_score || 0) > 0)
      .sort((a: any, b: any) => Number(b?.drift_score || 0) - Number(a?.drift_score || 0))
      .slice(0, 8)

    const mergeCandidates = (lineage?.merge_candidates || []).slice(0, 8)

    return {
      active: behavioralTimestamps.length > 0,
      lastBehavioralUpdate,
      ensembleRows,
      staticRows,
      avgEnsembleConfidence,
      avgStaticConfidence,
      higherAvgSource,
      topDrift,
      mergeCandidates,
    }
  }, [relationshipRows, lineage])

  const statusSummary = useMemo(() => {
    const driftChanges = (agentStatus?.drift_changes || []).slice(0, 5)
    const mergeSuggestions = (agentStatus?.merge_suggestions || []).slice(0, 5)
    const coverage = agentStatus?.coverage || {}
    return {
      lastRunAt: agentStatus?.last_run?.saved_at,
      lastRunSource: String(agentStatus?.last_run?.source || 'N/A'),
      driftChanges,
      mergeSuggestions,
      coverage,
      report: agentStatus?.last_run?.report || null,
      generatedAt: agentStatus?.generated_at,
    }
  }, [agentStatus])

  function downloadAuditJson() {
    const payload = {
      exported_at: new Date().toISOString(),
      status: statusSummary,
      fallback_summary: agentSummary,
    }
    downloadBlob(
      `agent_audit_report_${Date.now()}.json`,
      JSON.stringify(payload, null, 2),
      'application/json;charset=utf-8'
    )
  }

  function downloadAuditTxt() {
    const lines: string[] = []
    lines.push('Agent Audit Report')
    lines.push(`Generated: ${new Date().toLocaleString()}`)
    lines.push(`Last Agent Run: ${safeDate(statusSummary.lastRunAt)}`)
    lines.push(`Run Source: ${statusSummary.lastRunSource}`)
    lines.push('')
    lines.push('Coverage:')
    lines.push(`- Ensemble: ${Number(statusSummary.coverage?.ensemble || agentSummary.ensembleRows)}`)
    lines.push(`- Static: ${Number(statusSummary.coverage?.static || agentSummary.staticRows)}`)
    lines.push(`- Behavioral Updates: ${Number(statusSummary.coverage?.behavioral_updates || 0)}`)
    lines.push('')
    lines.push('Top 5 Drifted Relationships (Before -> After):')
    if (statusSummary.driftChanges.length) {
      statusSummary.driftChanges.forEach((row: any, idx: number) => {
        lines.push(
          `${idx + 1}. ${row.left_dataset}.${row.left_column} -> ${row.right_dataset}.${row.right_column} | ${Number(
            row.before_confidence || 0
          ).toFixed(3)} -> ${Number(row.after_confidence || 0).toFixed(3)} (delta ${Number(row.delta || 0).toFixed(3)})`
        )
      })
    } else {
      lines.push('No drift deltas available yet.')
    }
    lines.push('')
    lines.push('Merge Suggestions:')
    if (statusSummary.mergeSuggestions.length) {
      statusSummary.mergeSuggestions.forEach((item: any, idx: number) => {
        lines.push(
          `${idx + 1}. ${item.left_dataset} <-> ${item.right_dataset} | confidence ${Number(
            item.best_confidence || 0
          ).toFixed(3)} (${item.best_decision})`
        )
        lines.push(`   Why: ${item.reason || 'No feature explanation available'}`)
      })
    } else {
      lines.push('No merge suggestions available.')
    }

    downloadBlob(`agent_audit_report_${Date.now()}.txt`, lines.join('\n'), 'text/plain;charset=utf-8')
  }

  return (
    <section className="df-tab-content">
      <article className="glass-card agent-monitor-card">
        <h3>Agent Monitor</h3>
        <p className="muted-text">
          Live transparency view of behavioral updates, drift detection, and model-confidence merge recommendations.
        </p>

        <div className="agent-actions-row">
          <button type="button" className="df-btn" onClick={() => void runAgentNow()} disabled={agentBusy || loading}>
            {agentBusy ? 'Running Agent...' : 'Run Agent Now'}
          </button>
          <button type="button" className="df-btn secondary" onClick={downloadAuditJson}>
            Download Audit JSON
          </button>
          <button type="button" className="df-btn secondary" onClick={downloadAuditTxt}>
            Download Audit TXT
          </button>
        </div>

        <div className="agent-monitor-grid">
          <div className="agent-metric-chip">
            <span>Status</span>
            <strong>{agentStatus?.agent_active || agentSummary.active ? 'Active' : 'No behavioral updates yet'}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Last Behavioral Update</span>
            <strong>{safeDate(agentSummary.lastBehavioralUpdate)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Scoring Source Coverage</span>
            <strong>
              Ensemble {Number(statusSummary.coverage?.static || agentSummary.staticRows)} | Static{' '}
              {Number(statusSummary.coverage?.ensemble || agentSummary.ensembleRows)}
            </strong>
          </div>
          <div className="agent-metric-chip">
            <span>Last Agent Run</span>
            <strong>{safeDate(statusSummary.lastRunAt)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Run Source</span>
            <strong>{statusSummary.lastRunSource}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Status Snapshot Generated</span>
            <strong>{safeDate(statusSummary.generatedAt)}</strong>
          </div>
        </div>

        <div className="agent-insight-grid">
          <div className="agent-insight-block">
            <h4>Top 5 Drifted (Before -&gt; After)</h4>
            {statusSummary.driftChanges.length ? (
              <ul className="agent-insight-list">
                {statusSummary.driftChanges.map((row: any) => (
                  <li key={row.relationship_key}>
                    <span>
                      {row.left_dataset}.{row.left_column} {'->'} {row.right_dataset}.{row.right_column}
                    </span>
                    <strong>
                      {Number(row.before_confidence || 0).toFixed(3)} {'->'} {Number(row.after_confidence || 0).toFixed(3)}
                    </strong>
                  </li>
                ))}
              </ul>
            ) : agentSummary.topDrift.length ? (
              <ul className="agent-insight-list">
                {agentSummary.topDrift.map((row: any) => (
                  <li key={row.relationship_key}>
                    <span>{row.left_dataset} {'->'} {row.right_dataset} ({row.left_column} {'->'} {row.right_column})</span>
                    <strong>drift {Number(row.drift_score || 0).toFixed(3)}</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-text">No drift risks detected in current metadata.</p>
            )}
          </div>

          <div className="agent-insight-block">
            <h4>Merge Suggestions (Why?)</h4>
            {statusSummary.mergeSuggestions.length ? (
              <ul className="agent-insight-list">
                {statusSummary.mergeSuggestions.map((candidate: any) => (
                  <li key={candidate.relationship_key}>
                    <span>
                      {candidate.left_dataset} {'↔'} {candidate.right_dataset}
                      <button
                        type="button"
                        className="why-merge-btn"
                        title={candidate.reason || 'No signal explanation available'}
                        aria-label={`Why merge ${candidate.left_dataset} and ${candidate.right_dataset}`}
                      >
                        Why?
                      </button>
                    </span>
                    <strong>{Number(candidate.best_confidence || 0).toFixed(3)} ({candidate.best_decision})</strong>
                  </li>
                ))}
              </ul>
            ) : agentSummary.mergeCandidates.length ? (
              <ul className="agent-insight-list">
                {agentSummary.mergeCandidates.map((candidate: any) => (
                  <li key={candidate.relationship_key}>
                    <span>{candidate.left_dataset} {'↔'} {candidate.right_dataset}</span>
                    <strong>{Number(candidate.best_confidence || 0).toFixed(3)} ({candidate.best_decision})</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-text">No confidence-based merge suggestions available.</p>
            )}
          </div>
        </div>

      </article>
    </section>
  )
}
