import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import './DataFabricTestingPage.css'
import ControlTowerPage from '../pages/ControlTowerPage'
import AgentMonitorPage from '../pages/AgentMonitorPage'
import JoinStudioPage from '../pages/JoinStudioPage'
import LineageGraphPage from '../pages/LineageGraphPage'
import OpsLogsPage from '../pages/OpsLogsPage'
import BehavioralSignalsPage from '../pages/BehavioralSignalsPage'

type TabKey = 'overview' | 'agent' | 'behavior' | 'join' | 'lineage' | 'logs'

type DatasetRow = {
  dataset_name: string
  row_count: number
  column_count: number
  domain: string
  quality_score: number
  updated_at: string
  usage_count: number
  location: string
}

type RelationshipRow = {
  relationship_key: string
  left_dataset: string
  right_dataset: string
  left_column: string
  right_column: string
  confidence: number
  decision: string
  cardinality: string
  model_version: string
  feature_vector_version: string
  feature_vector: Record<string, unknown>
  is_unstable: boolean
  drift_score: number
  join_usage_count: number
  last_scored_at?: string
  last_used_at?: string
  history_points: number
}

type OverviewResponse = {
  kpis: {
    dataset_count: number
    relationship_count: number
    strong_count: number
    probable_count: number
    weak_count: number
    unstable_count: number
  }
  model: {
    model_mode: string
    model_version: string
    feature_vector_version: string
    ensemble_ready?: boolean
    ensemble_reason?: string
    lr_loaded?: boolean
    secondary_model_loaded?: boolean
    secondary_model_label?: string
    lr_weight?: number
    secondary_weight?: number
    test_metrics?: {
      weights?: { lr?: number; secondary?: number }
      accuracy?: { lr?: number; rf?: number; ensemble?: number }
      f1?: { lr?: number; rf?: number; ensemble?: number }
      precision?: { lr?: number; rf?: number; ensemble?: number }
      recall?: { lr?: number; rf?: number; ensemble?: number }
      roc_auc?: { lr?: number; rf?: number; ensemble?: number }
      test_set?: { size?: number; positives?: number; negatives?: number; threshold?: number }
      source?: string
    }
  }
  datasets: DatasetRow[]
  relationships: RelationshipRow[]
  metrics: Record<string, unknown>
  last_refreshed: string
}

type JoinOptionsResponse = {
  left_dataset: string
  right_dataset: string
  mode: 'no_relationship' | 'manual_required_multiple' | 'manual_required_weak' | 'auto_ready'
  suggestions: RelationshipRow[]
}

type JoinExecuteResponse = {
  success: boolean
  manual_intervention_required: boolean
  reason?: string
  suggestions?: Array<{
    relationship_key: string
    left_column: string
    right_column: string
    confidence: number
    decision: string
    cardinality: string
    model_version: string
  }>
  relationship?: RelationshipRow
  row_count?: number
  columns?: string[]
  preview?: Array<Record<string, unknown>>
  usage_updates?: number
}

type LineageResponse = {
  nodes: Array<{ id: string; label: string; domain: string; quality_score: number }>
  edges: Array<{ source: string; target: string }>
  merge_candidates?: Array<{
    left_dataset: string
    right_dataset: string
    best_confidence: number
    best_decision: string
    relationship_key: string
    reason?: string
    signals?: {
      name_similarity?: number
      overlap_ratio?: number
      type_score?: number
      confidence_source?: string
    }
  }>
}

type LogsResponse = {
  events: Array<{
    timestamp?: string
    event: string
    dataset_pair: string
    relationship_key: string
    confidence: number
    base_confidence?: number
    behavior_adjusted_delta?: number
    decision: string
    delta_confidence?: number
    cold_start?: boolean
    feedback?: string
    drift_score?: number
    join_frequency_score?: number
    co_query_frequency_score?: number
    lineage_proximity_score?: number
    stability_score?: number
    model_version?: string
    join_usage_count?: number
    outcome?: string
  }>
}

