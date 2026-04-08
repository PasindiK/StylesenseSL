import { useMemo, useState } from 'react';
import * as dashboardApi from '../api/dashboardApi';
import { MetricCard } from '../cards/MetricCard';
import { useToast } from '../notifications/ToastProvider';
import { Panel } from '../panels/Panel';

interface ActionLog {
  timestamp: string;
  action: string;
  status: 'success' | 'error' | 'running';
  details: string;
}

interface ActionsPageProps {
  pipelineStatus: string;
  stakeholderViewCount: number;
  onOperationFinished: () => void | Promise<void>;
}

interface ActionDefinition {
  id: string;
  label: string;
  execute: () => Promise<{ status: string; message: string; result: Record<string, unknown> }>;
}

export function ActionsPage({ pipelineStatus, stakeholderViewCount, onOperationFinished }: ActionsPageProps) {
  const { showToast } = useToast();
  const [runningActionId, setRunningActionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<ActionLog[]>([]);

  const actions = useMemo<ActionDefinition[]>(
    () => [
      {
        id: 'kafka-ingestion',
        label: 'Run Kafka Ingestion',
        execute: dashboardApi.runKafkaIngestion,
      },
      {
        id: 'bronze-silver',
        label: 'Run Bronze -> Silver Transformation',
        execute: dashboardApi.runBronzeToSilver,
      },
      {
        id: 'silver-gold',
        label: 'Run Silver -> Gold Transformation',
        execute: dashboardApi.runSilverToGold,
      },
      {
        id: 'dq-checks',
        label: 'Run Data Quality Checks',
        execute: dashboardApi.runDataQualityChecks,
      },
      {
        id: 'stakeholder-views',
        label: 'Generate Stakeholder Views',
        execute: dashboardApi.runStakeholderViews,
      },
    ],
    [],
  );

  const appendLog = (log: ActionLog) => {
    setLogs((current) => [log, ...current].slice(0, 60));
  };

  const handleAction = async (action: ActionDefinition) => {
    setRunningActionId(action.id);
    appendLog({
      timestamp: new Date().toISOString(),
      action: action.label,
      status: 'running',
      details: 'Operation submitted to backend',
    });
    showToast(`${action.label} is running...`, 'running', 1800);

    try {
      const response = await action.execute();
      appendLog({
        timestamp: new Date().toISOString(),
        action: action.label,
        status: 'success',
        details: response.message,
      });
      showToast(response.message, 'success');
      await onOperationFinished();
    } catch (err) {
      const message = err instanceof Error ? err.message : `${action.label} failed.`;
      appendLog({
        timestamp: new Date().toISOString(),
        action: action.label,
        status: 'error',
        details: message,
      });
      showToast(message, 'error');
    } finally {
      setRunningActionId(null);
    }
  };

  return (
    <div className="grid-12 animate-fade">
      <div className="span-12">
        <div className="metric-grid three">
          <MetricCard label="Pipeline Status" value={pipelineStatus} tone={pipelineStatus === 'Running' ? 'positive' : 'warning'} />
          <MetricCard label="Available Actions" value={actions.length} />
          <MetricCard label="Stakeholder Views Generated" value={stakeholderViewCount} />
        </div>
      </div>

      <div className="span-7">
        <Panel title="Pipeline Controls" subtitle="Run live backend operations">
          <div className="actions-grid">
            {actions.map((action) => (
              <button
                key={action.id}
                type="button"
                className="action-button"
                disabled={Boolean(runningActionId)}
                onClick={() => handleAction(action)}
              >
                <span>{action.label}</span>
                <strong>{runningActionId === action.id ? 'Running...' : 'Execute'}</strong>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      <div className="span-5">
        <Panel title="Pipeline Status Indicators" subtitle="Operational control posture">
          <div className="status-indicator-list">
            <div className="status-indicator">
              <span>Kafka Ingestion</span>
              <strong className={pipelineStatus === 'Running' ? 'tone-positive' : 'tone-warning'}>{pipelineStatus}</strong>
            </div>
            <div className="status-indicator">
              <span>Bronze → Silver</span>
              <strong className="tone-positive">Available</strong>
            </div>
            <div className="status-indicator">
              <span>Silver → Gold</span>
              <strong className="tone-positive">Available</strong>
            </div>
            <div className="status-indicator">
              <span>Data Quality Checks</span>
              <strong className="tone-positive">Available</strong>
            </div>
            <div className="status-indicator">
              <span>Stakeholder View Generation</span>
              <strong className="tone-positive">Available</strong>
            </div>
          </div>
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Execution Logs" subtitle="Latest operation traces">
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Operation</th>
                  <th>Status</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={4}>No operations executed yet.</td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={`${log.timestamp}-${log.action}-${log.status}`}>
                      <td>{new Date(log.timestamp).toLocaleString()}</td>
                      <td>{log.action}</td>
                      <td className={`log-status-${log.status}`}>{log.status}</td>
                      <td>{log.details}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
