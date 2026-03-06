type Props = {
  loading: boolean
  logs: any
  safeDate: (value?: string) => string
  decisionClass: (decision: string) => string
}

export default function OpsLogsPage({ loading, logs, safeDate, decisionClass }: Props) {
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

  return (
    <section className="df-tab-content">
      <article className="glass-card">
        <h3>Operational Logs</h3>
        <div className="df-table-wrap">
          <table className="df-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Event</th>
                <th>Dataset Pair</th>
                <th>Confidence</th>
                <th>Decision</th>
                <th>Drift</th>
              </tr>
            </thead>
            <tbody>
              {logs.events.map((event: any, index: number) => (
                <tr key={`${event.relationship_key}-${index}`}>
                  <td>{safeDate(event.timestamp)}</td>
                  <td>{event.event}</td>
                  <td>{event.dataset_pair}</td>
                  <td>{event.confidence.toFixed(3)}</td>
                  <td>
                    <span className={`df-decision ${decisionClass(event.decision)}`}>{event.decision}</span>
                  </td>
                  <td>{typeof event.drift_score === 'number' ? event.drift_score.toFixed(3) : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  )
}
