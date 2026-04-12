import { useMemo, useState } from 'react'

type BehavioralSignalRow = {
  relationship_key: string
  left_dataset: string
  right_dataset: string
  left_column: string
  right_column: string
  decision: string
  confidence: number
  before_confidence?: number | null
  delta?: number | null
  confidence_source?: string
  models_used?: Record<string, number>
  history_points: number
  join_usage_count: number
  relationship_stability: number
  behavioral_score: number
  is_unstable: boolean
  drift_score: number
  join_frequency_score?: number
  co_query_frequency_score?: number
  lineage_proximity_score?: number
  stability_score?: number
  name_similarity?: number
  type_score?: number
  overlap_ratio?: number
  last_scored_at?: string
  last_used_at?: string
  behavioral_updated_at?: string
  feedback_applied: boolean
}

type JoinedViewRow = {
  dataset_name: string
  upstream_datasets: string[]
  downstream_datasets: string[]
  row_count: number
  validation_status: string
  created_at?: string
  last_updated?: string
  location?: string
}

type BehavioralSignalsResponse = {
  summary: {
    total_relationships: number
    feedback_applied_count: number
    usage_tracked_count: number
    unstable_count: number
    avg_stability: number
    feedback_ratio: number
    feedback_mode: string
    feedback_enabled: boolean
    joined_views_count?: number
  }
  signals: BehavioralSignalRow[]
  joined_views?: JoinedViewRow[]
  generated_at: string
}

type Props = {
  loading: boolean
  behavioralSignals: BehavioralSignalsResponse | null
  safeDate: (value?: string) => string
  formatNumber: (value: number) => string
  decisionClass: (decision: string) => string
}

function clamp01(value?: number | null): number {
  return Math.max(0, Math.min(1, Number(value) || 0))
}

function formatScore(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 'N/A'
  }
  return value.toFixed(3)
}

function ratioPercent(value?: number | null): string {
  return `${(clamp01(value) * 100).toFixed(1)}%`
}

function relationshipLabel(row: BehavioralSignalRow): string {
  return `${row.left_dataset}.${row.left_column} -> ${row.right_dataset}.${row.right_column}`
}

