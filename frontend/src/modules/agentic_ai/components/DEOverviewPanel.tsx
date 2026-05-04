import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { getAgenticApiBase } from '../../../lib/agenticApiBase'

const PIPELINE_STEPS = [
  { step: '1', label: 'Dataset Upload', agent: 'Ingestion Agent', detail: 'Dataset accepted and staged for semantic monitoring.' },
  { step: '2', label: 'Column Profiling', agent: 'Profiling Agent', detail: 'Types, scale, missingness, and patterns per column.' },
  { step: '3', label: 'Semantic Profile', agent: 'Semantic Profile Agent', detail: 'Roles, units, and semantic signatures.' },
  { step: '4', label: 'Internal Drift', agent: 'Semantic Drift Agent', detail: 'Consistency checks inside the upload.' },
  { step: '5', label: 'External Drift', agent: 'Baseline Comparison Agent', detail: 'Compare to selected registry baseline version.' },
  { step: '6', label: 'Release Gate', agent: 'Release Gate Agent', detail: 'READY / CONDITIONAL / QUARANTINED and registry update.' },
] as const

type FamilyApiRow = {
  family_id?: string
  family_name?: string
  is_architecture_template?: boolean
  version_count?: number
  versions?: unknown[]
  latest_version?: number
  updated_at?: string
}

type DriftRunApiRow = {
  run_id?: string
  dataset_name?: string
  created_at?: string
  family_id?: string | null
  dataset_rows?: number | null
}

