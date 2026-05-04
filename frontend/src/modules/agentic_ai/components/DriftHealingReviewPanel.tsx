import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { getAgenticApiBase } from '../../../lib/agenticApiBase'

const DECISIONS_KEY = 'stylesense_featureops_healing_decisions_v1'

type HealingKpis = {
  drifted_columns?: number
  auto_healed?: number
  needs_review?: number
  quarantined?: number
  stable_columns?: number
  families_total?: number
  families_with_drift?: number
}

type AutoHealedRow = {
  family?: string
  source_file?: string
  dataset?: string
  column: string
  drift_type?: string
  drift_type_code?: string
  healing_applied?: string
  result?: string
  status?: string
  decision?: string
  numeric_evidence?: string | null
}

type NeedsReviewRow = {
  family?: string
  source_file?: string
  dataset?: string
  column: string
  drift_type?: string
  drift_type_code?: string
  suggested_healing?: string
  decision?: string
  reason?: string
  numeric_evidence?: string | null
}

type QuarantinedRow = {
  family?: string
  source_file?: string
  dataset?: string
  column: string
  drift_type?: string
  drift_type_code?: string
  reason?: string
  status?: string
  decision?: string
  numeric_evidence?: string | null
}

type HealingDashboardPayload = {
  run_id?: string
  kpis: HealingKpis
  auto_healed: AutoHealedRow[]
  needs_review: NeedsReviewRow[]
  quarantined: QuarantinedRow[]
}

type DecisionStatus = 'pending' | 'validated' | 'rejected' | 'instruction'

