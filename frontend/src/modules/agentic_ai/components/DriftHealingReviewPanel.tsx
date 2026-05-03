import React, { useCallback, useEffect, useMemo, useState } from 'react'

const DECISIONS_KEY = 'stylesense_featureops_healing_decisions_v1'
const MANUAL_QUEUE_KEY = 'stylesense_validations_manual_queue_v1'

type ManualQueueEntry = {
  id: string
  column: string
  datasetName: string
  explanation: string
  recommendedAction: string
  createdAt: string
}

function loadManualQueue(): ManualQueueEntry[] {
  try {
    const raw = localStorage.getItem(MANUAL_QUEUE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ManualQueueEntry[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveManualQueue(entries: ManualQueueEntry[]) {
  localStorage.setItem(MANUAL_QUEUE_KEY, JSON.stringify(entries))
}

function shortText(text: string, max = 96): string {
  const t = String(text || '').replace(/\s+/g, ' ').trim()
  if (t.length <= max) return t
  return `${t.slice(0, max - 1)}…`
}

function newManualId() {
  return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 9)}`
}

/** Documented transforms aligned with backend `self_healing_service` (safe, bounded). */
const SAFE_HEALING_REFERENCE: Array<{ title: string; explanation: string; examples: string }> = [
  {
    title: 'Known column renames',
    explanation:
      'Renames only fire when the target column is missing, so meaning is preserved. These are treated as schema alignment, not semantic relabeling.',
    examples: 'sales_amt → sales_amount; qty → quantity',
  },
  {
    title: 'Numeric coercion for known measures',
    explanation:
      'Selected financial and count columns are coerced to numeric types where parsing is unambiguous. Invalid values become NaN and surface in profiling rather than silent swaps.',
    examples: 'sales_amount, discount_amount, quantity',
  },
  {
    title: 'Date standardisation',
    explanation:
      'Columns whose names contain “date” are normalised to ISO YYYY-MM-DD when a single unambiguous parse exists.',
    examples: 'order_date, ship_date',
  },
  {
    title: 'Optional missing columns',
    explanation:
      'Baseline-expected optional columns (for example discount_amount) may be added as empty when absent, so downstream schemas stay aligned.',
    examples: 'discount_amount added as null',
  },
]

type DriftSeverity = string

type DecisionStatus = 'pending' | 'validated' | 'rejected' | 'instruction'

type StoredDecision = {
  status: DecisionStatus
  instruction?: string
  at: string
}

type MergedHealingRow = {
  proposalId: string
  runId: string
  datasetName: string
  uploadedAt: string
  column: string
  releaseStatus?: string
  maxSeverity: DriftSeverity
  tier: 'safe_from_run' | 'validation_required'
  explanation: string
  recommendedAction: string
  sources: string[]
  /** Added from “manual queue” form; persisted in localStorage. */
  isManual?: boolean
}

function manualEntryToRow(m: ManualQueueEntry): MergedHealingRow {
  return {
    proposalId: `manual::${m.id}`,
    runId: '—',
    datasetName: m.datasetName,
    uploadedAt: m.createdAt,
    column: m.column,
    releaseStatus: 'MANUAL',
    maxSeverity: 'REVIEW',
    tier: 'validation_required',
    explanation: m.explanation,
    recommendedAction: m.recommendedAction,
    sources: ['manual entry'],
    isManual: true,
  }
}

function sevRank(s: string | undefined | null): number {
  const u = String(s || 'NONE').toUpperCase()
  if (u === 'HIGH') return 4
  if (u === 'MODERATE') return 3
  if (u === 'REVIEW') return 3
  if (u === 'LOW') return 2
  return 1
}

function maxSeverity(a?: string | null, b?: string | null): string {
  return sevRank(a) >= sevRank(b) ? String(a || 'NONE').toUpperCase() : String(b || 'NONE').toUpperCase()
}

function loadDecisions(): Record<string, StoredDecision> {
  try {
    const raw = localStorage.getItem(DECISIONS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, StoredDecision>
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function saveDecisions(next: Record<string, StoredDecision>) {
  localStorage.setItem(DECISIONS_KEY, JSON.stringify(next))
}

type DriftResultRow = {
  column_name?: string
  drift_severity?: string
  explanation?: string
  recommended_action?: string
}

type ReleaseGateRow = {
  column_name?: string
  release_status?: string
  explanation?: string
  recommended_action?: string
  internal_drift_severity?: string
  external_drift_severity?: string
  statistical_drift_severity?: string
  behavioral_drift_severity?: string
}

type DriftRunApi = {
  run_id?: string
  dataset_name?: string
  created_at?: string
  internal_drift_results?: DriftResultRow[]
  external_drift_results?: DriftResultRow[]
  release_results?: ReleaseGateRow[]
}

function buildMergedRows(runs: DriftRunApi[]): MergedHealingRow[] {
  const rows: MergedHealingRow[] = []
  for (const run of runs) {
    const runId = String(run.run_id || '')
    if (!runId) continue
    const datasetName = String(run.dataset_name || '—')
    const uploadedAt = String(run.created_at || '')
    const internal = Array.isArray(run.internal_drift_results) ? run.internal_drift_results : []
    const external = Array.isArray(run.external_drift_results) ? run.external_drift_results : []
    const release = Array.isArray(run.release_results) ? run.release_results : []

    const colMap = new Map<
      string,
      {
        maxSeverity: string
        explanations: string[]
        actions: string[]
        sources: Set<string>
        releaseStatus?: string
      }
    >()

    const bump = (col: string, sev: string | undefined, expl: string, act: string, src: string) => {
      const key = String(col || '').trim() || '—'
      if (!colMap.has(key)) {
        colMap.set(key, {
          maxSeverity: 'NONE',
          explanations: [],
          actions: [],
          sources: new Set(),
        })
      }
      const m = colMap.get(key)!
      m.maxSeverity = maxSeverity(m.maxSeverity, sev)
      if (expl && !m.explanations.includes(expl)) m.explanations.push(expl)
      if (act && !m.actions.includes(act)) m.actions.push(act)
      m.sources.add(src)
    }

    for (const r of internal) {
      bump(
        String(r.column_name ?? ''),
        r.drift_severity,
        String(r.explanation || '').trim(),
        String(r.recommended_action || '').trim(),
        'internal drift',
      )
    }
    for (const r of external) {
      bump(
        String(r.column_name ?? ''),
        r.drift_severity,
        String(r.explanation || '').trim(),
        String(r.recommended_action || '').trim(),
        'external drift',
      )
    }
    for (const r of release) {
      const col = String(r.column_name || '').trim() || '—'
      const m = colMap.get(col) || {
        maxSeverity: 'NONE',
        explanations: [],
        actions: [],
        sources: new Set<string>(),
      }
      if (!colMap.has(col)) colMap.set(col, m)
      m.releaseStatus = String(r.release_status || '')
      bump(
        col,
        maxSeverity(r.internal_drift_severity, maxSeverity(r.external_drift_severity, maxSeverity(r.statistical_drift_severity, r.behavioral_drift_severity))),
        String(r.explanation || '').trim(),
        String(r.recommended_action || '').trim(),
        'release gate',
      )
    }

    for (const [column, meta] of colMap) {
      const rs = meta.releaseStatus
      const ms = meta.maxSeverity
      /** Require an explicit READY from the release gate — do not infer “safe” from drift rows alone. */
      const tier: MergedHealingRow['tier'] =
        rs === 'READY' && sevRank(ms) <= sevRank('LOW') ? 'safe_from_run' : 'validation_required'

      const explanation = meta.explanations.filter(Boolean).join(' \n') || '—'
      const recommendedAction = meta.actions.filter(Boolean).join(' \n') || 'Review column mapping, baseline version, and semantic meaning before production.'
      const proposalId = `${runId}::${encodeURIComponent(column)}::merged`
      rows.push({
        proposalId,
        runId,
        datasetName,
        uploadedAt,
        column,
        releaseStatus: meta.releaseStatus,
        maxSeverity: ms,
        tier,
        explanation,
        recommendedAction,
        sources: [...meta.sources],
      })
    }
  }
  return rows.sort((a, b) => String(b.uploadedAt).localeCompare(String(a.uploadedAt)))
}

export default function DriftHealingReviewPanel() {
  const apiBase = import.meta.env.VITE_API_URL || import.meta.env.VITE_AGENTIC_API_URL || '/api'
  const [runs, setRuns] = useState<DriftRunApi[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [decisions, setDecisions] = useState<Record<string, StoredDecision>>(() => loadDecisions())
  const [instructionDrafts, setInstructionDrafts] = useState<Record<string, string>>({})
  const [manualQueue, setManualQueue] = useState<ManualQueueEntry[]>(() => loadManualQueue())
  const [manualForm, setManualForm] = useState({
    column: '',
    datasetName: '',
    explanation: '',
    recommendedAction: '',
  })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/featureops/drift-runs`)
      const json = await res.json()
      if (json.status === 'ok' && Array.isArray(json.runs)) setRuns(json.runs as DriftRunApi[])
      else setRuns([])
    } catch {
      setError('Could not load drift runs for healing review.')
      setRuns([])
    } finally {
      setLoading(false)
    }
  }, [apiBase])

  useEffect(() => {
    void load()
  }, [load])

  const merged = useMemo(() => buildMergedRows(runs), [runs])
  const safeFromRuns = useMemo(() => merged.filter((r) => r.tier === 'safe_from_run'), [merged])
  const needsValidation = useMemo(() => merged.filter((r) => r.tier === 'validation_required'), [merged])
  const manualRowsMerged = useMemo(() => manualQueue.map(manualEntryToRow), [manualQueue])
  const fullValidationQueue = useMemo(
    () => [...manualRowsMerged, ...needsValidation].sort((a, b) => String(b.uploadedAt).localeCompare(String(a.uploadedAt))),
    [manualRowsMerged, needsValidation],
  )

  const validationKpis = useMemo(() => {
    let pending = 0
    let validated = 0
    let rejected = 0
    let instruction = 0
    for (const row of fullValidationQueue) {
      const st = decisions[row.proposalId]?.status
      if (!st || st === 'pending') pending += 1
      else if (st === 'validated') validated += 1
      else if (st === 'rejected') rejected += 1
      else if (st === 'instruction') instruction += 1
    }
    return {
      pending,
      validated,
      rejected,
      instruction,
      autoHealEligible: safeFromRuns.length,
      unsafeGated: fullValidationQueue.length,
      distinctGatedColumns: new Set(fullValidationQueue.map((r) => r.column)).size,
    }
  }, [fullValidationQueue, safeFromRuns, decisions])

  type ColumnStat = {
    column: string
    autoHeal: number
    gated: number
    pending: number
    validated: number
    rejected: number
    instruction: number
  }

  const columnValidationStats = useMemo(() => {
    const map = new Map<string, ColumnStat>()
    const touch = (col: string): ColumnStat => {
      const k = col || '—'
      if (!map.has(k)) {
        map.set(k, { column: k, autoHeal: 0, gated: 0, pending: 0, validated: 0, rejected: 0, instruction: 0 })
      }
      return map.get(k)!
    }
    for (const row of safeFromRuns) {
      touch(row.column).autoHeal += 1
    }
    for (const row of fullValidationQueue) {
      const e = touch(row.column)
      e.gated += 1
      const st = decisions[row.proposalId]?.status
      if (!st || st === 'pending') e.pending += 1
      else if (st === 'validated') e.validated += 1
      else if (st === 'rejected') e.rejected += 1
      else if (st === 'instruction') e.instruction += 1
    }
    return [...map.values()].sort((a, b) => b.gated + b.autoHeal - (a.gated + a.autoHeal))
  }, [safeFromRuns, fullValidationQueue, decisions])

  function setDecision(proposalId: string, status: DecisionStatus, instruction?: string) {
    const next = {
      ...decisions,
      [proposalId]: {
        status,
        instruction: instruction?.trim() || undefined,
        at: new Date().toISOString(),
      },
    }
    setDecisions(next)
    saveDecisions(next)
    if (status !== 'instruction') {
      setInstructionDrafts((d) => {
        const copy = { ...d }
        delete copy[proposalId]
        return copy
      })
    }
  }

  function addManualToQueue() {
    const col = manualForm.column.trim()
    if (!col) return
    const entry: ManualQueueEntry = {
      id: newManualId(),
      column: col,
      datasetName: manualForm.datasetName.trim() || '—',
      explanation: manualForm.explanation.trim() || '—',
      recommendedAction: manualForm.recommendedAction.trim() || '—',
      createdAt: new Date().toISOString(),
    }
    setManualQueue((prev) => {
      const next = [entry, ...prev]
      saveManualQueue(next)
      return next
    })
    setManualForm({ column: '', datasetName: '', explanation: '', recommendedAction: '' })
  }

  function removeManualFromQueue(manualId: string) {
    setManualQueue((prev) => {
      const next = prev.filter((x) => x.id !== manualId)
      saveManualQueue(next)
      return next
    })
    const pid = `manual::${manualId}`
    setDecisions((d) => {
      const copy = { ...d }
      delete copy[pid]
      saveDecisions(copy)
      return copy
    })
    setInstructionDrafts((d) => {
      const copy = { ...d }
      delete copy[pid]
      return copy
    })
  }

  function riskBadgeStyle(severity: string): { bg: string; color: string; border: string; label: string } {
    const u = String(severity || 'NONE').toUpperCase()
    if (u === 'HIGH') return { bg: '#fee2e2', color: '#991b1b', border: '#fecaca', label: 'High' }
    if (u === 'MODERATE') return { bg: '#ffedd5', color: '#9a3412', border: '#fed7aa', label: 'Moderate' }
    if (u === 'REVIEW') return { bg: '#fef3c7', color: '#92400e', border: '#fde68a', label: 'Review' }
    if (u === 'LOW') return { bg: '#dcfce7', color: '#166534', border: '#bbf7d0', label: 'Low' }
    return { bg: '#f1f5f9', color: '#475569', border: '#e2e8f0', label: u === 'NONE' ? 'None' : u }
  }

  function reviewStatusLabel(proposalId: string): string {
    const st = decisions[proposalId]?.status
    if (!st || st === 'pending') return 'Pending'
    if (st === 'validated') return 'Validated'
    if (st === 'rejected') return 'Rejected'
    return 'Has note'
  }

  return (
    <section style={{ width: '100%', maxWidth: 'none', boxSizing: 'border-box', background: '#fdf2f8', borderRadius: 12, border: '1px solid #fbcfe8', padding: '12px 0', color: '#0f172a' }}>
      <div style={{ width: '100%', display: 'grid', gap: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em' }}>Validations</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4, maxWidth: 820, lineHeight: 1.5 }}>
              Column-wise drift healing review: safe reference transforms, auto-eligible (READY + low drift) items, and an approval-style queue table for
              gated rows. Decisions and validation notes use{' '}
              <code style={{ fontSize: 11 }}>{DECISIONS_KEY}</code>; manually added queue lines use{' '}
              <code style={{ fontSize: 11 }}>{MANUAL_QUEUE_KEY}</code> (this browser only).
            </div>
          </div>
          <button type="button" className="df-btn secondary" onClick={() => void load()} disabled={loading}>
            {loading ? 'Loading…' : 'Reload runs'}
          </button>
        </div>

        {error ? (
          <div style={{ borderRadius: 8, border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', padding: 10, fontSize: 12 }}>{error}</div>
        ) : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
          {[
            ['Pending validations', String(validationKpis.pending), 'Gated column-events with no decision yet.'],
            ['Validations done', String(validationKpis.validated), 'Local “Validate” confirmations recorded.'],
            ['Rejected', String(validationKpis.rejected), 'Local “Reject” outcomes.'],
            ['Human instructions', String(validationKpis.instruction), 'Reviewer notes saved on gated items.'],
            ['Auto-heal eligible', String(validationKpis.autoHealEligible), 'READY + max drift LOW/NONE (per upload column).'],
            ['Unsafe / gated', String(validationKpis.unsafeGated), 'Needs human gate before treating as safe.'],
            ['Distinct gated columns', String(validationKpis.distinctGatedColumns), 'Unique column names in the gated queue.'],
          ].map(([label, value, hint]) => (
            <div key={String(label)} style={{ borderRadius: 10, border: '1px solid #fbcfe8', background: '#ffffff', padding: 10, display: 'grid', gap: 4 }}>
              <div style={{ fontSize: 10, color: '#9d174d', fontWeight: 700 }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#831843' }}>{value}</div>
              <div style={{ fontSize: 10, color: '#94a3b8', lineHeight: 1.35 }}>{hint}</div>
            </div>
          ))}
        </div>

        <div>
          <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a', marginBottom: 8 }}>Column validation summary</div>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>Aggregated per column across all drift runs (upload events). Gated counts drive the review queue below.</div>
          <div style={{ overflowX: 'auto', borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, minWidth: 640 }}>
              <thead>
                <tr style={{ background: '#fdf2f8' }}>
                  {['Column', 'Auto-heal eligible', 'Gated (unsafe)', 'Pending', 'Validated', 'Rejected', 'Instructions'].map((h) => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 6px', borderBottom: '1px solid #fbcfe8', color: '#9f1239', fontWeight: 800 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!columnValidationStats.length ? (
                  <tr>
                    <td colSpan={7} style={{ padding: 12, color: '#64748b' }}>No drift-run columns yet.</td>
                  </tr>
                ) : (
                  columnValidationStats.map((row) => (
                    <tr key={row.column}>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 800, color: '#0f172a' }}>{row.column}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#166534', fontWeight: 700 }}>{row.autoHeal}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#9f1239', fontWeight: 700 }}>{row.gated}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.pending}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.validated}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.rejected}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.instruction}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ fontSize: 14, fontWeight: 800, color: '#831843', marginBottom: 8 }}>Safe healing (reference)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
            {SAFE_HEALING_REFERENCE.map((item) => (
              <div key={item.title} style={{ borderRadius: 10, border: '1px solid #bbf7d0', background: '#f0fdf4', padding: 10, display: 'grid', gap: 6 }}>
                <div style={{ fontSize: 12, fontWeight: 800, color: '#14532d' }}>{item.title}</div>
                <div style={{ fontSize: 10.5, color: '#166534', lineHeight: 1.45 }}>{item.explanation}</div>
                <div style={{ fontSize: 10, color: '#15803d', fontWeight: 700 }}>Examples: {item.examples}</div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a', marginBottom: 8 }}>Safe guidance from drift runs ({safeFromRuns.length})</div>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>
            Rows where the release gate is <strong>READY</strong> and combined drift severity is <strong>NONE or LOW</strong> only. Anything without a READY gate stays under validation — read explanations before production promotion.
          </div>
          {!safeFromRuns.length ? (
            <div style={{ borderRadius: 8, border: '1px dashed #cbd5e1', background: '#f8fafc', padding: 12, fontSize: 12, color: '#475569' }}>
              No qualifying columns yet. Upload and run the DE Workflow to populate drift runs.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {safeFromRuns.slice(0, 40).map((row) => (
                <div key={row.proposalId} style={{ borderRadius: 10, border: '1px solid #bbf7d0', background: '#ffffff', padding: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 800, color: '#14532d' }}>
                    {row.column} <span style={{ color: '#64748b', fontWeight: 600 }}>· {row.datasetName}</span>
                  </div>
                  <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                    {row.uploadedAt ? new Date(row.uploadedAt).toLocaleString('en-GB') : '—'} · {row.sources.join(', ')} · severity {row.maxSeverity}
                  </div>
                  <div style={{ fontSize: 11, color: '#334155', marginTop: 6, lineHeight: 1.45 }}>{row.explanation}</div>
                  <div style={{ fontSize: 11, color: '#166534', marginTop: 4, lineHeight: 1.45 }}>
                    <strong>Healing / follow-up:</strong> {row.recommendedAction}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 800, color: '#9f1239' }}>Validation approval queue</div>
              <div style={{ fontSize: 11, color: '#881337', marginTop: 4, maxWidth: 900, lineHeight: 1.45 }}>
                Data-architecture style table: one row per gated column-event (drift runs + manual entries). Short text columns keep the grid readable;
                hover or use your browser tooltip on truncated cells. Validate / Reject / Save note persist locally.
              </div>
            </div>
            <span
              style={{
                borderRadius: 999,
                padding: '6px 12px',
                fontSize: 11,
                fontWeight: 800,
                background: '#fef3c7',
                color: '#92400e',
                border: '1px solid #fcd34d',
              }}
            >
              {fullValidationQueue.length} awaiting / tracked
            </span>
          </div>

          {fullValidationQueue.length > 0 ? (
            <div
              style={{
                borderRadius: 12,
                border: '1px solid #e2e8f0',
                background: '#ffffff',
                boxShadow: '0 1px 3px rgba(15,23,42,0.06)',
                overflow: 'hidden',
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  padding: '10px 12px',
                  background: 'linear-gradient(90deg, #fff7ed 0%, #fff1f2 100%)',
                  borderBottom: '1px solid #fecdd3',
                  fontSize: 11,
                  color: '#9f1239',
                }}
              >
                <span style={{ fontSize: 14, lineHeight: 1 }}>⚠️</span>
                <div>
                  <strong>Action required:</strong> {validationKpis.pending} pending · {validationKpis.validated} validated · {validationKpis.rejected}{' '}
                  rejected · {validationKpis.instruction} with saved notes. Manual rows are mixed with drift-run rows; remove a manual row only if it was
                  added in error.
                </div>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, color: '#0f172a', minWidth: 980 }}>
                  <thead>
                    <tr style={{ background: '#fdf2f8', borderBottom: '1px solid #fbcfe8' }}>
                      {[
                        'Column',
                        'Dataset / run',
                        'When',
                        'Release',
                        'Risk',
                        'Explanation',
                        'Suggested healing',
                        'Review status',
                        'Saved validation note',
                        'Actions',
                      ].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: 'left',
                            padding: '10px 8px',
                            fontWeight: 800,
                            color: '#831843',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {fullValidationQueue.map((row) => {
                      const d = decisions[row.proposalId]
                      const draft = instructionDrafts[row.proposalId] ?? d?.instruction ?? ''
                      const rb = riskBadgeStyle(row.maxSeverity)
                      const manualId = row.isManual && row.proposalId.startsWith('manual::') ? row.proposalId.slice('manual::'.length) : null
                      return (
                        <tr key={row.proposalId} style={{ borderBottom: '1px solid #f1f5f9', verticalAlign: 'top' }}>
                          <td style={{ padding: '10px 8px', fontWeight: 800 }}>
                            <div>{row.column}</div>
                            {row.isManual ? (
                              <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600, marginTop: 2 }}>Manual queue</div>
                            ) : null}
                          </td>
                          <td style={{ padding: '10px 8px' }}>
                            <div style={{ fontWeight: 700, color: '#0f172a' }}>{row.datasetName}</div>
                            <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>run {row.runId}</div>
                          </td>
                          <td style={{ padding: '10px 8px', color: '#475569', whiteSpace: 'nowrap' }}>
                            {row.uploadedAt ? new Date(row.uploadedAt).toLocaleString('en-GB') : '—'}
                          </td>
                          <td style={{ padding: '10px 8px' }}>
                            <span style={{ fontWeight: 700 }}>{row.releaseStatus || '—'}</span>
                          </td>
                          <td style={{ padding: '10px 8px' }}>
                            <span
                              style={{
                                display: 'inline-block',
                                borderRadius: 999,
                                padding: '3px 10px',
                                fontSize: 10,
                                fontWeight: 800,
                                background: rb.bg,
                                color: rb.color,
                                border: `1px solid ${rb.border}`,
                              }}
                            >
                              {rb.label}
                            </span>
                          </td>
                          <td style={{ padding: '10px 8px', maxWidth: 200, color: '#334155', lineHeight: 1.35 }} title={row.explanation}>
                            {shortText(row.explanation, 100)}
                          </td>
                          <td style={{ padding: '10px 8px', maxWidth: 200, color: '#334155', lineHeight: 1.35 }} title={row.recommendedAction}>
                            {shortText(row.recommendedAction, 100)}
                          </td>
                          <td style={{ padding: '10px 8px', fontWeight: 700, color: '#0f172a' }}>{reviewStatusLabel(row.proposalId)}</td>
                          <td style={{ padding: '10px 8px', maxWidth: 180, color: '#475569', lineHeight: 1.35 }} title={d?.instruction || ''}>
                            {d?.instruction ? shortText(d.instruction, 80) : '—'}
                          </td>
                          <td style={{ padding: '10px 8px', minWidth: 200 }}>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
                              <button type="button" className="df-btn" style={{ fontSize: 10, padding: '4px 10px' }} onClick={() => setDecision(row.proposalId, 'validated')}>
                                Validate
                              </button>
                              <button type="button" className="df-btn secondary" style={{ fontSize: 10, padding: '4px 10px' }} onClick={() => setDecision(row.proposalId, 'rejected')}>
                                Reject
                              </button>
                              {manualId ? (
                                <button
                                  type="button"
                                  className="df-btn secondary"
                                  style={{ fontSize: 10, padding: '4px 10px', borderColor: '#fecaca', color: '#b91c1c' }}
                                  onClick={() => removeManualFromQueue(manualId)}
                                >
                                  Remove
                                </button>
                              ) : null}
                            </div>
                            <textarea
                              value={draft}
                              onChange={(e) => setInstructionDrafts((prev) => ({ ...prev, [row.proposalId]: e.target.value }))}
                              rows={2}
                              placeholder="Validation note (saved with Save note)…"
                              style={{
                                width: '100%',
                                maxWidth: 260,
                                borderRadius: 8,
                                border: '1px solid #e2e8f0',
                                padding: 6,
                                fontSize: 10,
                                fontFamily: 'inherit',
                                resize: 'vertical',
                                boxSizing: 'border-box',
                              }}
                            />
                            <button
                              type="button"
                              className="df-btn secondary"
                              style={{ fontSize: 10, padding: '4px 10px', marginTop: 6 }}
                              onClick={() => setDecision(row.proposalId, 'instruction', draft)}
                            >
                              Save note
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div style={{ borderRadius: 8, border: '1px dashed #fda4af', background: '#fff1f2', padding: 12, fontSize: 12, color: '#9f1239' }}>
              No gated items yet. Add a manual validation below, or run the DE Workflow so drift runs populate this queue.
            </div>
          )}

          <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a', marginBottom: 8 }}>Add manual validation (saved to browser)</div>
          <div style={{ fontSize: 10.5, color: '#64748b', marginBottom: 8 }}>
            Use when something must be tracked before it appears in drift runs (e.g. policy exception). Appears in the table above with source “Manual queue”.
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 10,
              padding: 12,
              borderRadius: 10,
              border: '1px solid #e2e8f0',
              background: '#f8fafc',
            }}
          >
            <label style={{ display: 'grid', gap: 4, fontSize: 11, fontWeight: 700, color: '#334155' }}>
              Column *
              <input
                value={manualForm.column}
                onChange={(e) => setManualForm((f) => ({ ...f, column: e.target.value }))}
                style={{ borderRadius: 8, border: '1px solid #cbd5e1', padding: '8px 10px', fontSize: 12 }}
                placeholder="e.g. sales_amount"
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 11, fontWeight: 700, color: '#334155' }}>
              Dataset / context
              <input
                value={manualForm.datasetName}
                onChange={(e) => setManualForm((f) => ({ ...f, datasetName: e.target.value }))}
                style={{ borderRadius: 8, border: '1px solid #cbd5e1', padding: '8px 10px', fontSize: 12 }}
                placeholder="e.g. Q4 upload"
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 11, fontWeight: 700, color: '#334155', gridColumn: '1 / -1' }}>
              Short explanation
              <textarea
                value={manualForm.explanation}
                onChange={(e) => setManualForm((f) => ({ ...f, explanation: e.target.value }))}
                rows={2}
                style={{ borderRadius: 8, border: '1px solid #cbd5e1', padding: 8, fontSize: 12, fontFamily: 'inherit', resize: 'vertical' }}
                placeholder="What drift or ambiguity was detected?"
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 11, fontWeight: 700, color: '#334155', gridColumn: '1 / -1' }}>
              Suggested healing
              <textarea
                value={manualForm.recommendedAction}
                onChange={(e) => setManualForm((f) => ({ ...f, recommendedAction: e.target.value }))}
                rows={2}
                style={{ borderRadius: 8, border: '1px solid #cbd5e1', padding: 8, fontSize: 12, fontFamily: 'inherit', resize: 'vertical' }}
                placeholder="What should reviewers or implementers do?"
              />
            </label>
            <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <button type="button" className="df-btn" onClick={addManualToQueue} disabled={!manualForm.column.trim()}>
                Add to queue and save
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