export default function DEOverviewPanel() {
  const apiBase = useMemo(() => getAgenticApiBase(), [])
  const [families, setFamilies] = useState<FamilyApiRow[]>([])
  const [runs, setRuns] = useState<DriftRunApiRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [famRes, runRes] = await Promise.all([
        fetch(`${apiBase}/featureops/families`),
        fetch(`${apiBase}/featureops/drift-runs`),
      ])
      const famJson = await famRes.json()
      const runJson = await runRes.json()
      if (famJson.status === 'ok' && Array.isArray(famJson.families)) setFamilies(famJson.families as FamilyApiRow[])
      else setFamilies([])
      if (runJson.status === 'ok' && Array.isArray(runJson.runs)) setRuns(runJson.runs as DriftRunApiRow[])
      else setRuns([])
    } catch {
      setError('Could not load FeatureOps registry.')
      setFamilies([])
      setRuns([])
    } finally {
      setLoading(false)
    }
  }, [apiBase])

  useEffect(() => {
    void load()
  }, [load])

  const registryFamilies = useMemo(
    () => families.filter((f) => !f.is_architecture_template),
    [families],
  )

  const totalVersions = useMemo(
    () => registryFamilies.reduce((acc, f) => acc + Number(f.version_count ?? (f.versions || []).length ?? 0), 0),
    [registryFamilies],
  )

  const linkedRuns = useMemo(() => runs.filter((r) => !!r.family_id).length, [runs])

  const totalIngestedRows = useMemo(() => {
    let n = 0
    for (const r of runs) {
      const rows = Number(r.dataset_rows)
      if (Number.isFinite(rows)) n += rows
    }
    return n
  }, [runs])

  const recentRuns = useMemo(() => [...runs].reverse().slice(0, 12), [runs])

  return (
    <section style={{ width: '100%', maxWidth: 'none', boxSizing: 'border-box', background: '#f1f5f9', borderRadius: 12, border: '1px solid #e2e8f0', padding: '12px 0', color: '#0f172a' }}>
      <div style={{ width: '100%', display: 'grid', gap: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em' }}>DE Overview</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4, maxWidth: 720 }}>
              FeatureOps registry, upload pipeline agents, and ingested upload summary. Data matches the DE Workflow and Timeline tabs.
            </div>
          </div>
          <button
            type="button"
            className="df-btn secondary"
            onClick={() => void load()}
            disabled={loading}
            style={{ flexShrink: 0 }}
          >
            {loading ? 'Loading…' : 'Reload'}
          </button>
        </div>

        {error ? (
          <div style={{ borderRadius: 8, border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', padding: 10, fontSize: 12 }}>{error}</div>
        ) : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
          {[
            ['Registry families', String(registryFamilies.length), 'Saved dataset families (excludes architecture templates).'],
            ['Saved versions', String(totalVersions), 'Version rows summed across registry families.'],
            ['Upload events', String(runs.length), 'Drift run records from workflow uploads.'],
            ['Linked uploads', String(linkedRuns), 'Runs with a persisted family_id.'],
            ['Rows (upload events)', totalIngestedRows.toLocaleString('en-GB'), 'Sum of dataset_rows on drift runs when present.'],
          ].map(([label, value, hint]) => (
            <div key={String(label)} style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 4 }}>
              <div style={{ fontSize: 10, color: '#64748b', fontWeight: 700 }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{value}</div>
              <div style={{ fontSize: 10, color: '#94a3b8', lineHeight: 1.35 }}>{hint}</div>
            </div>
          ))}
        </div>

        <div>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a', marginBottom: 8 }}>Pipeline flow (agents)</div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 8,
              alignItems: 'stretch',
            }}
          >
            {PIPELINE_STEPS.map((s) => (
              <div
                key={s.step}
                style={{
                  borderRadius: 10,
                  border: '1px solid #cbd5e1',
                  background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
                  padding: 10,
                  display: 'grid',
                  gap: 6,
                  position: 'relative',
                }}
              >
                <div style={{ fontSize: 10, fontWeight: 800, color: '#64748b' }}>Step {s.step}</div>
                <div style={{ fontSize: 11, fontWeight: 800, color: '#0f172a' }}>{s.label}</div>
                <div style={{ fontSize: 10, fontWeight: 700, color: '#2563eb' }}>{s.agent}</div>
                <div style={{ fontSize: 9.5, color: '#475569', lineHeight: 1.35 }}>{s.detail}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
          <div style={{ borderRadius: 12, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Registry summary</div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    {['Family', 'Versions', 'Latest', 'Updated'].map((h) => (
                      <th key={h} style={{ textAlign: 'left', padding: '6px 4px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {registryFamilies.length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ padding: 10, color: '#64748b' }}>No registry families yet.</td>
                    </tr>
                  ) : (
                    registryFamilies.slice(0, 20).map((f) => (
                      <tr key={String(f.family_id ?? '')}>
                        <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{f.family_name}</td>
                        <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9' }}>{f.version_count ?? (f.versions || []).length}</td>
                        <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9' }}>v{f.latest_version ?? '—'}</td>
                        <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>
                          {f.updated_at ? new Date(f.updated_at).toLocaleDateString('en-GB', { month: 'short', day: '2-digit' }) : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ borderRadius: 12, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Recent ingested uploads</div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    {['Dataset', 'Uploaded', 'Family', 'Rows'].map((h) => (
                      <th key={h} style={{ textAlign: 'left', padding: '6px 4px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ padding: 10, color: '#64748b' }}>No upload events yet.</td>
                    </tr>
                  ) : (
                    recentRuns.map((r) => {
                      const fam = r.family_id ? families.find((x) => x.family_id === r.family_id) : null
                      const famLabel = fam?.family_name || r.family_id || '—'
                      return (
                        <tr key={r.run_id || `${r.dataset_name}-${r.created_at}`}>
                          <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{r.dataset_name}</td>
                          <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>
                            {r.created_at ? new Date(r.created_at).toLocaleString('en-GB') : '—'}
                          </td>
                          <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{famLabel}</td>
                          <td style={{ padding: '6px 4px', borderBottom: '1px solid #f1f5f9' }}>{r.dataset_rows != null ? Number(r.dataset_rows).toLocaleString('en-GB') : '—'}</td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
