import { useState } from 'react';
import { Badge } from './Badge';
import type { DriftEvent } from '../types';

interface DriftEventsPageProps {
  driftEvents: DriftEvent[];
}

export function DriftEventsPage({ driftEvents }: DriftEventsPageProps) {
  const [selectedDrift, setSelectedDrift] = useState<DriftEvent | null>(null);

  if (!driftEvents || driftEvents.length === 0) {
    return (
      <div className="page-section">
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h3>No Drift Events</h3>
          <p>No schema drift has been detected yet. Events will appear here as data is processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Recent Drift Events</h2>
        <Badge label={`${driftEvents.length} events`} tone="info" />
      </div>

      <div className="card">
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Table</th>
                <th>Timestamp</th>
                <th>Changes</th>
                <th>Decision</th>
                <th>Approval</th>
                <th>Risk</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {driftEvents.map((evt) => (
                <tr key={evt.file}>
                  <td>
                    <div className="table-cell-main">{evt.table}</div>
                    <div className="table-cell-sub">{evt.file}</div>
                  </td>
                  <td className="table-cell-timestamp">{evt.timestamp}</td>
                  <td className="table-cell-changes">
                    <div className="change-summary">
                      {evt.counts?.new ? <span className="change-item success">+{evt.counts.new}</span> : null}
                      {evt.counts?.missing ? <span className="change-item danger">-{evt.counts.missing}</span> : null}
                      {evt.counts?.dtype ? <span className="change-item warning">Δ{evt.counts.dtype}</span> : null}
                      {evt.counts?.renames ? <span className="change-item info">↻{evt.counts.renames}</span> : null}
                    </div>
                  </td>
                  <td>
                    <Badge label={evt.decision || 'N/A'} tone="info" />
                  </td>
                  <td>
                    <Badge
                      label={evt.requires_approval ? 'Pending' : 'Auto'}
                      tone={evt.requires_approval ? 'warning' : 'success'}
                    />
                  </td>
                  <td>
                    <Badge
                      tone={
                        evt.risk_level === 'high' ? 'danger' :
                        evt.risk_level === 'medium' ? 'warning' :
                        'success'
                      }
                      label={evt.risk_level || 'low'}
                    />
                  </td>
                  <td>
                    <button 
                      className="btn-small btn-ghost" 
                      onClick={() => setSelectedDrift(evt)}
                    >
                      View Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Drift Detail Modal */}
      {selectedDrift && (
        <div className="modal-backdrop" onClick={() => setSelectedDrift(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">{selectedDrift.table} Drift Details</h3>
                <div className="modal-subtitle">{selectedDrift.timestamp}</div>
              </div>
              <button className="btn btn-ghost" onClick={() => setSelectedDrift(null)}>
                Close
              </button>
            </div>
            <div className="modal-body">
              <div className="drift-section">
                <h4>New Columns ({selectedDrift.diff?.new_columns?.length ?? 0})</h4>
                <div className="chip-row">
                  {selectedDrift.diff?.new_columns?.map((c) => (
                    <Badge key={c} label={c} tone="success" />
                  )) || <span className="muted">None</span>}
                </div>
              </div>

              <div className="drift-section">
                <h4>Missing Columns ({selectedDrift.diff?.missing_columns?.length ?? 0})</h4>
                <div className="chip-row">
                  {selectedDrift.diff?.missing_columns?.map((c) => (
                    <Badge key={c} label={c} tone="danger" />
                  )) || <span className="muted">None</span>}
                </div>
              </div>

              <div className="drift-section">
                <h4>Column Renames ({selectedDrift.diff?.renames?.length ?? 0})</h4>
                {selectedDrift.diff?.renames && selectedDrift.diff.renames.length > 0 ? (
                  <div className="rename-list">
                    {selectedDrift.diff.renames.map((r, idx) => (
                      <div key={idx} className="rename-item">
                        <span className="rename-old">{r.old_name}</span>
                        <span className="rename-arrow">→</span>
                        <span className="rename-new">{r.new_name}</span>
                        <span className="rename-meta">
                          {(r.similarity * 100).toFixed(0)}% similar
                          {r.type_match && ' · type match ✓'}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="muted">None</div>
                )}
              </div>

              <div className="drift-section">
                <h4>Type Changes ({selectedDrift.diff?.dtype_changes?.length ?? 0})</h4>
                {selectedDrift.diff?.dtype_changes && selectedDrift.diff.dtype_changes.length > 0 ? (
                  <div className="type-change-list">
                    {selectedDrift.diff.dtype_changes.map((c) => (
                      <div key={c.column} className="type-change-item">
                        <span className="type-column">{c.column}</span>
                        <span className="type-change">
                          <span className="type-old">{c.expected}</span>
                          <span className="type-arrow">→</span>
                          <span className="type-new">{c.actual}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="muted">None</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
