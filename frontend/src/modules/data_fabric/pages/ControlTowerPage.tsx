import { useMemo, useState } from 'react'
import {
  Bot,
  Database,
  FileCheck2,
  FileUp,
  FolderSearch,
  GitBranch,
  Link2,
  Radar,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'

type Props = {
  loading: boolean
  overview: any
  selectedRelationshipKey: string
  setSelectedRelationshipKey: (key: string) => void
  selectedRelationship: any
  formatNumber: (value: number) => string
  safeDate: (value?: string) => string
  decisionClass: (decision: string) => string
}

export default function ControlTowerPage({
  loading,
  overview,
  selectedRelationshipKey,
  setSelectedRelationshipKey,
  selectedRelationship,
  formatNumber,
  safeDate,
  decisionClass,
}: Props) {
  const phases: Array<{
    id: string
    title: string
    detail: string
    emoji: string
    icon: LucideIcon
    row: 1 | 2
  }> = [
    {
      id: 'Phase 01',
      title: 'New File Intake',
      detail: 'Upload/path intake with policy-based auto-join',
      emoji: '📤',
      icon: FileUp,
      row: 1,
    },
    {
      id: 'Phase 02',
      title: 'Preprocessing Layer',
      detail: 'Normalization, schema checks, null handling, quality safeguards',
      emoji: '🧹',
      icon: ShieldCheck,
      row: 1,
    },
    {
      id: 'Phase 03',
      title: 'Ingestion Scanner',
      detail: 'Folder scanner + typed file loading pipeline',
      emoji: '🛰️',
      icon: FolderSearch,
      row: 1,
    },
    {
      id: 'Phase 04',
      title: 'Metadata Catalog',
      detail: 'Dataset assets, schema, inferred relations, lineage persistence',
      emoji: '🗂️',
      icon: Database,
      row: 1,
    },
    {
      id: 'Phase 05',
      title: 'Relationship Discovery',
      detail: 'Structural, statistical, behavioral feature extraction',
      emoji: '🧠',
      icon: Radar,
      row: 1,
    },
    {
      id: 'Phase 06',
      title: 'Scoring Engine',
      detail: 'LR/RF ensemble + fallback confidence decisions',
      emoji: '🤖',
      icon: Bot,
      row: 2,
    },
    {
      id: 'Phase 07',
      title: 'Join Executor',
      detail: 'Auto-join or manual intervention selection flow',
      emoji: '🧩',
      icon: Link2,
      row: 2,
    },
    {
      id: 'Phase 08',
      title: 'Autonomous Agent',
      detail: 'Usage logging, drift checks, behavioral updates',
      emoji: '⚙️',
      icon: Bot,
      row: 2,
    },
    {
      id: 'Phase 09',
      title: 'Lineage & Ops Logs',
      detail: 'Graph impact + operational event tracking',
      emoji: '📈',
      icon: GitBranch,
      row: 2,
    },
  ]

  const topRow = phases.filter((phase) => phase.row === 1)
  const bottomRow = phases.filter((phase) => phase.row === 2)

  const [activeLayerId, setActiveLayerId] = useState<string>('Phase 04')
  const activeLayer = useMemo(
    () => phases.find((phase) => phase.id === activeLayerId) ?? phases[0],
    [activeLayerId]
  )

  if (!overview) {
    return (
      <section className="df-tab-content">
        <article className="glass-card df-state-card">
          <h3>{loading ? 'Loading Data Fabric Overview...' : 'No Overview Data Loaded Yet'}</h3>
          <p className="muted-text">
            {loading
              ? 'Fetching datasets, relationships, lineage, and logs from backend...'
              : 'Use "Refresh Live Data" to fetch latest metadata from backend.'}
          </p>
        </article>
      </section>
    )
  }

  return (
    <section className="df-tab-content">
      <article className="glass-card phase-visual-card">
        <h3>Architecture Picture</h3>

        <div className="architecture-flow-board" aria-label="Data Fabric architecture flow">
          <div className="architecture-row" role="list" aria-label="Data Fabric flow row 1">
            {topRow.map((phase, index) => {
              const Icon = phase.icon
              return (
                <div key={phase.id} className="flow-step-wrap" role="listitem">
                  <button
                    type="button"
                    className={`phase-node architecture-node ${activeLayerId === phase.id ? 'active' : ''}`}
                    onClick={() => setActiveLayerId(phase.id)}
                  >
                    <span className="phase-id">{phase.id}</span>
                    <span className="phase-emoji" aria-hidden="true">{phase.emoji}</span>
                    <span className="phase-icon-wrap">
                      <Icon size={24} strokeWidth={2.2} />
                    </span>
                    <strong>{phase.title}</strong>
                    <p>{phase.detail}</p>
                  </button>
                  {index < topRow.length - 1 ? <span className="flow-arrow" aria-hidden="true">→</span> : null}
                </div>
              )
            })}
          </div>

          <div className="flow-drop-zone" aria-hidden="true">
            <span className="flow-down">↓</span>
          </div>

          <div className="architecture-row" role="list" aria-label="Data Fabric flow row 2">
            {bottomRow.map((phase, index) => {
              const Icon = phase.icon
              return (
                <div key={phase.id} className="flow-step-wrap" role="listitem">
                  <button
                    type="button"
                    className={`phase-node architecture-node ${activeLayerId === phase.id ? 'active' : ''}`}
                    onClick={() => setActiveLayerId(phase.id)}
                  >
                    <span className="phase-id">{phase.id}</span>
                    <span className="phase-emoji" aria-hidden="true">{phase.emoji}</span>
                    <span className="phase-icon-wrap">
                      <Icon size={24} strokeWidth={2.2} />
                    </span>
                    <strong>{phase.title}</strong>
                    <p>{phase.detail}</p>
                  </button>
                  {index < bottomRow.length - 1 ? <span className="flow-arrow" aria-hidden="true">→</span> : null}
                </div>
              )
            })}
          </div>
        </div>

        <div className="architecture-legend" aria-label="Flow legend">
          <span><FileCheck2 size={14} /> Validation + Quality</span>
          <span><Database size={14} /> Metadata + Catalog</span>
          <span><Bot size={14} /> Intelligence + Automation</span>
        </div>

      </article>

      <div className="df-kpi-grid">
        <article className="glass-card kpi-card">
          <span>Datasets</span>
          <strong>{formatNumber(overview.kpis.dataset_count)}</strong>
        </article>
        <article className="glass-card kpi-card">
          <span>Relationships</span>
          <strong>{formatNumber(overview.kpis.relationship_count)}</strong>
        </article>
        <article className="glass-card kpi-card">
          <span>Strong / Probable / Weak</span>
          <strong>
            {overview.kpis.strong_count} / {overview.kpis.probable_count} / {overview.kpis.weak_count}
          </strong>
        </article>
        <article className="glass-card kpi-card">
          <span>Unstable Relationships</span>
          <strong>{formatNumber(overview.kpis.unstable_count)}</strong>
        </article>
        <article className="glass-card kpi-card">
          <span>Model Version</span>
          <strong>{overview.model.model_version}</strong>
          <p className="muted-text">
            {overview.model.ensemble_ready
              ? `Ensemble ready: LR + ${overview.model.secondary_model_label || 'RF'}`
              : 'Static fallback active'}
          </p>
          <p className="muted-text">{overview.model.ensemble_reason || 'No model readiness details available.'}</p>
        </article>
        <article className="glass-card kpi-card">
          <span>Last Refreshed</span>
          <strong>{safeDate(overview.last_refreshed)}</strong>
        </article>
      </div>

      <div className="df-main-grid">
        <article className="glass-card">
          <h3>Dataset Manager</h3>
          <div className="df-table-wrap">
            <table className="df-table">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Rows</th>
                  <th>Columns</th>
                  <th>Domain</th>
                  <th>Quality</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {overview.datasets.map((row: any) => (
                  <tr key={row.dataset_name}>
                    <td>{row.dataset_name}</td>
                    <td>{formatNumber(row.row_count)}</td>
                    <td>{formatNumber(row.column_count)}</td>
                    <td>{row.domain}</td>
                    <td>{row.quality_score.toFixed(2)}</td>
                    <td>{safeDate(row.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="glass-card">
          <h3>Relationship Discovery</h3>
          <div className="df-table-wrap">
            <table className="df-table">
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Join Columns</th>
                  <th>Confidence</th>
                  <th>Decision</th>
                  <th>Cardinality</th>
                </tr>
              </thead>
              <tbody>
                {overview.relationships.map((row: any) => (
                  <tr
                    key={row.relationship_key}
                    className={selectedRelationshipKey === row.relationship_key ? 'selected-row' : ''}
                    onClick={() => setSelectedRelationshipKey(row.relationship_key)}
                  >
                    <td>
                      {row.left_dataset} {'->'} {row.right_dataset}
                    </td>
                    <td>
                      {row.left_column} {'->'} {row.right_column}
                    </td>
                    <td>{row.confidence.toFixed(3)}</td>
                    <td>
                      <span className={`df-decision ${decisionClass(row.decision)}`}>{row.decision}</span>
                    </td>
                    <td>{row.cardinality}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

      </div>
    </section>
  )
}