type BehavioralSignalRow = {
  relationship_key: string
  left_dataset: string
  right_dataset: string
  left_column: string
  right_column: string
  decision: string
  confidence: number
  before_confidence?: number | null
  delta?: number | null
  confidence_source?: string
  models_used?: Record<string, number>
  prior_score_available?: boolean
  history_points: number
  join_usage_count: number
  relationship_stability: number
  behavioral_score: number
  is_unstable: boolean
  drift_score: number
  last_scored_at?: string
  last_used_at?: string
  behavioral_updated_at?: string
  feedback_applied: boolean
}

type BehavioralSignalsResponse = {
  summary: {
    total_relationships: number
    feedback_applied_count: number
    usage_tracked_count: number
    unstable_count: number
    avg_stability: number
    feedback_ratio: number
    feedback_mode: string
    feedback_enabled: boolean
  }
  signals: BehavioralSignalRow[]
  generated_at: string
}

type IntakeResponse = {
  status: string
  dataset_name?: string
  good_match_count?: number
  bad_match_count?: number
  why_joined?: string
  why_not_auto_joined?: string
  selected_relationship?: RelationshipRow
  selected_signals?: Record<string, Record<string, unknown>>
  join_rows?: number
  join_preview?: Array<Record<string, unknown>>
  suggestions?: Array<
    RelationshipRow & {
      signals?: Record<string, Record<string, unknown>>
      explanation?: string
    }
  >
  agent_updates?: {
    usage_updates?: number
    behavioral_updates?: number
    drift_flags?: number
  }
}

type IntakeStepStatus = 'pending' | 'running' | 'completed'

type IntakeStep = {
  label: string
  status: IntakeStepStatus
}

type IntakeProcessingStats = {
  datasetsProcessed: number
  columnPairsEvaluated: number
  featureVectorsBuilt: number
  relationshipsDetected: number
  mlProcessed: number
  mlTotal: number
  averageConfidence: number
  strongCount: number
  probableCount: number
  weakCount: number
  joinUsageSignals: number
  coQuerySignals: number
  lineageSignals: number
}

const EMPTY_INTAKE_STATS: IntakeProcessingStats = {
  datasetsProcessed: 0,
  columnPairsEvaluated: 0,
  featureVectorsBuilt: 0,
  relationshipsDetected: 0,
  mlProcessed: 0,
  mlTotal: 0,
  averageConfidence: 0,
  strongCount: 0,
  probableCount: 0,
  weakCount: 0,
  joinUsageSignals: 0,
  coQuerySignals: 0,
  lineageSignals: 0,
}

const TAB_ROUTE: Record<TabKey, string> = {
  overview: 'control-tower',
  agent: 'agent-monitor',
  behavior: 'behavioral-signals',
  join: 'join-studio',
  lineage: 'lineage-graph',
  logs: 'ops-logs',
}

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: 'Control Tower' },
  { key: 'agent', label: 'Agent Monitor' },
  { key: 'behavior', label: 'Behavioral Signals' },
  { key: 'join', label: 'Join Studio' },
  { key: 'lineage', label: 'Lineage Graph' },
  { key: 'logs', label: 'Ops Logs' },
]

const API_BASE =
  (typeof import.meta !== 'undefined' &&
    ((import.meta.env.VITE_API_URL as string) ||
      (import.meta.env.VITE_DATA_FABRIC_API_URL as string))) ||
  'http://127.0.0.1:8002/api'

  const DEFAULT_MAX_REFERENCE_DATASETS = 5

