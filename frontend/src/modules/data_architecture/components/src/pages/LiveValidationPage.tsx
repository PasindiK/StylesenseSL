import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import { MetricCard } from '../cards/MetricCard';
import { Panel } from '../panels/Panel';
import { useToast } from '../notifications/ToastProvider';
import * as dashboardApi from '../api/dashboardApi';
import type {
  DashboardSummaryResponse,
  LiveInputDataset,
  LiveValidationMetricsSnapshot,
  LiveValidationResult,
} from '../types';
import { compactDateTime, formatBytes, pct } from '../utils/formatters';

interface LiveValidationPageProps {
  summary: DashboardSummaryResponse;
  onOperationFinished?: () => void | Promise<void>;
}

function renderDataPreview(rows: Array<Record<string, unknown>>, emptyText: string) {
  if (!rows.length) {
    return <div className="muted">{emptyText}</div>;
  }

  const headers = Object.keys(rows[0]);
  return (
    <div className="table-scroll">
      <table className="data-table compact">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`preview-row-${index}`}>
              {headers.map((header) => (
                <td key={`${header}-${index}`}>{String(row[header] ?? 'null')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function metricDelta(before: number, after: number) {
  const delta = after - before;
  const sign = delta > 0 ? '+' : '';
  return `${sign}${delta.toLocaleString()}`;
}

function toMetricRows(snapshot: LiveValidationResult | null) {
  if (!snapshot) {
    return [];
  }

  const before: LiveValidationMetricsSnapshot = snapshot.before_metrics;
  const after: LiveValidationMetricsSnapshot = snapshot.after_metrics;

  return [
    {
      label: 'Records Ingested Today',
      before: before.total_records_ingested_today,
      after: after.total_records_ingested_today,
      delta: metricDelta(before.total_records_ingested_today, after.total_records_ingested_today),
    },
    {
      label: 'Bronze File Count',
      before: before.bronze_files_count,
      after: after.bronze_files_count,
      delta: metricDelta(before.bronze_files_count, after.bronze_files_count),
    },
    {
      label: 'Active Drift Alerts',
      before: before.active_drift_alerts,
      after: after.active_drift_alerts,
      delta: metricDelta(before.active_drift_alerts, after.active_drift_alerts),
    },
    {
      label: 'Storage Used (GB)',
      before: Number(before.total_storage_used_gb.toFixed(4)),
      after: Number(after.total_storage_used_gb.toFixed(4)),
      delta: (after.total_storage_used_gb - before.total_storage_used_gb).toFixed(4),
    },
  ];
}

export function LiveValidationPage({ summary, onOperationFinished }: LiveValidationPageProps) {
  const { showToast } = useToast();

  const [datasets, setDatasets] = useState<LiveInputDataset[]>([]);
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);

  const [selectedDatasetId, setSelectedDatasetId] = useState('');
  const [datasetAlias, setDatasetAlias] = useState('');
  const [ingestToBronze, setIngestToBronze] = useState(true);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<LiveValidationResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.id === selectedDatasetId) || null,
    [datasets, selectedDatasetId],
  );

  const resultMetricRows = useMemo(() => toMetricRows(result), [result]);

  const refreshBaselineInputs = async () => {
    try {
      setLoadingDatasets(true);
      const payload = await dashboardApi.getLiveInputDatasets(15, 5);
      setDatasets(payload.datasets);
      setDatasetsError(null);
      setSelectedDatasetId((previous) => {
        if (previous && payload.datasets.some((item) => item.id === previous)) {
          return previous;
        }
        return payload.datasets[0]?.id || '';
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load baseline datasets.';
      setDatasetsError(message);
    } finally {
      setLoadingDatasets(false);
    }
  };

  useEffect(() => {
    refreshBaselineInputs();
  }, []);

  const onUploadFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setUploadFile(file);
  };

  const onSubmitValidation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!selectedDatasetId) {
      setSubmitError('Select a baseline dataset before uploading.');
      return;
    }
    if (!uploadFile) {
      setSubmitError('Choose a CSV file to run the live validation.');
      return;
    }

    try {
      setSubmitting(true);
      setSubmitError(null);
      showToast('Validating uploaded dataset against selected baseline...', 'running', 2500);

      const payload = await dashboardApi.validateUploadedDataset({
        file: uploadFile,
        baselineDatasetId: selectedDatasetId,
        datasetName: datasetAlias || selectedDataset?.dataset_name,
        ingestToBronze,
      });

      setResult(payload);
      showToast(payload.status_message, payload.drift_detected ? 'running' : 'success', 3500);

      if (onOperationFinished) {
        await onOperationFinished();
      }
      await refreshBaselineInputs();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Live validation failed.';
      setSubmitError(message);
      showToast(message, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // Use live metrics from upload result if available, otherwise use summary
  const liveBronzeCount = result?.after_metrics?.bronze_files_count ?? summary.overview.metrics.bronze_files_count;
  const liveDriftAlerts = result?.after_metrics?.active_drift_alerts ?? summary.overview.metrics.active_drift_alerts;
  const liveQualityScore = result?.after_metrics?.data_quality_score ?? summary.overview.metrics.data_quality_score;

  return (
    <div className="grid-12 animate-fade page-grid">
      <div className="span-4">
        <MetricCard
          label="Live Bronze Files"
          value={liveBronzeCount.toLocaleString()}
          hint={result ? 'Updated after upload' : 'Current count'}
        />
      </div>
      <div className="span-4">
        <MetricCard
          label="Live Drift Alerts"
          value={liveDriftAlerts.toLocaleString()}
          hint={result ? 'Updated after upload' : 'Pending schema issues'}
          tone={liveDriftAlerts > 0 ? 'warning' : 'positive'}
        />
      </div>
      <div className="span-4">
        <MetricCard
          label="Live Data Quality"
          value={pct(liveQualityScore)}
          hint={result ? 'Updated after upload' : `Pipeline ${summary.actions.pipeline_status}`}
        />
      </div>

      <div className="span-12">
        <Panel title="Step 1: Baseline Input Snapshot" subtitle="Show existing input schema before the live upload test.">
          {loadingDatasets && <div className="loading-row"><span className="spinner" />Loading baseline inputs...</div>}
          {datasetsError && <div className="status-banner error">{datasetsError}</div>}

          {!loadingDatasets && !datasetsError && (
            <div className="live-validation-grid">
              <div className="live-validation-column">
                <label htmlFor="baseline-dataset" className="field-label">
                  Baseline dataset
                </label>
                <select
                  id="baseline-dataset"
                  value={selectedDatasetId}
                  onChange={(event) => setSelectedDatasetId(event.target.value)}
                  className="field-input"
                >
                  {datasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {dataset.dataset_name} ({dataset.source_layer})
                    </option>
                  ))}
                </select>

                {selectedDataset && (
                  <div className="live-dataset-meta">
                    <div><strong>Path:</strong> {selectedDataset.path}</div>
                    <div><strong>Rows:</strong> {selectedDataset.row_count_estimate.toLocaleString()}</div>
                    <div><strong>Size:</strong> {formatBytes(selectedDataset.size_bytes)}</div>
                    <div><strong>Updated:</strong> {compactDateTime(selectedDataset.last_modified)}</div>
                  </div>
                )}
              </div>

              <div className="live-validation-column">
                <div className="panel-subtitle">Schema Columns ({selectedDataset?.schema.length || 0})</div>
                <div className="table-scroll table-scroll-short">
                  <table className="data-table compact">
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedDataset?.schema || []).map((col) => (
                        <tr key={col.column}>
                          <td>{col.column}</td>
                          <td>{col.dtype}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {selectedDataset && (
            <div className="preview-block">
              <div className="panel-subtitle">Baseline Data Preview (first rows)</div>
              {renderDataPreview(selectedDataset.sample_rows, 'No sample rows available for baseline dataset.')}
            </div>
          )}
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Step 2: Upload New Dataset" subtitle="Run live schema drift detection during the demo.">
          <form onSubmit={onSubmitValidation} className="upload-form">
            <div className="upload-row">
              <div className="field-group grow">
                <label htmlFor="dataset-alias" className="field-label">Dataset name for event logs</label>
                <input
                  id="dataset-alias"
                  className="field-input"
                  placeholder="Optional (e.g., transactions_live_case)"
                  value={datasetAlias}
                  onChange={(event) => setDatasetAlias(event.target.value)}
                />
              </div>
              <div className="field-group grow">
                <label htmlFor="upload-csv" className="field-label">Upload CSV</label>
                <input id="upload-csv" type="file" accept=".csv" className="field-input" onChange={onUploadFileChange} />
              </div>
            </div>

            <label className="checkbox-row" htmlFor="ingest-checkbox">
              <input
                id="ingest-checkbox"
                type="checkbox"
                checked={ingestToBronze}
                onChange={(event) => setIngestToBronze(event.target.checked)}
              />
              Ingest uploaded file to Bronze so all dashboard analytics update live
            </label>

            <div className="upload-actions">
              <button type="submit" className="action-button" disabled={submitting || !uploadFile || !selectedDatasetId}>
                {submitting ? 'Running live validation...' : 'Validate Upload and Refresh Analytics'}
              </button>
              {uploadFile && (
                <span className="muted">
                  Selected file: <strong>{uploadFile.name}</strong> ({formatBytes(uploadFile.size)})
                </span>
              )}
            </div>
          </form>

          {submitError && <div className="status-banner error">{submitError}</div>}
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Step 3: Drift Result and Before/After Comparison" subtitle="Use this section to explain schema changes and live metric deltas.">
          {!result && <div className="muted">Run one upload test to see schema drift output and metric comparison.</div>}

          {result && (
            <div className="result-stack">
              <div className={`status-banner ${result.drift_detected ? 'warning' : 'success'}`}>
                <strong>{result.drift_detected ? 'Schema Drift Detected' : 'No Schema Drift'}</strong>
                <span>{result.status_message}</span>
              </div>

              <div className="drift-count-row">
                <span>New: {result.drift_counts.new || 0}</span>
                <span>Missing: {result.drift_counts.missing || 0}</span>
                <span>Type changes: {result.drift_counts.dtype || 0}</span>
                <span>Renames: {result.drift_counts.renames || 0}</span>
                <span>Risk: {result.risk_level}</span>
              </div>

              <div className="table-scroll">
                <table className="data-table compact">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Before Upload</th>
                      <th>After Upload</th>
                      <th>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultMetricRows.map((row) => (
                      <tr key={row.label}>
                        <td>{row.label}</td>
                        <td>{row.before.toLocaleString()}</td>
                        <td>{row.after.toLocaleString()}</td>
                        <td>{row.delta}</td>
                      </tr>
                    ))}
                    <tr>
                      <td>Pipeline Status</td>
                      <td>{result.before_metrics.pipeline_status}</td>
                      <td>{result.after_metrics.pipeline_status}</td>
                      <td>n/a</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {result.event_id && (
                <div className="muted">
                  Drift event logged for approvals: <code>{result.event_id}</code>
                </div>
              )}

              {result.ingestion.local_path && (
                <div className="muted">
                  Uploaded dataset stored at: <code>{result.ingestion.local_path}</code>
                </div>
              )}

              {result.ingestion.azure_blob_path && (
                <div className="muted">
                  Azure mirror path: <code>{result.ingestion.azure_blob_path}</code>
                </div>
              )}

              {result.ingestion.azure_upload_error && (
                <div className="status-banner warning">
                  Azure upload warning: {result.ingestion.azure_upload_error}
                </div>
              )}

              <div className="live-validation-grid">
                <div className="live-validation-column">
                  <div className="panel-subtitle">Detected Drift Details</div>
                  <div className="drift-list-block">
                    <div><strong>New columns:</strong> {(result.diff.new_columns || []).join(', ') || 'None'}</div>
                    <div><strong>Missing columns:</strong> {(result.diff.missing_columns || []).join(', ') || 'None'}</div>
                    <div>
                      <strong>Dtype changes:</strong>
                      <ul className="flat-list">
                        {(result.diff.dtype_changes || []).length === 0 && <li>None</li>}
                        {(result.diff.dtype_changes || []).map((item) => (
                          <li key={item.column}>{item.column}: {item.expected}{' -> '}{item.actual}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <strong>Renames:</strong>
                      <ul className="flat-list">
                        {(result.diff.renames || []).length === 0 && <li>None</li>}
                        {(result.diff.renames || []).map((item) => (
                          <li key={`${item.old_name}-${item.new_name}`}>
                            {item.old_name}{' -> '}{item.new_name} ({(item.similarity * 100).toFixed(0)}% similarity)
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>

                <div className="live-validation-column">
                  <div className="panel-subtitle">Uploaded Data Preview (first rows)</div>
                  {renderDataPreview(result.uploaded_preview, 'No rows available in uploaded preview.')}
                </div>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
