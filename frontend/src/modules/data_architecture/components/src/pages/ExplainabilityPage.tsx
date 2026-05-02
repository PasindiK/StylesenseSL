import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useEffect, useState } from 'react';
import * as dashboardApi from '../api/dashboardApi';
import { MetricCard } from '../cards/MetricCard';
import { Panel } from '../panels/Panel';
import type { DashboardSummaryResponse, SchemaVersionTableGroup, SchemaVersion } from '../types';
import { pct } from '../utils/formatters';

interface ExplainabilityPageProps {
  summary: DashboardSummaryResponse;
}

export function ExplainabilityPage({ summary }: ExplainabilityPageProps) {
  const explainability = summary.explainability;
  const [schemaVersions, setSchemaVersions] = useState<SchemaVersionTableGroup[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(true);
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [rollbackInProgressVersion, setRollbackInProgressVersion] = useState<number | null>(null);
  const [rollbackStatusMessage, setRollbackStatusMessage] = useState<string | null>(null);

  const featureRows = explainability.feature_importance.flatMap((entry) =>
    entry.features.map((feature) => ({
      action: entry.action,
      feature: feature.name,
      weight: feature.weight,
    })),
  );

  const loadSchemaVersions = async (preferredTable?: string) => {
    try {
      setLoadingVersions(true);
      const response = await dashboardApi.getSchemaVersions();
      const tables = response.tables || [];
      setSchemaVersions(tables);

      const nextSelectedTable =
        (preferredTable && tables.find((entry) => entry.table === preferredTable)?.table) ||
        (selectedTable && tables.find((entry) => entry.table === selectedTable)?.table) ||
        (tables[0]?.table || '');

      setSelectedTable(nextSelectedTable);
    } catch (error) {
      console.error('Failed to load schema versions:', error);
      setRollbackStatusMessage('Failed to load schema versions.');
    } finally {
      setLoadingVersions(false);
    }
  };

  useEffect(() => {
    void loadSchemaVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currentTableVersions = schemaVersions.find((t) => t.table === selectedTable);
  const latestVersion = currentTableVersions?.latest_version;
  const currentBaselineVersion = currentTableVersions?.active_baseline_version ?? latestVersion?.version;
  const currentSchema = currentTableVersions?.current_schema || [];
  const tableLabelMap: Record<string, string> = {
    users: 'Users',
    products: 'Products',
    transactions: 'Transactions',
    shops: 'Shops',
    trends: 'Trends',
  };

  const handleRollbackToVersion = async (targetVersion: number) => {
    if (!selectedTable) {
      return;
    }

    try {
      setRollbackStatusMessage(null);
      setRollbackInProgressVersion(targetVersion);
      await dashboardApi.rollbackSchemaVersion(selectedTable, targetVersion);
      await loadSchemaVersions(selectedTable);
      setRollbackStatusMessage(
        `Baseline for ${tableLabelMap[selectedTable] || selectedTable} rolled back to version ${targetVersion}.`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Schema rollback failed';
      setRollbackStatusMessage(`Rollback failed: ${message}`);
    } finally {
      setRollbackInProgressVersion(null);
    }
  };

  return (
    <div className="grid-12 animate-fade">
      <div className="span-12">
        <div className="metric-grid four">
          <MetricCard
            label="Training Dataset Size"
            value={explainability.ml_dataset_metrics.training_dataset_size.toLocaleString()}
          />
          <MetricCard label="Feature Count" value={explainability.ml_dataset_metrics.feature_count.toLocaleString()} />
          <MetricCard
            label="Embedding Vectors Generated"
            value={explainability.ml_dataset_metrics.embedding_vectors_generated.toLocaleString()}
          />
          <MetricCard
            label="Model Accuracy"
            value={pct(explainability.ml_dataset_metrics.model_accuracy)}
            tone={explainability.ml_dataset_metrics.model_accuracy >= 80 ? 'positive' : 'warning'}
          />
        </div>
      </div>

      <div className="span-12">
        <Panel title="Schema Versioning" subtitle="Current schema and approval history">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', minHeight: '400px' }}>
            {/* Current Schema Panel */}
            <div style={{ borderRight: '1px solid #e5e7eb', paddingRight: '20px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: '#111827' }}>
                Baseline Schema (Current)
              </h3>
              <div style={{ marginBottom: '16px' }}>
                <label
                  style={{ fontSize: '14px', fontWeight: 500, marginBottom: '8px', display: 'block', color: '#374151' }}
                >
                  Select Table:
                </label>
                <select
                  value={selectedTable}
                  onChange={(e) => {
                    setSelectedTable(e.target.value);
                    setRollbackStatusMessage(null);
                  }}
                  style={{
                    width: '100%',
                    height: '40px',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    fontSize: '14px',
                    backgroundColor: 'white',
                    color: '#111827',
                    fontWeight: 600,
                  }}
                >
                  {schemaVersions.length === 0 && <option value="">No tables available</option>}
                  {schemaVersions.map((table) => (
                    <option key={table.table} value={table.table}>
                      {tableLabelMap[table.table] || table.table} ({table.version_count} versions)
                    </option>
                  ))}
                </select>
              </div>
              {loadingVersions ? (
                <div style={{ color: '#6b7280', padding: '20px', textAlign: 'center' }}>Loading schema...</div>
              ) : currentTableVersions ? (
                <div>
                  <div
                    style={{
                      marginBottom: '12px',
                      padding: '12px',
                      backgroundColor: '#f3f4f6',
                      borderRadius: '6px',
                      border: '1px solid #e5e7eb',
                    }}
                  >
                    <div style={{ fontSize: '13px', color: '#111827', fontWeight: 600, marginBottom: '6px' }}>
                      {tableLabelMap[selectedTable] || selectedTable || 'Selected Table'}
                    </div>
                    <div style={{ fontSize: '12px', color: '#4b5563', marginBottom: '4px' }}>
                      Baseline: {currentTableVersions.baseline_dataset || 'Not linked'}
                    </div>
                    <div style={{ fontSize: '12px', color: '#4b5563' }}>
                      Columns: {currentSchema.length.toLocaleString()} | Active Baseline: V{currentBaselineVersion ?? '-'}
                    </div>
                  </div>
                  <div
                    style={{
                      maxHeight: '260px',
                      overflowY: 'auto',
                      border: '1px solid #e5e7eb',
                      borderRadius: '6px',
                      backgroundColor: '#ffffff',
                    }}
                  >
                    {currentSchema.length > 0 ? (
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                        <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f9fafb' }}>
                          <tr>
                            <th
                              style={{
                                textAlign: 'left',
                                padding: '8px 10px',
                                borderBottom: '1px solid #e5e7eb',
                                color: '#111827',
                                fontWeight: 600,
                              }}
                            >
                              Column
                            </th>
                            <th
                              style={{
                                textAlign: 'left',
                                padding: '8px 10px',
                                borderBottom: '1px solid #e5e7eb',
                                color: '#111827',
                                fontWeight: 600,
                              }}
                            >
                              Type
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {currentSchema.map((columnDef) => (
                            <tr key={`${columnDef.column}:${columnDef.dtype}`}>
                              <td style={{ padding: '8px 10px', borderBottom: '1px solid #f3f4f6', color: '#1f2937' }}>
                                {columnDef.column}
                              </td>
                              <td style={{ padding: '8px 10px', borderBottom: '1px solid #f3f4f6' }}>
                                <span
                                  style={{
                                    display: 'inline-block',
                                    fontSize: '11px',
                                    padding: '2px 8px',
                                    backgroundColor: '#eef2ff',
                                    color: '#3730a3',
                                    borderRadius: '999px',
                                    fontWeight: 600,
                                  }}
                                >
                                  {columnDef.dtype}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div style={{ color: '#6b7280', fontSize: '13px', padding: '14px' }}>
                        Baseline schema is not available for this table yet.
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{ color: '#6b7280', padding: '20px', textAlign: 'center' }}>No schema versions available</div>
              )}
            </div>

            {/* Version History Panel */}
            <div style={{ paddingLeft: '20px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: '#111827' }}>
                Version History
              </h3>
              {rollbackStatusMessage && (
                <div
                  style={{
                    marginBottom: '12px',
                    padding: '10px 12px',
                    borderRadius: '6px',
                    border: '1px solid #d1d5db',
                    backgroundColor: '#f8fafc',
                    color: '#334155',
                    fontSize: '12px',
                  }}
                >
                  {rollbackStatusMessage}
                </div>
              )}
              {loadingVersions ? (
                <div style={{ color: '#6b7280', padding: '20px', textAlign: 'center' }}>Loading history...</div>
              ) : currentTableVersions && currentTableVersions.versions.length > 0 ? (
                <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                  {currentTableVersions.versions.map((version: SchemaVersion) => (
                    <div
                      key={version.version}
                      style={{
                        padding: '12px',
                        marginBottom: '12px',
                        border: '1px solid #e5e7eb',
                        borderRadius: '6px',
                        backgroundColor:
                          version.version === currentBaselineVersion
                            ? '#f0fdf4'
                            : version.is_baseline
                              ? '#f8fafc'
                              : 'white',
                      }}
                    >
                      <div
                        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '8px' }}
                      >
                        <div>
                          <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>
                            Version {version.version}
                            {version.is_baseline && (
                              <span
                                style={{
                                  marginLeft: '8px',
                                  fontSize: '11px',
                                  padding: '2px 8px',
                                  backgroundColor: '#334155',
                                  color: 'white',
                                  borderRadius: '4px',
                                  fontWeight: 500,
                                }}
                              >
                                BASELINE
                              </span>
                            )}
                            {version.version === currentBaselineVersion && (
                              <span
                                style={{
                                  marginLeft: '8px',
                                  fontSize: '11px',
                                  padding: '2px 8px',
                                  backgroundColor: '#10b981',
                                  color: 'white',
                                  borderRadius: '4px',
                                  fontWeight: 500,
                                }}
                              >
                                CURRENT
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                            {new Date(version.approved_at).toLocaleString()}
                          </div>
                        </div>
                        <div
                          style={{
                            fontSize: '11px',
                            padding: '4px 8px',
                            backgroundColor:
                              version.risk_level === 'high'
                                ? '#fee2e2'
                                : version.risk_level === 'medium'
                                  ? '#fef3c7'
                                  : '#dbeafe',
                            color:
                              version.risk_level === 'high'
                                ? '#991b1b'
                                : version.risk_level === 'medium'
                                  ? '#92400e'
                                  : '#1e40af',
                            borderRadius: '4px',
                            fontWeight: 500,
                          }}
                        >
                          {version.risk_level.toUpperCase()}
                        </div>
                      </div>
                      <div style={{ fontSize: '12px', color: '#374151', marginBottom: '6px' }}>
                        <strong>Changes:</strong> +{version.change_summary.new || 0} columns, -
                        {version.change_summary.missing || 0} columns, {version.change_summary.dtype || 0} type changes
                      </div>
                      {version.notes && (
                        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>{version.notes}</div>
                      )}
                      <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px' }}>
                        By {version.approved_by} • {version.source_file}
                      </div>
                      {version.version !== currentBaselineVersion && (
                        <button
                          type="button"
                          onClick={() => handleRollbackToVersion(version.version)}
                          disabled={rollbackInProgressVersion === version.version}
                          style={{
                            fontSize: '12px',
                            padding: '6px 10px',
                            borderRadius: '6px',
                            border: '1px solid #2563eb',
                            backgroundColor: rollbackInProgressVersion === version.version ? '#dbeafe' : '#eff6ff',
                            color: '#1d4ed8',
                            fontWeight: 600,
                            cursor: rollbackInProgressVersion === version.version ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {rollbackInProgressVersion === version.version ? 'Applying...' : 'Set As Baseline'}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: '#6b7280', padding: '20px', textAlign: 'center' }}>No version history available</div>
              )}
            </div>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Feature Importance" subtitle="Primary drivers behind model decisions">
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={featureRows.slice(0, 20)} layout="vertical" margin={{ left: 120 }}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis dataKey="feature" type="category" width={130} />
                <Tooltip />
                <Bar dataKey="weight" fill="#0f766e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Embedding Clusters" subtitle="Product similarity cluster scatter">
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis dataKey="x" type="number" name="Embedding X" />
                <YAxis dataKey="y" type="number" name="Embedding Y" />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                <Scatter data={explainability.embedding_clusters} fill="#0284c7" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Recommendation Explanation" subtitle="Why products were recommended">
          <div className="recommendation-grid">
            {explainability.recommendation_explanations.map((item) => (
              <article key={item.title} className="recommendation-card">
                <h4>{item.title}</h4>
                <p>{item.reason}</p>
                <div className="recommendation-confidence">Confidence: {pct(item.confidence)}</div>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
