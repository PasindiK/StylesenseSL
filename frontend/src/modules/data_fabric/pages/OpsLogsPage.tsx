import { useMemo, useState } from 'react'

type LogEvent = {
  timestamp?: string
  event: string
  dataset_pair: string
  relationship_key: string
  confidence: number
  base_confidence?: number
  behavior_adjusted_delta?: number
  decision: string
  delta_confidence?: number
  cold_start?: boolean
  feedback?: string
  drift_score?: number
  join_frequency_score?: number
  co_query_frequency_score?: number
  lineage_proximity_score?: number
  stability_score?: number
  model_version?: string
  join_usage_count?: number
  outcome?: string
}

type LogsResponse = {
  events: LogEvent[]
}

type Props = {
  loading: boolean
  logs: LogsResponse | null
  safeDate: (value?: string) => string
  decisionClass: (decision: string) => string
}

function formatScore(value?: number): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '-'
  }
  return value.toFixed(3)
}

export default function OpsLogsPage({ loading, logs, safeDate, decisionClass }: Props) {
  const [eventFilter, setEventFilter] = useState('all')
  const [pairFilter, setPairFilter] = useState('')
  const [coldOnly, setColdOnly] = useState(false)

  if (!logs) {
    return (
      <section className="df-tab-content">
        <article className="glass-card df-state-card">
          <h3>{loading ? 'Loading Operational Logs...' : 'No Logs Loaded Yet'}</h3>
          <p className="muted-text">
            {loading
              ? 'Fetching integration and drift events from backend...'
              : 'Use "Refresh Live Data" to load operational events.'}
          </p>
        </article>
      </section>
    )
  }

  const events = logs.events || []

  const eventTypes = useMemo(() => {
    const set = new Set<string>()
    events.forEach((event) => set.add(event.event))
    return ['all', ...Array.from(set).sort((a, b) => a.localeCompare(b))]
  }, [events])

  const filteredEvents = useMemo(() => {
    const token = pairFilter.trim().toLowerCase()
    return events.filter((event) => {
      if (eventFilter !== 'all' && event.event !== eventFilter) {
        return false
      }
      if (coldOnly && !event.cold_start) {
        return false
      }
      if (token && !event.dataset_pair.toLowerCase().includes(token) && !event.relationship_key.toLowerCase().includes(token)) {
        return false
      }
      return true
    })
  }, [events, eventFilter, coldOnly, pairFilter])

  const eventCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    events.forEach((event) => {
      counts[event.event] = (counts[event.event] || 0) + 1
    })
    return counts
  }, [events])

  const driftAlerts = useMemo(
    () => events.filter((event) => Math.abs(Number(event.drift_score || 0)) >= 0.2).length,
    [events]
  )

  const coldStarts = useMemo(() => events.filter((event) => Boolean(event.cold_start)).length, [events])

  return (
    <section className="df-tab-content">
      <article className="glass-card">
        <h3>Operational Logs</h3>

        <div className="agent-monitor-grid">
          <div className="agent-metric-chip">
            <span>Total Events</span>
            <strong>{events.length}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Scored</span>
            <strong>{eventCounts.relationship_scored || 0}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Inferred</span>
            <strong>{eventCounts.relationship_inferred || 0}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Join Executed</span>
            <strong>{eventCounts.join_executed || 0}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Behavioral Updates</span>
            <strong>{eventCounts.behavioral_update || 0}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Drift Alerts (&gt;= 0.2)</span>
            <strong>{driftAlerts}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Cold-Start Events</span>
            <strong>{coldStarts}</strong>
          </div>
          <div className="agent-metric-chip">
            <span>Model Retrains</span>
            <strong>{eventCounts.model_retrained || 0}</strong>
          </div>
        </div>

        <div className="agent-actions-row">
          <select
            className="behavioral-search"
            value={eventFilter}
            onChange={(event) => setEventFilter(event.target.value)}
            aria-label="Filter by event type"
          >
            {eventTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <input
            className="behavioral-search"
            type="text"
            value={pairFilter}
            onChange={(event) => setPairFilter(event.target.value)}
            placeholder="Filter by dataset pair or relationship key"
          />
          <button type="button" className={`df-btn secondary ${coldOnly ? 'active' : ''}`} onClick={() => setColdOnly((value) => !value)}>
            {coldOnly ? 'Show All Events' : 'Cold-Start Only'}
          </button>
        </div>

        <div className="df-table-wrap">
          <table className="df-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Event</th>
                <th>Dataset Pair</th>
                <th>Base</th>
                <th>Behavior Adj</th>
                <th>Final</th>
                <th>Decision</th>
                <th>Delta</th>
                <th>Cold Start</th>
                <th>Drift Alert</th>
                <th>Feedback</th>
                <th>Behavioral Snapshot</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.map((event, index) => {
                const drift = Number(event.drift_score || 0)
                const driftAlert = Math.abs(drift) >= 0.2
                return (
                  <tr key={`${event.relationship_key}-${event.event}-${index}`} className={driftAlert ? 'selected-row' : ''}>
                    <td>{safeDate(event.timestamp)}</td>
                    <td>
                      <strong>{event.event}</strong>
                      {event.model_version ? <div className="muted-text">model={event.model_version}</div> : null}
                    </td>
                    <td>
                      <div>{event.dataset_pair}</div>
                      <div className="muted-text">{event.relationship_key}</div>
                    </td>
                    <td>{formatScore(event.base_confidence)}</td>
                    <td>{formatScore(event.behavior_adjusted_delta)}</td>
                    <td>{formatScore(event.confidence)}</td>
                    <td>
                      <span className={`df-decision ${decisionClass(event.decision)}`}>{event.decision}</span>
                    </td>
                    <td>{formatScore(event.delta_confidence)}</td>
                    <td>{event.cold_start ? 'Yes' : 'No'}</td>
                    <td className={driftAlert ? 'delta-negative' : 'delta-positive'}>
                      {driftAlert ? `ALERT (${formatScore(event.drift_score)})` : formatScore(event.drift_score)}
                    </td>
                    <td>{event.feedback || 'pending'}</td>
                    <td>
                      <div>join={formatScore(event.join_frequency_score)}</div>
                      <div>coQ={formatScore(event.co_query_frequency_score)}</div>
                      <div>lineage={formatScore(event.lineage_proximity_score)}</div>
                      <div>stability={formatScore(event.stability_score)}</div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  )
}
