import React from 'react'

const checks = [
  { name: 'Pipeline connectivity', status: 'Pass' },
  { name: 'Metadata sync', status: 'Pass' },
  { name: 'Schema drift alert', status: 'Review' },
  { name: 'Catalog indexing', status: 'Pass' },
]

export default function DataFabricTestingPage() {
  return (
    <div className="test-page-shell">
      <h2>Data Fabric Testing Page</h2>
      <p>Use this page to validate data integration, metadata flow, and orchestration checks.</p>

      <div className="test-grid">
        {checks.map((check) => (
          <div key={check.name} className="test-card">
            <span className="test-name">{check.name}</span>
            <span className={`test-status ${check.status.toLowerCase()}`}>{check.status}</span>
          </div>
        ))}
      </div>

      <div className="test-actions">
        <button type="button" className="sidebar-btn">Run smoke checks</button>
        <button type="button" className="sidebar-btn">Refresh statuses</button>
      </div>
    </div>
  )
}
