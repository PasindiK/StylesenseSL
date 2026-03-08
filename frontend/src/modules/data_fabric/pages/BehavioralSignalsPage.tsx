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
  prior_score_available?: boolean
  history_points: number
  join_usage_count: number
  relationship_stability: number
  behavioral_score: number
  is_unstable: boolean
  drift_score: number
  last_scored_at?: string
  last_used_at?: string
  behavioral_updated_at?: string
  feedback_applied: boolean
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
  }
  signals: BehavioralSignalRow[]
  generated_at: string
}

type Props = {
  loading: boolean
  behavioralSignals: BehavioralSignalsResponse | null
  safeDate: (value?: string) => string
  formatNumber: (value: number) => string
  decisionClass: (decision: string) => string
}

function ratioPercent(value: number): string {
  return `${(Math.max(0, Math.min(1, Number(value) || 0)) * 100).toFixed(1)}%`
}

export default function BehavioralSignalsPage({
  loading,
  behavioralSignals,
  safeDate,
  formatNumber,
  decisionClass,
}: Props) {
  if (!behavioralSignals) {
    return (
      <section className="df-tab-content">
        <article className="glass-card df-state-card">
          <h3>{loading ? 'Loading Behavioral Signals...' : 'No Behavioral Signals Loaded Yet'}</h3>
          <p className="muted-text">
            {loading
              ? 'Collecting usage, stability, and drift feedback from metadata catalog...'
              : 'Use "Refresh Live Data" to load behavioral signal capture details.'}
          </p>
        </article>
      </section>
    )
  }

  const summary = behavioralSignals.summary
  const rows = behavioralSignals.signals || []
  const [showAllRows, setShowAllRows] = useState(false)

  const driftedRows = useMemo(
    () => rows.filter((row) => typeof row.delta === 'number' && Math.abs(row.delta) > 0),
    [rows]
  )

  const rowsToDisplay = showAllRows ? rows : driftedRows

  function formatScore(value?: number | null): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return 'N/A'
    }
    return value.toFixed(3)
  }

  return (
    <section className="df-tab-content">
      <article className="glass-card behavioral-signals-card">
        <h3>Behavioral Signal Capture Panel</h3>
        <p className="muted-text">
          This tab shows post-run behavioral capture and confirms those signals are now fed into fresh feature-vector
          construction through catalog history hydration.
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
            <span>Unstable Relationships</span>
            <strong>{formatNumber(summary.unstable_count || 0)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Avg Stability</span>
            <strong>{Number(summary.avg_stability || 0).toFixed(3)}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Feedback Mode</span>
            <strong>{summary.feedback_mode || 'N/A'}</strong>
          </div>
        </div>

        <div className="behavioral-note-row">
          <span className="behavior-flag">Capture: catalog behavioral updates</span>
          <span className="behavior-flag">Feedback: feature-vector hydration enabled</span>
          <span className="behavior-flag">Confidence drifted: {formatNumber(driftedRows.length)}</span>
          <span className="muted-text">Snapshot: {safeDate(behavioralSignals.generated_at)}</span>
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

        {!rowsToDisplay.length ? (
          <p className="muted-text">
            No confidence drift detected in the current snapshot. Switch to "Show All Relationships" to inspect full
            behavioral capture.
          </p>
        ) : null}

        <div className="df-table-wrap">
          <table className="df-table">
            <thead>
              <tr>
                <th>Relationship</th>
                <th>Decision</th>
                <th>Confidence (Before -&gt; After)</th>
                <th>Behavioral</th>
                <th>Usage / Drift</th>
                <th>Timestamps</th>
              </tr>
            </thead>
            <tbody>
              {rowsToDisplay.map((row) => (
                <tr key={row.relationship_key}>
                  <td>
                    <strong>
                      {row.left_dataset}.{row.left_column} {'->'} {row.right_dataset}.{row.right_column}
                    </strong>
                    <div className="muted-text">{row.relationship_key}</div>
                  </td>
                  <td>
                    <span className={`df-decision ${decisionClass(row.decision)}`}>{row.decision}</span>
                    <div className="muted-text">Feedback: {row.feedback_applied ? 'Applied' : 'Pending'}</div>
                    <div className="muted-text">Source: {row.confidence_source || 'unknown'}</div>
                  </td>
                  <td>
                    <strong>
                      {formatScore(row.before_confidence)} {'->'} {formatScore(row.confidence)}
                    </strong>
                    <div className="muted-text">Delta {formatScore(row.delta)}</div>
                    {row.models_used && Object.keys(row.models_used).length ? (
                      <div className="muted-text">
                        Models:{' '}
                        {Object.entries(row.models_used)
                          .map(([name, prob]) => `${name}=${Number(prob).toFixed(3)}`)
                          .join(' | ')}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <div>Stability {Number(row.relationship_stability || 0).toFixed(3)}</div>
                    <div>Behavioral Score {Number(row.behavioral_score || 0).toFixed(3)}</div>
                    <div className="muted-text">History points: {formatNumber(row.history_points || 0)}</div>
                  </td>
                  <td>
                    <div>Join usage: {formatNumber(row.join_usage_count || 0)}</div>
                    <div>Drift score: {Number(row.drift_score || 0).toFixed(3)}</div>
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
