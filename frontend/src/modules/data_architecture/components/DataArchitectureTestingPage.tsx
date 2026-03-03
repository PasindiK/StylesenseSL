import React from 'react'

const checks = [
  { name: 'Model alignment', status: 'Pass' },
  { name: 'Standards compliance', status: 'Pass' },
  { name: 'Lineage consistency', status: 'Review' },
  { name: 'Reference architecture fit', status: 'Pass' },
]

export default function DataArchitectureTestingPage() {
  return (
    <div className="test-page-shell">
      <h2>Data Architecture Testing Page</h2>
      <p>Use this page to validate architecture standards, governance rules, and model consistency.</p>

      <div className="test-grid">
        {checks.map((check) => (
          <div key={check.name} className="test-card">
            <span className="test-name">{check.name}</span>
            <span className={`test-status ${check.status.toLowerCase()}`}>{check.status}</span>
          </div>
        ))}
      </div>

      <div className="test-actions">
        <button type="button" className="sidebar-btn">Run architecture checks</button>
        <button type="button" className="sidebar-btn">Refresh statuses</button>
      </div>
    </div>
  )
}
