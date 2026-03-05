import { useState } from 'react';
import { Badge } from './Badge';
import { DashboardData } from '../types';

interface MedallionPageProps {
  architecture: NonNullable<DashboardData['architecture']>;
  datasetOverview: DashboardData['dataset_overview'];
  csvPreviews: DashboardData['csv_previews'];
}

export function MedallionPage({ architecture, datasetOverview, csvPreviews }: MedallionPageProps) {
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);

  const stageDatasets: Record<string, string[]> = architecture.stages.reduce((acc, stage) => {
    acc[stage.name] = stage.datasets || [];
    return acc;
  }, {} as Record<string, string[]>);

  const findDatasetPreview = (datasetName: string) => {
    if (!csvPreviews) return null;
    
    if (csvPreviews[datasetName]) {
      return csvPreviews[datasetName];
    }
    
    for (const [key, preview] of Object.entries(csvPreviews)) {
      if (key.includes(datasetName) || preview.file.replace('.csv', '') === datasetName) {
        return preview;
      }
    }
    
    return null;
  };

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Medallion Architecture</h2>
        <p className="section-description">
          Data flow through Bronze → Silver → Gold layers with schema drift detection
        </p>
      </div>

      {/* Medallion Pipeline */}
      <div className="card">
        <div className="card-header">
          <h3>Data Pipeline</h3>
          {architecture.drift_gate_note && (
            <Badge label="Drift Gate Active" tone="warning" />
          )}
        </div>
        <div className="medallion-pipeline">
          {architecture.stages.map((stage, idx) => (
            <div key={stage.name} className="pipeline-stage-group">
              <button
                className={`pipeline-stage ${stage.status === 'drift-gate' ? 'gate' : ''} ${selectedStage === stage.name ? 'selected' : ''}`}
                onClick={() => setSelectedStage(stage.name)}
              >
                <div className="stage-icon">
                  {stage.status === 'drift-gate' ? '⚠️' : 
                   stage.name.includes('Bronze') ? '🟤' :
                   stage.name.includes('Silver') ? '⚪' :
                   stage.name.includes('Gold') ? '🟡' : '📊'}
                </div>
                <div className="stage-content">
                  <div className="stage-name">{stage.name}</div>
                  <div className="stage-count">
                    {stageDatasets[stage.name]?.length || 0} datasets
                  </div>
                </div>
                {stage.status === 'drift-gate' && (
                  <div className="stage-badge">
                    <Badge label="Drift Gate" tone="warning" />
                  </div>
                )}
              </button>
              {idx < architecture.stages.length - 1 && (
                <div className="pipeline-arrow">→</div>
              )}
            </div>
          ))}
        </div>
        <div className="help-text">
          Click any stage to explore datasets and preview data
        </div>
      </div>

      {/* Stage Datasets Modal */}
      {selectedStage && !selectedDataset && (
        <div className="modal-backdrop" onClick={() => setSelectedStage(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">{selectedStage} Layer Datasets</h3>
                <div className="modal-subtitle">
                  {stageDatasets[selectedStage]?.length || 0} datasets available
                </div>
              </div>
              <button className="btn btn-ghost" onClick={() => setSelectedStage(null)}>
                Close
              </button>
            </div>
            <div className="modal-body">
              <div className="datasets-grid">
                {(stageDatasets[selectedStage] || []).map((dataset) => {
                  const meta = datasetOverview?.[dataset];
                  return (
                    <button
                      key={dataset}
                      className="dataset-card-btn"
                      onClick={() => setSelectedDataset(dataset)}
                    >
                      <div className="dataset-icon">📄</div>
                      <div className="dataset-info">
                        <div className="dataset-name">{dataset}</div>
                        {meta && (
                          <div className="dataset-meta">
                            {meta.rows} rows · {meta.cols.length} columns
                          </div>
                        )}
                      </div>
                      <div className="dataset-action">→</div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dataset Preview Modal */}
      {selectedDataset && (
        <div className="modal-backdrop" onClick={() => setSelectedDataset(null)}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">{selectedDataset}</h3>
                <div className="modal-subtitle">
                  {(() => {
                    const preview = findDatasetPreview(selectedDataset);
                    if (preview) {
                      return `${preview.rows_total} rows · ${preview.columns.length} columns · Showing first 10 rows`;
                    }
                    if (datasetOverview?.[selectedDataset]) {
                      return `${datasetOverview[selectedDataset].rows} rows · ${datasetOverview[selectedDataset].cols.length} columns`;
                    }
                    return 'Dataset information';
                  })()}
                </div>
              </div>
              <div className="modal-actions">
                <button className="btn btn-ghost" onClick={() => setSelectedDataset(null)}>
                  ← Back
                </button>
                <button className="btn btn-ghost" onClick={() => { setSelectedDataset(null); setSelectedStage(null); }}>
                  Close
                </button>
              </div>
            </div>
            <div className="modal-body">
              {(() => {
                const preview = findDatasetPreview(selectedDataset);
                if (preview) {
                  return (
                    <>
                      <div className="preview-section">
                        <h4>Schema</h4>
                        <div className="chip-row">
                          {preview.columns.map((col: string) => (
                            <Badge key={col} label={col} tone="info" />
                          ))}
                        </div>
                      </div>
                      <div className="preview-section">
                        <h4>Data Preview (First 10 Rows)</h4>
                        <div className="table-wrapper">
                          <table className="data-table compact">
                            <thead>
                              <tr>
                                {preview.columns.map((col: string) => (
                                  <th key={col}>{col}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {preview.preview.map((row: any, idx: number) => (
                                <tr key={idx}>
                                  {preview.columns.map((col: string) => (
                                    <td key={col}>
                                      {row[col] !== null && row[col] !== undefined 
                                        ? String(row[col]) 
                                        : '—'}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </>
                  );
                }
                if (datasetOverview?.[selectedDataset]) {
                  return (
                    <>
                      <div className="preview-section">
                        <h4>Schema</h4>
                        <div className="chip-row">
                          {datasetOverview[selectedDataset].cols.map((col: string) => (
                            <Badge key={col} label={col} tone="info" />
                          ))}
                        </div>
                      </div>
                      <div className="empty-state">
                        <div className="empty-icon">📊</div>
                        <p>CSV preview not available</p>
                      </div>
                    </>
                  );
                }
                return (
                  <div className="empty-state">
                    <div className="empty-icon">❌</div>
                    <p>Dataset not found</p>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