type StoredDecision = {
  status: DecisionStatus
  instruction?: string
  at: string
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

function proposalId(row: NeedsReviewRow) {
  const fam = row.family || '—'
  const src = row.source_file || row.dataset || '—'
  return `nr::${encodeURIComponent(fam)}::${encodeURIComponent(src)}::${encodeURIComponent(row.column)}`
}

function displaySource(row: { source_file?: string; dataset?: string }) {
  return row.source_file || row.dataset || '—'
}

export default function DriftHealingReviewPanel() {
  /** FeatureOps + healing-dashboard live on the agentic FastAPI app (default dev :8000), not Data Architecture :8003. */
  const apiBase = useMemo(() => getAgenticApiBase(), [])
  const [runScope, setRunScope] = useState<string>('all')
  const [runOptions, setRunOptions] = useState<Array<{ run_id: string; dataset_name: string; created_at?: string }>>([])
  const [dashboard, setDashboard] = useState<HealingDashboardPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [decisions, setDecisions] = useState<Record<string, StoredDecision>>(() => loadDecisions())

  const loadRunOptions = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/featureops/drift-runs`)
      const json = await res.json()
      if (json.status === 'ok' && Array.isArray(json.runs)) {
        const rows = (json.runs as Array<{ run_id?: string; dataset_name?: string; created_at?: string }>)
          .filter((r) => r.run_id)
          .map((r) => ({
            run_id: String(r.run_id),
            dataset_name: String(r.dataset_name || '—'),
            created_at: r.created_at ? String(r.created_at) : undefined,
          }))
        rows.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
        setRunOptions(rows)
      } else {
        setRunOptions([])
      }
    } catch {
      setRunOptions([])
    }
  }, [apiBase])

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const path = runScope === 'all' ? 'all' : encodeURIComponent(runScope)
      const res = await fetch(`${apiBase}/semantic-drift/runs/${path}/healing-dashboard`)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || res.statusText)
      }
      const json = (await res.json()) as HealingDashboardPayload & { status?: string }
      if (json.kpis && Array.isArray(json.auto_healed) && Array.isArray(json.needs_review) && Array.isArray(json.quarantined)) {
        setDashboard({
          run_id: json.run_id,
          kpis: json.kpis,
          auto_healed: json.auto_healed,
          needs_review: json.needs_review,
          quarantined: json.quarantined,
        })
      } else {
        setDashboard(null)
      }
    } catch (e) {
      setError(`Could not load healing dashboard (${String(e)}).`)
      setDashboard(null)
    } finally {
      setLoading(false)
    }
  }, [apiBase, runScope])

  useEffect(() => {
    void loadRunOptions()
  }, [loadRunOptions])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard])

  function setDecision(proposalId: string, status: DecisionStatus, instruction?: string) {
    const prev = decisions[proposalId]
    let nextInstruction = prev?.instruction
    if (status === 'instruction') {
      nextInstruction = instruction?.trim() || undefined
    } else if (instruction !== undefined) {
      nextInstruction = instruction?.trim() || undefined
    }
    const next = {
      ...decisions,
      [proposalId]: {
        status,
        instruction: nextInstruction,
        at: new Date().toISOString(),
      },
    }
    setDecisions(next)
    saveDecisions(next)
  }

  function reviewBadge(pid: string): string {
    const st = decisions[pid]?.status
    if (!st || st === 'pending') return 'Pending'
    if (st === 'validated') return 'Approved'
    if (st === 'rejected') return 'Rejected'
    if (st === 'instruction') return 'Mapping saved'
    return 'Pending'
  }

  function onEditMapping(pid: string) {
    const current = decisions[pid]?.instruction ?? ''
    const next = window.prompt('Edit category or conversion mapping (saved on this device)', current)
    if (next !== null && next.trim()) {
      setDecision(pid, 'instruction', next.trim())
    }
  }

  const kpis = dashboard?.kpis
  const famTotal = kpis?.families_total ?? 5
  const famDrift = kpis?.families_with_drift ?? 0

  return (
    <section
      style={{
        width: '100%',
        maxWidth: 'none',
        boxSizing: 'border-box',
        background: '#fdf2f8',
        borderRadius: 12,
        border: '1px solid #fbcfe8',
        padding: '12px 0',
        color: '#0f172a',
      }}
    >
      <div style={{ width: '100%', display: 'grid', gap: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em' }}>Validation</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 6, maxWidth: 880, lineHeight: 1.55 }}>
              Self-healing means the system fixes only safe drift automatically. If the drift is risky or meaning is lost, the system asks a human or quarantines
              it. Rows are grouped under the five architecture families when you upload against those baselines (product catalog, user profiles, sales
              transactions, shop directory, fashion trends). Only final outcomes appear here — not READY/NONE stable columns or row_count_guard noise.{' '}
              <strong>Stats (from drift run)</strong> is copied from the persisted internal drift job (segment means, scales, evidence lines). It is not a live
              re-fit; affine / embedding proposals from the separate semantic-drift ingest path are not merged into FeatureOps runs yet.
            </div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <label style={{ fontSize: 11, color: '#831843', fontWeight: 700, display: 'flex', gap: 6, alignItems: 'center' }}>
              Upload
              <select
                value={runScope}
                onChange={(e) => setRunScope(e.target.value)}
                style={{ borderRadius: 8, border: '1px solid #fbcfe8', padding: '6px 10px', fontSize: 12, background: '#fff' }}
              >
                <option value="all">All (merged)</option>
                {runOptions.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.dataset_name} · {r.run_id}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="df-btn secondary" onClick={() => void Promise.all([loadRunOptions(), loadDashboard()])} disabled={loading}>
              {loading ? 'Loading…' : 'Reload'}
            </button>
          </div>
        </div>

        {error ? (
          <div style={{ borderRadius: 8, border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', padding: 10, fontSize: 12 }}>{error}</div>
        ) : null}

        {!error && !loading && dashboard && (dashboard.kpis?.drifted_columns ?? 0) === 0 && runOptions.length === 0 ? (
          <div
            style={{
              borderRadius: 10,
              border: '1px solid #fde68a',
              background: '#fffbeb',
              color: '#92400e',
              padding: 12,
              fontSize: 12,
              lineHeight: 1.5,
            }}
          >
            <strong>No drift runs in the agentic registry.</strong> Validation reads from the same backend as the DE workflow (FeatureOps drift runs + semantic
            drift routes). Run the main agentic API on <strong>port 8000</strong> and set <code style={{ fontSize: 11 }}>VITE_AGENTIC_API_URL=http://127.0.0.1:8000/api</code> if your{' '}
            <code style={{ fontSize: 11 }}>VITE_API_URL</code> points at Data Architecture (8003). Then upload again so drift is persisted to{' '}
            <code style={{ fontSize: 11 }}>drift_runs.json</code>.
          </div>
        ) : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 10 }}>
          {[
            ['Drifted columns', String(kpis?.drifted_columns ?? '—')],
            ['Auto-healed', String(kpis?.auto_healed ?? 0)],
            ['Needs review', String(kpis?.needs_review ?? 0)],
            ['Quarantined', String(kpis?.quarantined ?? 0)],
            ['Stable columns', String(kpis?.stable_columns ?? 0)],
            ['Families w/ drift', `${famDrift} / ${famTotal}`],
          ].map(([label, value]) => (
            <div key={String(label)} style={{ borderRadius: 10, border: '1px solid #fbcfe8', background: '#ffffff', padding: 10, display: 'grid', gap: 4 }}>
              <div style={{ fontSize: 10, color: '#9d174d', fontWeight: 700 }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#831843' }}>{value}</div>
            </div>
          ))}
        </div>

        <div>
          <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 8, color: '#14532d' }}>1. Auto-healed</div>
          <div style={{ overflowX: 'auto', borderRadius: 10, border: '1px solid #bbf7d0', background: '#ffffff' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5, minWidth: 820 }}>
              <thead>
                <tr style={{ background: '#f0fdf4' }}>
                  {['Family', 'Upload', 'Column', 'Drift type', 'Healing applied', 'Result', 'Stats (from drift run)', 'Status'].map((h) => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 8px', borderBottom: '1px solid #bbf7d0', color: '#14532d', fontWeight: 800 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!dashboard?.auto_healed?.length ? (
                  <tr>
                    <td colSpan={8} style={{ padding: 12, color: '#64748b' }}>
                      No auto-healed columns for this scope. Upload each of the five demo families to see drifted columns here.
                    </td>
                  </tr>
                ) : (
                  dashboard.auto_healed.map((row) => (
                    <tr key={`${row.family}-${displaySource(row)}-${row.column}-${row.result}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '8px 8px', fontWeight: 800, color: '#14532d' }}>{row.family || '—'}</td>
                      <td style={{ padding: '8px 8px', fontWeight: 600, color: '#475569', fontSize: 11 }}>{displaySource(row)}</td>
                      <td style={{ padding: '8px 8px', fontWeight: 800 }}>{row.column}</td>
                      <td style={{ padding: '8px 8px', color: '#334155' }}>{row.drift_type}</td>
                      <td style={{ padding: '8px 8px', color: '#166534' }}>{row.healing_applied}</td>
                      <td style={{ padding: '8px 8px', color: '#0f172a' }}>{row.result}</td>
                      <td style={{ padding: '8px 8px', color: '#475569', fontSize: 10, lineHeight: 1.4, maxWidth: 280, whiteSpace: 'pre-wrap' }}>
                        {row.numeric_evidence || '—'}
                      </td>
                      <td style={{ padding: '8px 8px', fontWeight: 800, color: '#166534' }}>{row.status || 'AUTO_HEALED'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 8, color: '#92400e' }}>2. Needs human review</div>
          <div style={{ overflowX: 'auto', borderRadius: 10, border: '1px solid #fde68a', background: '#ffffff' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5, minWidth: 960 }}>
              <thead>
                <tr style={{ background: '#fffbeb' }}>
                  {['Family', 'Upload', 'Column', 'Drift type', 'Suggested healing', 'Stats (from drift run)', 'Action'].map((h) => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 8px', borderBottom: '1px solid #fde68a', color: '#92400e', fontWeight: 800 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!dashboard?.needs_review?.length ? (
                  <tr>
                    <td colSpan={7} style={{ padding: 12, color: '#64748b' }}>
                      Nothing needs human review for this scope.
                    </td>
                  </tr>
                ) : (
                  dashboard.needs_review.map((row) => {
                    const pid = proposalId(row)
                    return (
                      <tr key={pid} style={{ borderBottom: '1px solid #f1f5f9', verticalAlign: 'top' }}>
                        <td style={{ padding: '8px 8px', fontWeight: 800, color: '#92400e' }}>{row.family || '—'}</td>
                        <td style={{ padding: '8px 8px', fontWeight: 600, color: '#475569', fontSize: 11 }}>{displaySource(row)}</td>
                        <td style={{ padding: '8px 8px', fontWeight: 800 }}>{row.column}</td>
                        <td style={{ padding: '8px 8px', color: '#334155', maxWidth: 200 }}>{row.drift_type}</td>
                        <td style={{ padding: '8px 8px', color: '#334155', maxWidth: 280, lineHeight: 1.45 }}>
                          <div style={{ fontWeight: 700 }}>{row.suggested_healing}</div>
                          {row.reason ? <div style={{ fontSize: 10, color: '#64748b', marginTop: 4 }}>{row.reason}</div> : null}
                        </td>
                        <td style={{ padding: '8px 8px', color: '#475569', fontSize: 10, lineHeight: 1.4, maxWidth: 260, whiteSpace: 'pre-wrap' }}>
                          {row.numeric_evidence || '—'}
                        </td>
                        <td style={{ padding: '8px 8px', minWidth: 220 }}>
                          <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', marginBottom: 6 }}>{reviewBadge(pid)}</div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                            <button type="button" className="df-btn" style={{ fontSize: 10, padding: '4px 10px' }} onClick={() => setDecision(pid, 'validated')}>
                              Approve
                            </button>
                            <button type="button" className="df-btn secondary" style={{ fontSize: 10, padding: '4px 10px' }} onClick={() => setDecision(pid, 'rejected')}>
                              Reject
                            </button>
                            <button type="button" className="df-btn secondary" style={{ fontSize: 10, padding: '4px 10px' }} onClick={() => onEditMapping(pid)}>
                              Edit mapping
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 8, color: '#991b1b' }}>3. Quarantined</div>
          <div style={{ overflowX: 'auto', borderRadius: 10, border: '1px solid #fecaca', background: '#ffffff' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5, minWidth: 720 }}>
              <thead>
                <tr style={{ background: '#fef2f2' }}>
                  {['Family', 'Upload', 'Column', 'Drift type', 'Reason', 'Stats (from drift run)', 'Status'].map((h) => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 8px', borderBottom: '1px solid #fecaca', color: '#991b1b', fontWeight: 800 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!dashboard?.quarantined?.length ? (
                  <tr>
                    <td colSpan={7} style={{ padding: 12, color: '#64748b' }}>
                      No quarantined columns for this scope.
                    </td>
                  </tr>
                ) : (
                  dashboard.quarantined.map((row) => (
                    <tr key={`${row.family}-${displaySource(row)}-${row.column}-${row.reason}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '8px 8px', fontWeight: 800, color: '#991b1b' }}>{row.family || '—'}</td>
                      <td style={{ padding: '8px 8px', fontWeight: 600, color: '#475569', fontSize: 11 }}>{displaySource(row)}</td>
                      <td style={{ padding: '8px 8px', fontWeight: 800 }}>{row.column}</td>
                      <td style={{ padding: '8px 8px', color: '#334155' }}>{row.drift_type}</td>
                      <td style={{ padding: '8px 8px', color: '#475569', lineHeight: 1.45 }}>{row.reason}</td>
                      <td style={{ padding: '8px 8px', color: '#475569', fontSize: 10, lineHeight: 1.4, maxWidth: 260, whiteSpace: 'pre-wrap' }}>
                        {row.numeric_evidence || '—'}
                      </td>
                      <td style={{ padding: '8px 8px', fontWeight: 800, color: '#991b1b' }}>{row.status || 'QUARANTINED'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  )
}