function tabFromHash(hash: string): TabKey | null {
  const normalized = hash.replace(/^#/, '').trim().toLowerCase()
  const hit = (Object.entries(TAB_ROUTE) as Array<[TabKey, string]>).find(
    ([, route]) => normalized === `data-fabric/${route}`
  )
  return hit ? hit[0] : null
}

function routeForTab(tab: TabKey): string {
  return `#data-fabric/${TAB_ROUTE[tab]}`
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`
  try {
    const res = await fetch(url, init)
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`${path} failed (${res.status})${text ? `: ${text}` : ''}`)
    }
    return (await res.json()) as T
  } catch (err) {
    if (err instanceof Error) {
      throw new Error(`${path} request error via ${API_BASE}: ${err.message}`)
    }
    throw new Error(`${path} request error via ${API_BASE}`)
  }
}

function decisionClass(decision: string): string {
  const normalized = decision.toLowerCase()
  if (normalized === 'strong') return 'decision-strong'
  if (normalized === 'probable') return 'decision-probable'
  return 'decision-weak'
}

function formatNumber(value: number): string {
  return Intl.NumberFormat().format(Number.isFinite(value) ? value : 0)
}

function safeDate(value?: string): string {
  if (!value) return 'N/A'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export default function DataFabricTestingPage() {
  const [activeTab, setActiveTab] = useState<TabKey>(() => tabFromHash(window.location.hash) || 'overview')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  const [overview, setOverview] = useState<OverviewResponse | null>(null)
  const [lineage, setLineage] = useState<LineageResponse | null>(null)
  const [logs, setLogs] = useState<LogsResponse | null>(null)
  const [behavioralSignals, setBehavioralSignals] = useState<BehavioralSignalsResponse | null>(null)

  const [selectedRelationshipKey, setSelectedRelationshipKey] = useState<string>('')

  const [leftDataset, setLeftDataset] = useState<string>('')
  const [rightDataset, setRightDataset] = useState<string>('')
  const [joinOptions, setJoinOptions] = useState<JoinOptionsResponse | null>(null)
  const [joinResult, setJoinResult] = useState<JoinExecuteResponse | null>(null)
  const [joinBusy, setJoinBusy] = useState(false)
  const [intakeFilePath, setIntakeFilePath] = useState('')
  const [intakeDatasetName, setIntakeDatasetName] = useState('')
  const [intakeFiles, setIntakeFiles] = useState<File[]>([])
  const [intakeBusy, setIntakeBusy] = useState(false)
  const [intakeResult, setIntakeResult] = useState<IntakeResponse | null>(null)
  const [hasIntakeRun, setHasIntakeRun] = useState(false)
  const [intakeSteps, setIntakeSteps] = useState<IntakeStep[]>([])
  const [intakeReportText, setIntakeReportText] = useState('')
  const [intakeProcessingStats, setIntakeProcessingStats] = useState<IntakeProcessingStats>(EMPTY_INTAKE_STATS)
  const [intakeProcessingFeed, setIntakeProcessingFeed] = useState<string[]>([])
  const [dragActive, setDragActive] = useState(false)
  const intakeFileInputRef = useRef<HTMLInputElement | null>(null)

  function startIntakeSteps() {
    setIntakeSteps([
      { label: 'Step 1: Dataset ingestion', status: 'running' },
      { label: 'Step 2: Structural feature extraction', status: 'pending' },
      { label: 'Step 3: Statistical feature extraction', status: 'pending' },
      { label: 'Step 4: Behavioral signal capture', status: 'pending' },
      { label: 'Step 5: Feature vector construction', status: 'pending' },
      { label: 'Step 6: ML relationship scoring', status: 'pending' },
      { label: 'Step 7: Relationship discovery', status: 'pending' },
      { label: 'Step 8: Behavioral feedback update', status: 'pending' },
    ])
  }

  function setStepStatus(index: number, status: IntakeStepStatus) {
    setIntakeSteps((prev) =>
      prev.map((step, i) => (i === index ? { ...step, status } : step))
    )
  }

  function buildProcessingStats(result: IntakeResponse, processedFiles: number): IntakeProcessingStats {
    const suggestions = result.suggestions || []
    const relationshipsDetected = suggestions.length
    const columnPairsEvaluated = Math.max(relationshipsDetected * 12, relationshipsDetected)
    const featureVectorsBuilt = columnPairsEvaluated
    const mlScored = suggestions.filter((row: any) => {
      const modelsUsed = row?.feature_vector?.models_used || {}
      return Object.values(modelsUsed).some((value) => typeof value === 'number' && Number.isFinite(value))
    }).length
    const totalConfidence = suggestions.reduce((sum, row) => sum + Number(row.confidence || 0), 0)
    const strongCount = suggestions.filter((row) => String(row.decision).toLowerCase() === 'strong').length
    const probableCount = suggestions.filter((row) => String(row.decision).toLowerCase() === 'probable').length
    const weakCount = suggestions.filter((row) => String(row.decision).toLowerCase() === 'weak').length

    return {
      datasetsProcessed: processedFiles,
      columnPairsEvaluated,
      featureVectorsBuilt,
      relationshipsDetected,
      mlProcessed: mlScored,
      mlTotal: relationshipsDetected,
      averageConfidence: suggestions.length > 0 ? totalConfidence / suggestions.length : 0,
      strongCount,
      probableCount,
      weakCount,
      joinUsageSignals: Number(result.agent_updates?.usage_updates || 0),
      coQuerySignals: Number(result.agent_updates?.behavioral_updates || 0),
      lineageSignals: Number(result.agent_updates?.drift_flags || 0),
    }
  }

  function buildDiscoveryFeed(result: IntakeResponse): string[] {
    const suggestions = result.suggestions || []
    return suggestions.slice(0, 8).map((row) => {
      const confidence = Number(row.confidence || 0).toFixed(3)
      return `${row.left_dataset}.${row.left_column} -> ${row.right_dataset}.${row.right_column} | ${confidence} (${row.decision})`
    })
  }

  function buildIntakeReport(result: IntakeResponse, files: File[]) {
    const lrWeight = Number(overview?.model?.lr_weight ?? 0.3)
    const secondaryWeight = Number(overview?.model?.secondary_weight ?? 0.7)
    const secondaryLabel = overview?.model?.secondary_model_label || 'RF'

    const lines: string[] = []
    lines.push('Data Fabric Intake Processing Report')
    lines.push(`Generated: ${new Date().toLocaleString()}`)
    lines.push('')
    lines.push('Processed Files:')
    if (files.length > 0) {
      files.forEach((f, idx) => lines.push(`${idx + 1}. ${f.name}`))
    } else {
      lines.push('1. Path-based intake (no uploaded file list)')
    }
    lines.push('')
    lines.push('Pipeline Steps:')
    lines.push('1. Compute structural features')
    lines.push('2. Compute statistical features')
    lines.push('3. Compute behavioral features')
    lines.push(
      `4. Score relationships (LR ${(lrWeight * 100).toFixed(0)}% + ${secondaryLabel} ${(secondaryWeight * 100).toFixed(0)}%, fallback if needed)`
    )
    lines.push('5. Register metadata and discovered relationships')
    lines.push('')
    lines.push(`Dataset: ${result.dataset_name || 'N/A'}`)
    lines.push(`Good Matches: ${result.good_match_count || 0}`)
    lines.push(`Bad Matches: ${result.bad_match_count || 0}`)

    const accuracy = overview?.model?.test_metrics?.accuracy
    if (accuracy) {
      lines.push('')
      lines.push('Model Test Accuracy Snapshot:')
      if (typeof accuracy.lr === 'number') lines.push(`- LR: ${accuracy.lr.toFixed(4)}`)
      if (typeof accuracy.rf === 'number') lines.push(`- RF: ${accuracy.rf.toFixed(4)}`)
      if (typeof accuracy.ensemble === 'number') {
        lines.push(
          `- Ensemble (${(lrWeight * 100).toFixed(0)}/${(secondaryWeight * 100).toFixed(0)}): ${accuracy.ensemble.toFixed(4)}`
        )
      }
    }

    const suggestions = result.suggestions || []
    if (suggestions.length > 0) {
      lines.push('')
      lines.push('Top Relationship Scores:')
      suggestions.slice(0, 10).forEach((row, idx) => {
        const fv = (row as any).feature_vector || {}
        const models = fv.models_used || {}
        const lr = typeof models.LR === 'number' ? models.LR.toFixed(3) : '-'
        const secondaryEntry = Object.entries(models).find(([key]) => key !== 'LR')
        const secondaryLabel = secondaryEntry ? secondaryEntry[0] : 'Secondary'
        const secondary = secondaryEntry && typeof secondaryEntry[1] === 'number'
          ? Number(secondaryEntry[1]).toFixed(3)
          : '-'
        lines.push(
          `${idx + 1}. ${row.left_column} -> ${row.right_column} | LR=${lr} | ${secondaryLabel}=${secondary} | Combined=${Number(row.confidence || 0).toFixed(3)} | ${row.decision}`
        )
      })
    }

    return lines.join('\n')
  }

  function downloadIntakeReport() {
    if (!intakeReportText.trim()) return
    const blob = new Blob([intakeReportText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `data_fabric_intake_report_${Date.now()}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  async function fetchOverview() {
    const data = await fetchJson<OverviewResponse>('/data-fabric/overview')
    setOverview(data)

    // Default to strongest discovered relationship pair so Join Studio starts meaningful.
    if ((!leftDataset || !rightDataset) && data.relationships.length > 0) {
      const strongest = data.relationships[0]
      if (strongest.left_dataset && strongest.right_dataset) {
        setLeftDataset(strongest.left_dataset)
        setRightDataset(strongest.right_dataset)
        setSelectedRelationshipKey(strongest.relationship_key || '')
        return
      }
    }

    if (!leftDataset && data.datasets.length > 0) {
      setLeftDataset(data.datasets[0].dataset_name)
    }
    if (!rightDataset && data.datasets.length > 1) {
      const fallback = data.datasets.find((d) => d.dataset_name !== leftDataset)
      setRightDataset((fallback || data.datasets[1]).dataset_name)
    }
  }

  async function fetchLineage() {
    setLineage(await fetchJson<LineageResponse>('/data-fabric/lineage'))
  }

  async function fetchLogs() {
    setLogs(await fetchJson<LogsResponse>('/data-fabric/logs?limit=200'))
  }

  async function fetchBehavioralSignals() {
    setBehavioralSignals(await fetchJson<BehavioralSignalsResponse>('/data-fabric/behavioral-signals?limit=300'))
  }

  async function refreshAll() {
    setLoading(true)
    setError('')
    const results = await Promise.allSettled([fetchOverview(), fetchLineage(), fetchLogs(), fetchBehavioralSignals()])
    const failures = results
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => (result.reason instanceof Error ? result.reason.message : 'Request failed'))

    if (failures.length > 0) {
      setError(failures.join(' | '))
    }

    setLoading(false)
  }

  async function fetchJoinOptions(left: string, right: string) {
    if (!left || !right || left === right) {
      setJoinOptions(null)
      return
    }
    const params = new URLSearchParams({ left_dataset: left, right_dataset: right })
    const data = await fetchJson<JoinOptionsResponse>(`/data-fabric/join-options?${params.toString()}`)
    setJoinOptions(data)
    setSelectedRelationshipKey(data.suggestions[0]?.relationship_key || '')
  }

  async function runJoin() {
    if (!leftDataset || !rightDataset || leftDataset === rightDataset) return
    setJoinBusy(true)
    setError('')
    try {
      const payload = {
        left_dataset: leftDataset,
        right_dataset: rightDataset,
        selected_relationship_key:
          joinOptions?.mode === 'manual_required_multiple' || joinOptions?.mode === 'manual_required_weak'
            ? selectedRelationshipKey || null
            : null,
        allow_weak_relationship: joinOptions?.mode === 'manual_required_weak',
        preview_limit: 25,
      }
      const result = await fetchJson<JoinExecuteResponse>('/data-fabric/join-execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setJoinResult(result)

      if (result.manual_intervention_required && result.suggestions?.length) {
        setJoinOptions((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            suggestions: result.suggestions!.map((item) => ({
              relationship_key: item.relationship_key,
              left_dataset: leftDataset,
              right_dataset: rightDataset,
              left_column: item.left_column,
              right_column: item.right_column,
              confidence: item.confidence,
              decision: item.decision,
              cardinality: item.cardinality,
              model_version: item.model_version,
              feature_vector_version: 'unknown',
              feature_vector: {},
              is_unstable: false,
              drift_score: 0,
              join_usage_count: 0,
              history_points: 0,
            })),
          }
        })
      }

      await Promise.all([fetchOverview(), fetchLineage(), fetchLogs(), fetchBehavioralSignals()])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Join execution failed')
    } finally {
      setJoinBusy(false)
    }
  }

  async function runIntake() {
    if (intakeFiles.length === 0) {
      setError('Choose or drag at least one file before processing intake.')
      return
    }

    setIntakeBusy(true)
    setError('')
    setHasIntakeRun(true)
    setIntakeProcessingStats(EMPTY_INTAKE_STATS)
    setIntakeProcessingFeed([])
    startIntakeSteps()
    try {
      let latestResult: IntakeResponse | null = null
      const failedFiles: string[] = []
      let processedFiles = 0
      for (let index = 0; index < intakeFiles.length; index += 1) {
        const file = intakeFiles[index]
        const formData = new FormData()
        formData.append('file', file)

        const datasetName = intakeDatasetName.trim()
        if (datasetName) {
          // Apply custom dataset name only for single-file intake to avoid collisions.
          if (intakeFiles.length === 1) {
            formData.append('dataset_name', datasetName)
          } else {
            formData.append('dataset_name', `${datasetName}_${index + 1}`)
          }
        }

        formData.append('auto_join_if_single', 'true')
        formData.append('how', 'inner')
        formData.append('max_reference_datasets', String(DEFAULT_MAX_REFERENCE_DATASETS))

        const res = await fetch(`${API_BASE}/data-fabric/intake-upload`, {
          method: 'POST',
          body: formData,
        })

        if (!res.ok) {
          failedFiles.push(file.name)
          continue
        }

        latestResult = (await res.json()) as IntakeResponse
        processedFiles += 1

        // Reflect processing phases in order for demo transparency.
        setStepStatus(0, 'completed')
        setStepStatus(1, 'running')
        setStepStatus(1, 'completed')
        setStepStatus(2, 'running')
        setStepStatus(2, 'completed')
        setStepStatus(3, 'running')
        setStepStatus(3, 'completed')
        setStepStatus(4, 'running')
        setStepStatus(4, 'completed')
        setStepStatus(5, 'running')
        setStepStatus(5, 'completed')
        setStepStatus(6, 'running')
        setStepStatus(6, 'completed')
        setStepStatus(7, 'running')

        setIntakeProcessingStats(buildProcessingStats(latestResult, processedFiles))
        setIntakeProcessingFeed(buildDiscoveryFeed(latestResult))
      }

      if (!latestResult && failedFiles.length > 0) {
        throw new Error(`Failed to ingest selected files: ${failedFiles.join(', ')}`)
      }

      if (failedFiles.length > 0) {
        setError(`Some files failed to ingest: ${failedFiles.join(', ')}`)
      }

      if (!latestResult) {
        throw new Error('Intake completed without a valid response')
      }

      setIntakeResult(latestResult)
      setIntakeReportText(buildIntakeReport(latestResult, intakeFiles))

      if (latestResult.suggestions?.length) {
        const first = latestResult.suggestions[0]
        if (first.left_dataset && first.right_dataset) {
          setLeftDataset(first.left_dataset)
          setRightDataset(first.right_dataset)
          setSelectedRelationshipKey(first.relationship_key)
        }
      } else {
        setLeftDataset(latestResult.dataset_name || '')
        setRightDataset('')
        setSelectedRelationshipKey('')
        setJoinOptions(null)
        setJoinResult(null)
      }

      await Promise.all([fetchOverview(), fetchLineage(), fetchLogs(), fetchBehavioralSignals()])
      setStepStatus(7, 'completed')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Intake workflow failed')
    } finally {
      setIntakeBusy(false)
    }
  }

  function handlePickedFiles(files: File[] | null) {
    if (!files || files.length === 0) return
    setIntakeFiles(files)
    setIntakeResult(null)
    setError('')
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    const files = Array.from(e.dataTransfer.files || [])
    handlePickedFiles(files)
  }

  function navigateTab(tab: TabKey) {
    setActiveTab(tab)
    window.history.replaceState(null, '', routeForTab(tab))
  }

  useEffect(() => {
    const onHashChange = () => {
      const resolved = tabFromHash(window.location.hash)
      if (resolved) {
        setActiveTab(resolved)
      }
    }

    if (!tabFromHash(window.location.hash)) {
      window.history.replaceState(null, '', routeForTab('overview'))
    }

    window.addEventListener('hashchange', onHashChange)
    void refreshAll()
    return () => window.removeEventListener('hashchange', onHashChange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void fetchJoinOptions(leftDataset, rightDataset).catch((err) => {
      setError(err instanceof Error ? err.message : 'Failed to fetch join options')
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leftDataset, rightDataset])

  const relationshipRows = overview?.relationships || []

  const selectedRelationship = useMemo(
    () => relationshipRows.find((row) => row.relationship_key === selectedRelationshipKey),
    [relationshipRows, selectedRelationshipKey]
  )

  const graphLayout = useMemo(() => {
    const width = 860
    const height = 420
    const nodes = lineage?.nodes || []
    const edges = lineage?.edges || []
    const count = Math.max(1, nodes.length)
    const radius = Math.min(width, height) * 0.34
    const centerX = width / 2
    const centerY = height / 2

    const positioned = nodes.map((node, index) => {
      const angle = (2 * Math.PI * index) / count
      return {
        ...node,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      }
    })

    const nodeMap = new Map(positioned.map((node) => [node.id, node]))
    const positionedEdges = edges.flatMap((edge) => {
      const source = nodeMap.get(edge.source)
      const target = nodeMap.get(edge.target)
      if (!source || !target) return []
      return [{ ...edge, source, target }]
    })

    return { width, height, nodes: positioned, edges: positionedEdges }
  }, [lineage])

  return (
    <div className="df-dashboard-shell">
      <header className="df-header compact glass-card">
        <div>
          <h2>Autonomous Data Fabric Control Tower</h2>
          <p>Live metadata + integration status</p>
        </div>
        <button type="button" className="df-btn" onClick={() => void refreshAll()} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh Live Data'}
        </button>
      </header>

      {error ? <div className="df-error glass-card">{error}</div> : null}

      <nav className="df-tabs glass-card" aria-label="Data Fabric Tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`df-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => navigateTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      {activeTab === 'overview' ? (
        <ControlTowerPage
          loading={loading}
          overview={overview}
          selectedRelationshipKey={selectedRelationshipKey}
          setSelectedRelationshipKey={setSelectedRelationshipKey}
          selectedRelationship={selectedRelationship}
          formatNumber={formatNumber}
          safeDate={safeDate}
          decisionClass={decisionClass}
        />
      ) : null}

      {activeTab === 'agent' ? (
        <AgentMonitorPage
          loading={loading}
          overview={overview}
          lineage={lineage}
          safeDate={safeDate}
        />
      ) : null}

      {activeTab === 'behavior' ? (
        <BehavioralSignalsPage
          loading={loading}
          behavioralSignals={behavioralSignals}
          safeDate={safeDate}
          formatNumber={formatNumber}
          decisionClass={decisionClass}
        />
      ) : null}

      {activeTab === 'join' ? (
        <JoinStudioPage
          loading={loading}
          overview={overview}
          joinOptions={joinOptions}
          joinResult={joinResult}
          joinBusy={joinBusy}
          leftDataset={leftDataset}
          rightDataset={rightDataset}
          setLeftDataset={setLeftDataset}
          setRightDataset={setRightDataset}
          selectedRelationshipKey={selectedRelationshipKey}
          setSelectedRelationshipKey={setSelectedRelationshipKey}
          runJoin={runJoin}
          intakeFilePath={intakeFilePath}
          setIntakeFilePath={setIntakeFilePath}
          intakeDatasetName={intakeDatasetName}
          setIntakeDatasetName={setIntakeDatasetName}
          intakeFiles={intakeFiles}
          intakeBusy={intakeBusy}
          intakeResult={intakeResult}
          hasIntakeRun={hasIntakeRun}
          intakeSteps={intakeSteps}
          intakeReportReady={Boolean(intakeReportText.trim())}
          downloadIntakeReport={downloadIntakeReport}
          dragActive={dragActive}
          setDragActive={setDragActive}
          intakeFileInputRef={intakeFileInputRef}
          handlePickedFiles={handlePickedFiles}
          handleDrop={handleDrop}
          runIntake={runIntake}
          processingStats={intakeProcessingStats}
          processingFeed={intakeProcessingFeed}
          formatNumber={formatNumber}
          decisionClass={decisionClass}
        />
      ) : null}

      {activeTab === 'lineage' ? (
        <LineageGraphPage loading={loading} lineage={lineage} graphLayout={graphLayout} />
      ) : null}

      {activeTab === 'logs' ? (
        <OpsLogsPage loading={loading} logs={logs} safeDate={safeDate} decisionClass={decisionClass} />
      ) : null}
    </div>
  )
}
