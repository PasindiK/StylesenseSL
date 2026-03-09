import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { DashboardSummaryResponse, LayerId, MedallionFilesResponse } from '../types';
import { MetricCard } from '../cards/MetricCard';
import { GaugeChart } from '../charts/GaugeChart';
import { Panel } from '../panels/Panel';
import { formatBytes } from '../utils/formatters';

interface MedallionPageProps {
  summary: DashboardSummaryResponse;
  medallionFiles: Partial<Record<LayerId, MedallionFilesResponse>>;
  loading: boolean;
}

export function MedallionPage({ summary, medallionFiles, loading }: MedallionPageProps) {
  const medallion = summary.medallion;

  const fileRows = [
    ...(medallionFiles.bronze?.files || []),
    ...(medallionFiles.silver?.files || []),
    ...(medallionFiles.gold?.files || []),
  ].slice(0, 30);

  return (
    <div className="grid-12 animate-fade">
      <div className="span-12">
        <div className="metric-grid three">
          <MetricCard label="Bronze Records" value={medallion.metrics.bronze_records.toLocaleString()} />
          <MetricCard label="Silver Records" value={medallion.metrics.silver_records.toLocaleString()} />
          <MetricCard label="Gold Records" value={medallion.metrics.gold_records.toLocaleString()} />
        </div>
      </div>

      <div className="span-8">
        <Panel title="Layer Comparison" subtitle="Record distribution across medallion layers">
          <div className="chart-box medium">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={medallion.layer_comparison}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis dataKey="layer" />
                <YAxis />
                <Tooltip formatter={(val: number | undefined) => val ? val.toLocaleString() : 'N/A'} />
                <Bar dataKey="records" fill="#0f766e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-4">
        <Panel title="Transformation Success Rate" subtitle="Bronze -> Silver -> Gold reliability">
          <GaugeChart value={medallion.transformation_success_rate} label="Pipeline Success" />
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Dataset Explorer" subtitle="Latest Bronze files, Silver datasets, Gold tables">
          {loading ? (
            <div className="loading-row">
              <span className="spinner" />
              <span>Loading medallion file metadata...</span>
            </div>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Layer</th>
                    <th>Dataset</th>
                    <th>Path</th>
                    <th>Records</th>
                    <th>Size</th>
                    <th>Last Modified</th>
                    <th>Tier</th>
                  </tr>
                </thead>
                <tbody>
                  {fileRows.length === 0 ? (
                    <tr>
                      <td colSpan={7}>No datasets detected yet.</td>
                    </tr>
                  ) : (
                    fileRows.map((item) => (
                      <tr key={`${item.layer}-${item.path}`}>
                        <td>{item.layer}</td>
                        <td>{item.dataset_name}</td>
                        <td>{item.path}</td>
                        <td>{item.records.toLocaleString()}</td>
                        <td>{formatBytes(item.size_bytes)}</td>
                        <td>{new Date(item.last_modified).toLocaleString()}</td>
                        <td>{item.access_tier}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