export default function BehavioralSignalsPage({
  loading,
  behavioralSignals,
  safeDate,
  formatNumber,
  decisionClass,
}: Props) {
  const [showAllRows, setShowAllRows] = useState(false)

  if (!behavioralSignals) {
    return (
      <section className="df-tab-content">
        <article className="glass-card df-state-card">
          <h3>{loading ? 'Loading Behavioral Signals...' : 'No Behavioral Signals Loaded Yet'}</h3>
          <p className="muted-text">
            {loading
              ? 'Collecting metadata-captured usage, drift, and stability signals...'
              : 'Use "Refresh Live Data" to load behavioral signal capture details.'}
          </p>
        </article>
      </section>
    )
  }

  const summary = behavioralSignals.summary
  const rows = behavioralSignals.signals || []
  const joinedViews = behavioralSignals.joined_views || []

  const driftedRows = useMemo(
    () => rows.filter((row) => typeof row.delta === 'number' && Math.abs(row.delta) > 0),
    [rows]
  )

  const rowsToDisplay = showAllRows ? rows : driftedRows

  const usageTimeline = useMemo(
    () =>
      [...rows]
        .filter((row) => Boolean(row.last_used_at))
        .sort((a, b) => (b.last_used_at || '').localeCompare(a.last_used_at || ''))
        .slice(0, 10),
    [rows]
  )

  const coQueryMatrix = useMemo(() => {
    const pairMap = new Map<string, { left: string; right: string; usage: number; coQuery: number }>()
    rows.forEach((row) => {
      const [a, b] = [row.left_dataset, row.right_dataset].sort((x, y) => x.localeCompare(y))
      const key = `${a}::${b}`
      const usage = Number(row.join_usage_count || 0)
      const coQuery = clamp01(row.co_query_frequency_score)
      const existing = pairMap.get(key)
      if (!existing) {
        pairMap.set(key, { left: a, right: b, usage, coQuery })
      } else {
        existing.usage += usage
        existing.coQuery = Math.max(existing.coQuery, coQuery)
      }
    })
    return [...pairMap.values()].sort((a, b) => b.usage - a.usage).slice(0, 12)
  }, [rows])

  const coldStartRows = useMemo(
    () => rows.filter((row) => row.join_usage_count <= 0 || row.history_points <= 1 || !row.feedback_applied).slice(0, 8),
    [rows]
  )

  const driftAlerts = useMemo(
    () => rows.filter((row) => row.is_unstable || Math.abs(Number(row.delta || 0)) >= 0.2).slice(0, 8),
    [rows]
  )

  return (
    <section className="df-tab-content">
      <article className="glass-card behavioral-signals-card">
        <h3>Behavioral Signals Capture</h3>
        <p className="muted-text">
          This tab shows only metadata-captured behavioral signals, confidence drift, usage history, and newly joined views recorded in the catalog.
        </p>

        <div className="behavioral-kpi-grid">
          <div className="agent-metric-chip">
            <span>Total Relationships</span>
            <strong>{formatNumber(summary.total_relationships || 0)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Feedback Applied</span>
            <strong>
              {formatNumber(summary.feedback_applied_count || 0)} ({ratioPercent(summary.feedback_ratio || 0)})
            </strong>
          </div>
          <div className="agent-metric-chip">
            <span>Usage Tracked</span>
            <strong>{formatNumber(summary.usage_tracked_count || 0)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Unstable Alerts</span>
            <strong>{formatNumber(summary.unstable_count || 0)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Avg Stability</span>
            <strong>{Number(summary.avg_stability || 0).toFixed(3)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Joined Views</span>
            <strong>{formatNumber(summary.joined_views_count || joinedViews.length)}</strong>
          </div>
        </div>

        <div className="behavioral-note-row">
          <span className="behavior-flag">Capture Mode: {summary.feedback_mode || 'catalog_history_hydration'}</span>
          <span className="behavior-flag">Snapshot: {safeDate(behavioralSignals.generated_at)}</span>
          <span className="behavior-flag">Drifted rows: {formatNumber(driftedRows.length)}</span>
          <span className="behavior-flag">Cold-start rows: {formatNumber(coldStartRows.length)}</span>
        </div>

        <div className="agent-actions-row">
          <button
            type="button"
            className={`df-btn secondary ${!showAllRows ? 'active' : ''}`}
            onClick={() => setShowAllRows(false)}
          >
            Drifted Confidence Only
          </button>
          <button
            type="button"
            className={`df-btn secondary ${showAllRows ? 'active' : ''}`}
            onClick={() => setShowAllRows(true)}
          >
            Show All Relationships
          </button>
        </div>

        <div className="behavioral-layout-grid">
          <section className="behavioral-panel">
            <h4>Join Usage Timeline</h4>
            <ul className="runtime-stream-list">
              {usageTimeline.length ? (
                usageTimeline.map((row) => (
                  <li key={`timeline-${row.relationship_key}`}>
                    <strong>{safeDate(row.last_used_at)}</strong> | {row.left_dataset} + {row.right_dataset} | usage {formatNumber(row.join_usage_count || 0)}
                  </li>
                ))
              ) : (
                <li>No join usage events captured yet.</li>
              )}
            </ul>
          </section>

          <section className="behavioral-panel">
            <h4>Co-Query Matrix (Pair Intensity)</h4>
            <div className="df-table-wrap">
              <table className="df-table">
                <thead>
                  <tr>
                    <th>Dataset A</th>
                    <th>Dataset B</th>
                    <th>Usage Count</th>
                    <th>Co-Query Score</th>
                  </tr>
                </thead>
                <tbody>
                  {coQueryMatrix.map((pair) => (
                    <tr key={`coq-${pair.left}-${pair.right}`}>
                      <td>{pair.left}</td>
                      <td>{pair.right}</td>
                      <td>{formatNumber(pair.usage)}</td>
                      <td>
                        <div className="mini-heat-wrap">
                          <div className="mini-heat-fill" style={{ width: `${pair.coQuery * 100}%` }} />
                          <span>{pair.coQuery.toFixed(3)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="behavioral-panel">
            <h4>Stability and Drift Alerts</h4>
            <ul className="agent-insight-list">
              {driftAlerts.length ? (
                driftAlerts.map((row) => (
                  <li key={`alert-${row.relationship_key}`}>
                    <span>{relationshipLabel(row)}</span>
                    <strong>{row.is_unstable ? 'UNSTABLE' : 'DRIFT'}</strong>
                  </li>
                ))
              ) : (
                <li>
                  <span>No drift alerts above threshold.</span>
                  <strong>STABLE</strong>
                </li>
              )}
            </ul>
          </section>

          <section className="behavioral-panel">
            <h4>Cold-Start Relationships</h4>
            <div className="df-table-wrap">
              <table className="df-table">
                <thead>
                  <tr>
                    <th>Relationship</th>
                    <th>Confidence</th>
                    <th>Behavioral History</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {coldStartRows.length ? (
                    coldStartRows.map((row) => (
                      <tr key={`cold-${row.relationship_key}`}>
                        <td>{relationshipLabel(row)}</td>
                        <td>{formatScore(row.confidence)}</td>
                        <td>{row.history_points <= 1 ? 'None / Minimal' : 'Available'}</td>
                        <td>{row.feedback_applied ? 'Early feedback captured' : 'Cold-start'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4}>No cold-start rows detected.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="behavioral-panel">
            <h4>Newly Joined Views (Catalog)</h4>
            <div className="df-table-wrap">
              <table className="df-table">
                <thead>
                  <tr>
                    <th>View</th>
                    <th>Upstream</th>
                    <th>Rows</th>
                    <th>Status</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {joinedViews.length ? (
                    joinedViews.map((view) => (
                      <tr key={`view-${view.dataset_name}`}>
                        <td>
                          <strong>{view.dataset_name}</strong>
                          <div className="muted-text">{view.location || 'virtual://unknown'}</div>
                        </td>
                        <td>{view.upstream_datasets?.join(', ') || 'N/A'}</td>
                        <td>{formatNumber(view.row_count || 0)}</td>
                        <td>{view.validation_status || 'unknown'}</td>
                        <td>{safeDate(view.last_updated || view.created_at)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5}>No joined views registered yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <div className="df-table-wrap behavioral-all-rows">
          <table className="df-table">
            <thead>
              <tr>
                <th>Relationship</th>
                <th>Decision</th>
                <th>Confidence</th>
                <th>Behavioral Signals</th>
                <th>Usage / Drift</th>
                <th>Timestamps</th>
              </tr>
            </thead>
            <tbody>
              {rowsToDisplay.map((row) => (
                <tr key={row.relationship_key}>
                  <td>
                    <strong>{relationshipLabel(row)}</strong>
                    <div className="muted-text">{row.relationship_key}</div>
                  </td>
                  <td>
                    <span className={`df-decision ${decisionClass(row.decision)}`}>{row.decision}</span>
                    <div className="muted-text">Source: {row.confidence_source || 'unknown'}</div>
                  </td>
                  <td>
                    <strong>{formatScore(row.before_confidence)} {'->'} {formatScore(row.confidence)}</strong>
                    <div className="muted-text">Delta {formatScore(row.delta)}</div>
                    <div className="muted-text">
                      Core: n={formatScore(row.name_similarity)} t={formatScore(row.type_score)} o={formatScore(row.overlap_ratio)}
                    </div>
                  </td>
                  <td>
                    <div>join {formatScore(row.join_frequency_score)}</div>
                    <div>co-query {formatScore(row.co_query_frequency_score)}</div>
                    <div>lineage {formatScore(row.lineage_proximity_score)}</div>
                    <div>stability {formatScore(row.stability_score ?? row.relationship_stability)}</div>
                  </td>
                  <td>
                    <div>Usage: {formatNumber(row.join_usage_count || 0)}</div>
                    <div>Drift: {formatScore(row.drift_score)}</div>
                    <div className="muted-text">{row.is_unstable ? 'Unstable flagged' : 'Stable'}</div>
                  </td>
                  <td>
                    <div className="muted-text">Behavioral update: {safeDate(row.behavioral_updated_at)}</div>
                    <div className="muted-text">Last scored: {safeDate(row.last_scored_at)}</div>
                    <div className="muted-text">Last used: {safeDate(row.last_used_at)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  )
}
