import React, { useEffect, useMemo, useRef, useState } from 'react'
import { getAgenticApiBase } from '../../../lib/agenticApiBase'
import '../../data_fabric/components/DataFabricTestingPage.css'
import './FeatureOpsWorkflowPanel.css'
import { FeatureOpsDatasetHistoryTables } from './FeatureOpsDatasetHistoryTables'
import { detectInternalDrift, detectExternalDrift, mapBackendSignalsToUIResults, detectDriftFull, getPredefinedBaselines, setOrchestratorBaseline } from '../../../services/driftApi'
type DatasetValue = string | number | boolean | null
type DatasetRow = Record<string, DatasetValue>
type InferredType = 'numeric' | 'datetime' | 'boolean' | 'text' | 'mixed' | 'unknown'
type GenericRole =
  | 'Identifier'
  | 'Timestamp'
  | 'Numeric Measure'
  | 'Categorical Attribute'
  | 'Text Attribute'
  | 'Score / Rating'
  | 'Count / Activity'
  | 'Rate / Percentage'
  | 'Binary Label'
  | 'Target Column'
  | 'Unknown / Unmapped'
type DriftSeverity = 'NONE' | 'LOW' | 'MODERATE' | 'HIGH'
type FeatureStatus = 'READY' | 'CONDITIONAL' | 'QUARANTINED'

type ColumnProfile = {
  column_name: string
  inferred_type: InferredType
  missing_percent: number
  unique_percent: number
  min: number | null
  max: number | null
  mean: number | null
  std: number | null
  sample_values: string[]
  row_count: number
  column_count: number
  valid_date_percent: number
  integer_like_percent: number
  binary_like_percent: number
  avg_string_length: number
  outlier_percent: number
  scale_pattern: string
  value_pattern: string
  nullable: boolean
  detected_unit: string
  detected_direction: string
}

type RoleDetection = {
  column_name: string
  detected_role: GenericRole
  confidence: number
  reason: string
}

type SemanticProfile = {
  column_name: string
  approved_or_detected_meaning: string
  generic_role: GenericRole
  expected_scale: string
  detected_scale: string
  expected_unit: string
  detected_unit: string
  value_direction: string
  source_columns: string[]
  computation_logic: string
  semantic_signature: string
}

type InternalDriftResult = {
  column_name: string
  compared_by: string
  segment_summaries: Array<{ segment: string; scale: string; mean: number | null; unique_percent: number }>
  drift_severity: DriftSeverity
  evidence: string[]
  explanation: string
  recommended_action: string
}

type ExternalDriftResult = {
  column_name: string
  baseline_version: string
  current_version: string
  baseline_meaning: string
  current_detected_meaning: string
  drift_severity: DriftSeverity
  evidence: string[]
  explanation: string
  recommended_action: string
}

type StatisticalDriftResult = {
  column_name: string
  baseline_version: string
  current_version: string
  field_type: 'numeric' | 'categorical'
  drift_severity: DriftSeverity
  score: number
  evidence: string[]
  explanation: string
  recommended_action: string
}

type BehavioralDriftResult = {
  column_name: string
  baseline_version: string
  current_version: string
  baseline_release_status: FeatureStatus
  current_release_status: FeatureStatus
  release_status_delta: number
  drift_severity: DriftSeverity
  evidence: string[]
  explanation: string
  recommended_action: string
}

type ReleaseResult = {
  column_name: string
  role: GenericRole
  validation_status: 'PASS' | 'WARN' | 'FAIL'
  internal_drift_severity: DriftSeverity
  external_drift_severity: DriftSeverity
  statistical_drift_severity: DriftSeverity
  behavioral_drift_severity: DriftSeverity
  release_status: FeatureStatus
  critical_failures: string[]
  warnings: string[]
  explanation: string
  recommended_action: string
}

type DatasetFingerprint = {
  column_names: string[]
  roles: string[]
  types: string[]
  scale_patterns: string[]
  important_columns: string[]
}

type FamilyRecord = {
  family_id: string
  family_name: string
  created_at: string
  updated_at: string
  description: string
  versions: number[]
  latest_version: number
  approved_baseline_version?: number
  version_count?: number
  baseline_status: string
  /** Synthetic row: data-architecture predefined baseline not yet saved in the registry */
  is_architecture_template?: boolean
  baseline_key?: string
}

type StoredVersion = {
  version_id: string
  dataset_family_id: string
  version_number: number
  dataset_name: string
  file_name?: string
  version_note?: string
  created_at: string
  row_count: number
  column_count: number
  column_names: string[]
  dataset_rows?: DatasetRow[]
  dataset_fingerprint: DatasetFingerprint
  column_profiles: ColumnProfile[]
  semantic_profiles: SemanticProfile[]
  internal_drift_results: InternalDriftResult[]
  external_drift_results?: ExternalDriftResult[]
  statistical_drift_results?: StatisticalDriftResult[]
  behavioral_drift_results?: BehavioralDriftResult[]
  release_results: ReleaseResult[]
}

type VersionPairComparison = {
  left: StoredVersion
  right: StoredVersion
  external: ExternalDriftResult[]
  releaseByColumn: Record<string, ReleaseResult>
  severityCounts: Record<DriftSeverity, number>
  comparedColumns: number
}

type SanityCheckResult = {
  passed: boolean
  requiredColumns: string[]
  importantColumns: string[]
  missingColumns: string[]
  extraColumns: string[]
  columnCountDelta: number
}

type DuplicateDatasetResult = {
  familyId: string
  familyName: string
  versionNumber: number
}

type DriftRunRecord = {
  run_id: string
  dataset_name: string
  family_id?: string | null
  version_id?: string | null
  version_number?: number | null
  created_at: string
  dataset_rows?: DatasetRow[] | null
  dataset_fingerprint: DatasetFingerprint
  internal_drift_results: InternalDriftResult[]
  external_drift_results?: ExternalDriftResult[] | null
  statistical_drift_results?: StatisticalDriftResult[] | null
  behavioral_drift_results?: BehavioralDriftResult[] | null
  release_results: ReleaseResult[]
}

type StatusMessage = {
  id: string
  ts: string
  type: 'success' | 'warning' | 'error' | 'info' | 'pending'
  message: string
}

type FamilyMatch = {
  family_id: string
  family_name: string
  version_number: number
  version_id: string
  match_score: number
}

type MappingReviewFinding = {
  column_name: string
  current_role: GenericRole
  suggested_role: GenericRole
  reason: string
}

type SemanticProfileOverride = Partial<Pick<SemanticProfile, 'approved_or_detected_meaning' | 'expected_scale' | 'expected_unit' | 'value_direction'>>

type PredefinedBaselineColumn = {
  business_meaning: string
  role: string
  domain: string
  unit: string
  scale: string
  data_type: string
  value_direction: string
}

type PredefinedBaseline = {
  baseline_key: string
  dataset_name: string
  baseline_version: string
  description: string
  source_table: string
  column_count: number
  columns: Record<string, PredefinedBaselineColumn>
}

/** Prefix for synthetic family_id rows that map to predefined architecture baselines */
const ARCH_TEMPLATE_FAMILY_PREFIX = '__arch_template__:'

function slugifyFamilyId(value: string): string {
  const cleaned = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return cleaned || 'family'
}

function predefinedTemplateCoveredByRegistry(pre: PredefinedBaseline, registryFamilies: FamilyRecord[]): boolean {
  const idDataset = slugifyFamilyId(pre.dataset_name)
  const idKey = slugifyFamilyId(pre.baseline_key)
  const norm = (s: string) =>
    s.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase()
  const nameNorm = norm(pre.dataset_name.replace(/_/g, ' '))
  const keyNorm = norm(pre.baseline_key)
  return registryFamilies.some((f) => {
    if (f.is_architecture_template) return false
    if (f.family_id === idDataset || f.family_id === idKey) return true
    const fn = norm(String(f.family_name || ''))
    return fn === nameNorm || fn === keyNorm
  })
}

function buildArchitectureTemplateFamilyRecord(pre: PredefinedBaseline): FamilyRecord {
  const now = new Date().toISOString()
  return {
    family_id: `${ARCH_TEMPLATE_FAMILY_PREFIX}${pre.baseline_key}`,
    family_name: `${pre.dataset_name.replace(/_/g, ' ')} (approved template)`,
    description: pre.description || 'Approved data-architecture semantic baseline template.',
    created_at: now,
    updated_at: now,
    versions: [],
    latest_version: 0,
    version_count: 0,
    baseline_status: 'TEMPLATE',
    is_architecture_template: true,
    baseline_key: pre.baseline_key,
  }
}

const ROLE_OPTIONS: GenericRole[] = [
  'Identifier',
  'Timestamp',
  'Numeric Measure',
  'Categorical Attribute',
  'Text Attribute',
  'Score / Rating',
  'Count / Activity',
  'Rate / Percentage',
  'Binary Label',
  'Target Column',
  'Unknown / Unmapped',
]

const DEMO_NAME = 'esp32_tilt_synthetic_dataset.csv'
const IDENTIFIER_KEYWORDS = ['id', 'uuid', 'deviceid', 'rideid', 'productid', 'userid', 'customerid', 'sensorid']
const TIMESTAMP_KEYWORDS = ['timestamp', 'date', 'time', 'created_at', 'updated_at', 'datetime']
const SCORE_KEYWORDS = ['score', 'rating', 'risk', 'confidence', 'probability', 'likelihood']
const COUNT_KEYWORDS = ['click', 'view', 'count', 'purchase', 'event', 'visit', 'order', 'sale']
const RATE_KEYWORDS = ['ratio', 'percentage', 'pct', 'percent']
const BINARY_KEYWORDS = ['flag', 'detected', 'is_', 'has_', 'failed', 'anomaly']
const TARGET_KEYWORDS = ['label', 'target', 'relevant', 'outcome', 'class']
const TEXT_KEYWORDS = ['description', 'comment', 'message', 'review', 'query', 'prompt', 'title', 'name']

const demoDataset: DatasetRow[] = [
  { deviceId: 'ESP32_BAG_01', rideId: 'RIDE_001', timestamp: '2025-01-06 14:25:00', temperature: 29.18, coldTemperature: 28.78, humidity: 77.84, rainValue: 4095, rainStatus: 'Wet', magnetDetected: true, tilt_rate: -0.23, tilt_risk_score: 0.12, rain_risk_score: 0.81, label: 1 },
  { deviceId: 'ESP32_BAG_01', rideId: 'RIDE_001', timestamp: '2025-01-06 14:25:05', temperature: 27.81, coldTemperature: 27.41, humidity: 77.65, rainValue: 1500, rainStatus: 'Dry', magnetDetected: false, tilt_rate: 0.11, tilt_risk_score: 0.08, rain_risk_score: 0.25, label: 0 },
  { deviceId: 'ESP32_BAG_01', rideId: 'RIDE_001', timestamp: '2025-01-06 14:25:10', temperature: 28.73, coldTemperature: 28.33, humidity: 78.55, rainValue: 4095, rainStatus: 'Wet', magnetDetected: true, tilt_rate: -0.08, tilt_risk_score: 0.15, rain_risk_score: 0.88, label: 1 },
  { deviceId: 'ESP32_BAG_01', rideId: 'RIDE_001', timestamp: '2025-01-06 14:25:15', temperature: 29.32, coldTemperature: 28.92, humidity: 77.91, rainValue: 4095, rainStatus: 'Wet', magnetDetected: true, tilt_rate: 0.04, tilt_risk_score: 0.11, rain_risk_score: 0.79, label: 1 },
  { deviceId: 'ESP32_BAG_01', rideId: 'RIDE_001', timestamp: '2025-01-06 14:25:20', temperature: 27.68, coldTemperature: 27.28, humidity: 77.60, rainValue: 4095, rainStatus: 'Dry', magnetDetected: false, tilt_rate: -0.31, tilt_risk_score: 0.09, rain_risk_score: 0.64, label: 0 },
]

function clamp(value: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value))
}

function parseNumberish(value: DatasetValue): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'boolean') return value ? 1 : 0
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  if (/[a-z]/i.test(trimmed)) return null
  const parsed = Number(trimmed.replace(/[%,$\s]/g, ''))
  return Number.isFinite(parsed) ? parsed : null
}

function parseDateValue(value: DatasetValue): number | null {
  if (value == null || value === '' || typeof value === 'number' || typeof value === 'boolean') return null
  const raw = String(value).trim()
  if (!raw) return null
  const looksDateLike = /\d{4}[-/]\d{1,2}[-/]\d{1,2}/.test(raw)
    || /\d{1,2}:\d{2}(:\d{2})?/.test(raw)
    || /t\d{2}:\d{2}/i.test(raw)
    || /\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b/i.test(raw)
  if (!looksDateLike) return null
  const date = new Date(raw)
  const time = date.getTime()
  return Number.isFinite(time) ? time : null
}

function average(values: number[]) {
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function stdDev(values: number[]) {
  if (values.length < 2) return 0
  const mean = average(values) ?? 0
  return Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length)
}

function formatPct(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function safeFixed(value: number | null, digits = 2) {
  return value == null ? 'N/A' : value.toFixed(digits)
}

function keywordMatch(columnName: string, keywords: string[]) {
  const tokenized = columnName
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
  const tokens = tokenized ? tokenized.split(/\s+/) : []
  const compact = tokens.join('')
  return keywords.some((keyword) => {
    const normalizedKeyword = keyword.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
    const keywordTokens = normalizedKeyword ? normalizedKeyword.split(/\s+/) : []
    const keywordCompact = keywordTokens.join('')
    if (!keywordTokens.length) return false
    if (tokens.includes(normalizedKeyword)) return true
    if (keywordTokens.length > 1 && tokenized.includes(normalizedKeyword)) return true
    return keywordCompact.length >= 4 ? compact.includes(keywordCompact) : compact === keywordCompact
  })
}

function inferIdentifierPattern(value: DatasetValue) {
  const raw = String(value ?? '').trim()
  if (!raw) return 'empty'
  return raw
    .replace(/[A-Z]/g, 'A')
    .replace(/[a-z]/g, 'a')
    .replace(/[0-9]/g, '9')
}

function inferScalePattern(values: number[]) {
  if (!values.length) return 'unknown'
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min >= 0 && max <= 1) return '0-1'
  if (min >= 0 && max <= 100) return '0-100'
  if (min >= 1 && max <= 5) return '1-5'
  if (min >= 1 && max <= 10) return '1-10'
  if (Number.isInteger(min) && Number.isInteger(max) && min >= 0) return 'count'
  if (max > 1000 && min >= 0) return 'raw_sensor_adc'
  return 'continuous'
}

function inferUnit(columnName: string, scalePattern: string) {
  const lowered = columnName.toLowerCase()
  if (lowered.includes('temperature')) return 'temperature-like'
  if (lowered.includes('humidity')) return 'percentage-like'
  if (lowered.includes('score') || lowered.includes('risk')) return 'probability-like score'
  if (scalePattern === 'raw_sensor_adc') return 'raw sensor scale'
  if (scalePattern === 'count') return 'count'
  if (scalePattern === '0-100') return 'percentage'
  return 'unitless'
}

function inferDirection(columnName: string, role: GenericRole) {
  const lowered = columnName.toLowerCase()
  if (lowered.includes('risk')) return 'higher means higher risk'
  if (role === 'Score / Rating') return 'higher means stronger score'
  if (role === 'Count / Activity') return 'higher means more activity'
  if (role === 'Rate / Percentage') return 'higher means larger share'
  return 'neutral'
}

function suggestPredefinedBaselineKey(
  name: string,
  rows: DatasetRow[],
  options: PredefinedBaseline[],
) {
  const normalizedName = name.toLowerCase()
  const columns = rows.length ? Object.keys(rows[0] || {}).map((column) => column.toLowerCase()) : []
  let bestKey = ''
  let bestScore = 0

  options.forEach((option) => {
    const baselineColumns = Object.keys(option.columns || {}).map((column) => column.toLowerCase())
    const overlap = baselineColumns.length
      ? baselineColumns.filter((column) => columns.includes(column)).length / baselineColumns.length
      : 0
    const nameScore = normalizedName.includes(option.baseline_key)
      || normalizedName.includes(option.dataset_name.toLowerCase())
      || normalizedName.includes(option.source_table.toLowerCase())
      ? 0.45
      : 0
    const score = overlap + nameScore
    if (score > bestScore) {
      bestScore = score
      bestKey = option.baseline_key
    }
  })

  return bestScore >= 0.25 ? bestKey : ''
}

function buildColumnProfile(columnName: string, rows: DatasetRow[], columnCount: number): ColumnProfile {
  const values = rows.map((row) => row[columnName] ?? null)
  const filled = values.filter((value) => value != null && String(value).trim() !== '')
  const numericValues = filled.map(parseNumberish).filter((value): value is number => value != null)
  const dateValues = filled.map(parseDateValue).filter((value): value is number => value != null)
  const missingPercent = rows.length ? (rows.length - filled.length) / rows.length : 0
  const uniquePercent = filled.length ? new Set(filled.map((value) => String(value).trim().toLowerCase())).size / filled.length : 0
  const numericPercent = filled.length ? numericValues.length / filled.length : 0
  const validDatePercent = filled.length ? dateValues.length / filled.length : 0
  const integerLikePercent = numericValues.length ? numericValues.filter((value) => Number.isInteger(value)).length / numericValues.length : 0
  const binaryLikePercent = numericValues.length ? numericValues.filter((value) => value === 0 || value === 1).length / numericValues.length : 0
  const avgStringLength = filled.length ? filled.reduce<number>((sum, value) => sum + String(value).length, 0) / filled.length : 0
  const mean = average(numericValues)
  const std = stdDev(numericValues)
  const scalePattern = inferScalePattern(numericValues)

  let inferredType: InferredType = 'unknown'
  if (!filled.length) inferredType = 'unknown'
  else if (binaryLikePercent >= 0.95) inferredType = 'boolean'
  else if (validDatePercent >= 0.85) inferredType = 'datetime'
  else if (numericPercent >= 0.9) inferredType = 'numeric'
  else if (numericPercent >= 0.25) inferredType = 'mixed'
  else inferredType = 'text'

  let outlierPercent = 0
  if (numericValues.length >= 4 && mean != null && (std ?? 0) > 0) {
    outlierPercent = numericValues.filter((value) => Math.abs(value - mean) > (std ?? 0) * 3).length / numericValues.length
  }

  return {
    column_name: columnName,
    inferred_type: inferredType,
    missing_percent: missingPercent,
    unique_percent: uniquePercent,
    min: numericValues.length ? Math.min(...numericValues) : null,
    max: numericValues.length ? Math.max(...numericValues) : null,
    mean,
    std,
    sample_values: filled.slice(0, 4).map((value) => String(value)),
    row_count: rows.length,
    column_count: columnCount,
    valid_date_percent: validDatePercent,
    integer_like_percent: integerLikePercent,
    binary_like_percent: binaryLikePercent,
    avg_string_length: avgStringLength,
    outlier_percent: outlierPercent,
    scale_pattern: scalePattern,
    value_pattern: inferredType === 'text' ? 'textual' : scalePattern,
    nullable: missingPercent > 0,
    detected_unit: inferUnit(columnName, scalePattern),
    detected_direction: 'neutral',
  }
}

function detectRole(profile: ColumnProfile): RoleDetection {
  const name = profile.column_name.toLowerCase()
  let detectedRole: GenericRole = 'Unknown / Unmapped'
  let confidence = 0.25
  let reason = 'No strong deterministic pattern matched.'
  const hasIdentifierKeyword = keywordMatch(name, IDENTIFIER_KEYWORDS)
  const hasTimestampKeyword = keywordMatch(name, TIMESTAMP_KEYWORDS)
  const hasTargetKeyword = keywordMatch(name, TARGET_KEYWORDS)
  const hasBinaryKeyword = keywordMatch(name, BINARY_KEYWORDS)
  const hasScoreKeyword = keywordMatch(name, SCORE_KEYWORDS)
  const hasCountKeyword = keywordMatch(name, COUNT_KEYWORDS)
  const hasRateKeyword = keywordMatch(name, RATE_KEYWORDS)
  const hasTextKeyword = keywordMatch(name, TEXT_KEYWORDS)

  if (hasIdentifierKeyword && (profile.unique_percent >= 0.2 || name.endsWith('id'))) {
    detectedRole = 'Identifier'
    confidence = profile.unique_percent >= 0.75 ? 0.98 : 0.86
    reason = profile.unique_percent >= 0.75
      ? 'Contains ID keyword and behaves like a high-uniqueness identifier.'
      : 'Contains ID keyword and behaves like a repeated entity identifier.'
  } else if ((hasTimestampKeyword || profile.valid_date_percent >= 0.9) && !hasBinaryKeyword && profile.inferred_type !== 'boolean') {
    detectedRole = 'Timestamp'
    confidence = hasTimestampKeyword && profile.valid_date_percent >= 0.75 ? 0.99 : 0.84
    reason = 'Parsed as datetime and/or contains a timestamp keyword.'
  } else if (hasTargetKeyword) {
    if (profile.binary_like_percent >= 0.8 || profile.inferred_type === 'boolean') {
      detectedRole = 'Target Column'
      confidence = 0.95
      reason = 'Contains target/label keyword and values look like a target signal.'
    } else if (profile.inferred_type === 'text' && profile.unique_percent <= 0.4) {
      detectedRole = 'Target Column'
      confidence = 0.86
      reason = 'Contains target/label keyword and behaves like a repeated class field.'
    }
  } else if ((hasBinaryKeyword || profile.inferred_type === 'boolean') && profile.binary_like_percent >= 0.8) {
    detectedRole = 'Binary Label'
    confidence = 0.92
    reason = 'Boolean/binary pattern matched.'
  } else if (hasScoreKeyword && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed')) {
    detectedRole = 'Score / Rating'
    confidence = ['0-1', '0-100', '1-5', '1-10'].includes(profile.scale_pattern) ? 0.95 : 0.82
    reason = 'Score keyword matched and values behave like a score.'
  } else if (hasCountKeyword && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed')) {
    detectedRole = 'Count / Activity'
    confidence = profile.integer_like_percent >= 0.7 && (profile.min ?? 0) >= 0 ? 0.9 : 0.76
    reason = 'Count/activity keyword matched and values look like activity counts.'
  } else if ((hasRateKeyword || name.includes('humidity')) && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') && ['0-1', '0-100'].includes(profile.scale_pattern) && (profile.min ?? 0) >= 0) {
    detectedRole = 'Rate / Percentage'
    confidence = hasRateKeyword || name.includes('humidity') ? 0.88 : 0.74
    reason = 'Value range behaves like a bounded percentage or ratio.'
  } else if (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') {
    detectedRole = 'Numeric Measure'
    confidence = 0.85
    reason = 'Continuous numeric sensor or business measurement.'
  } else if (profile.inferred_type === 'text' && profile.unique_percent <= 0.6) {
    detectedRole = 'Categorical Attribute'
    confidence = 0.9
    reason = 'Repeated text values indicate a categorical attribute.'
  } else if (profile.inferred_type === 'text' && (hasTextKeyword || profile.avg_string_length >= 12)) {
    detectedRole = 'Text Attribute'
    confidence = 0.82
    reason = 'String values look like a descriptive text field.'
  }

  if (name.includes('value') && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed')) {
    detectedRole = 'Numeric Measure'
    confidence = Math.max(confidence, 0.9)
    reason = 'Numeric value columns should be treated as measured values, not timestamps.'
  }
  if (name.endsWith('status') && profile.inferred_type === 'text') {
    detectedRole = 'Categorical Attribute'
    confidence = Math.max(confidence, 0.9)
    reason = 'Status values are categorical labels, not binary targets.'
  }
  if (hasBinaryKeyword && (profile.binary_like_percent >= 0.8 || profile.inferred_type === 'boolean')) {
    detectedRole = 'Binary Label'
    confidence = Math.max(confidence, 0.94)
    reason = 'Detected/flag-style columns with boolean values should be treated as binary labels.'
  }
  if (name.includes('tilt_rate')) {
    detectedRole = 'Numeric Measure'
    confidence = 0.92
    reason = 'Tilt rate is a signed rate-of-change measure, so negative values are valid.'
  }

  return { column_name: profile.column_name, detected_role: detectedRole, confidence, reason }
}

function assessRoleFit(profile: ColumnProfile, role: GenericRole, detection: RoleDetection) {
  if (role === detection.detected_role) return { confidence: detection.confidence, reason: detection.reason, lowConfidence: detection.confidence < 0.7 }
  let confidence = 0.35
  let reason = 'Manual override applied, but the current column profile only weakly supports this role.'
  if (role === 'Identifier') {
    confidence = keywordMatch(profile.column_name, IDENTIFIER_KEYWORDS) ? 0.84 : profile.unique_percent >= 0.75 ? 0.86 : 0.48
    reason = keywordMatch(profile.column_name, IDENTIFIER_KEYWORDS)
      ? 'Manual override fits an identifier-like column name even when entities repeat across rows.'
      : profile.unique_percent >= 0.75
        ? 'Manual override fits a high-uniqueness identifier pattern.'
        : 'Identifier override has weak uniqueness support.'
  } else if (role === 'Timestamp') {
    confidence = profile.valid_date_percent >= 0.85 ? 0.92 : 0.34
    reason = profile.valid_date_percent >= 0.85 ? 'Manual override fits a strong datetime parsing pattern.' : 'Timestamp override has weak datetime evidence.'
  } else if (role === 'Numeric Measure') {
    confidence = profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed' ? 0.85 : 0.3
    if (profile.column_name.toLowerCase().includes('tilt_rate')) confidence = 0.92
    reason = confidence >= 0.8 ? 'Manual override fits a continuous numeric measurement pattern.' : 'Numeric Measure override has weak numeric evidence.'
  } else if (role === 'Categorical Attribute') {
    confidence = profile.inferred_type === 'text' && profile.unique_percent <= 0.7 ? 0.88 : 0.4
    reason = confidence >= 0.8 ? 'Manual override fits a repeated categorical text pattern.' : 'Categorical override has weak category evidence.'
  } else if (role === 'Text Attribute') {
    confidence = profile.inferred_type === 'text' ? (profile.avg_string_length >= 12 ? 0.82 : 0.64) : 0.24
    reason = confidence >= 0.75 ? 'Manual override fits a descriptive text field.' : 'Text override has weak descriptive-text evidence.'
  } else if (role === 'Score / Rating') {
    confidence = (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') ? 0.56 : 0.2
    if (keywordMatch(profile.column_name, SCORE_KEYWORDS)) confidence += 0.2
    if (['0-1', '0-100', '1-5', '1-10'].includes(profile.scale_pattern)) confidence += 0.15
    reason = confidence >= 0.8 ? 'Manual override fits score-like naming and scale behavior.' : 'Score override has weak scale or naming evidence.'
  } else if (role === 'Count / Activity') {
    confidence = (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') ? 0.56 : 0.2
    if (keywordMatch(profile.column_name, COUNT_KEYWORDS)) confidence += 0.2
    if ((profile.min ?? 0) >= 0 && profile.integer_like_percent >= 0.7) confidence += 0.15
    reason = confidence >= 0.8 ? 'Manual override fits count-like activity behavior.' : 'Count override has weak integer/count evidence.'
  } else if (role === 'Rate / Percentage') {
    confidence = (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') ? 0.5 : 0.2
    if ((profile.min ?? 0) >= 0 && ['0-1', '0-100'].includes(profile.scale_pattern)) confidence += 0.25
    if (keywordMatch(profile.column_name, RATE_KEYWORDS) || profile.column_name.toLowerCase().includes('humidity')) confidence += 0.12
    reason = confidence >= 0.8 ? 'Manual override fits bounded percentage behavior.' : 'Rate override has weak bounded-scale evidence.'
  } else if (role === 'Binary Label' || role === 'Target Column') {
    confidence = profile.binary_like_percent >= 0.8 || profile.inferred_type === 'boolean' ? 0.9 : 0.34
    if (keywordMatch(profile.column_name, TARGET_KEYWORDS)) confidence += 0.08
    reason = confidence >= 0.8 ? 'Manual override fits binary/target behavior.' : 'Label override has weak binary or target evidence.'
  } else if (role === 'Unknown / Unmapped') {
    confidence = 0.4
    reason = 'Manual override intentionally leaves this column unmapped.'
  }
  return { confidence: clamp(confidence), reason, lowConfidence: confidence < 0.7 }
}

function buildSemanticProfile(profile: ColumnProfile, role: GenericRole): SemanticProfile {
  const detectedScale = profile.scale_pattern
  const detectedUnit = profile.detected_unit
  const valueDirection = inferDirection(profile.column_name, role)
  const meaning =
    role === 'Identifier' ? `${profile.column_name} record identifier`
      : role === 'Timestamp' ? `${profile.column_name} event timestamp`
        : role === 'Score / Rating' ? `${profile.column_name} scored indicator`
          : role === 'Count / Activity' ? `${profile.column_name} activity count`
            : role === 'Rate / Percentage' ? `${profile.column_name} bounded ratio`
              : role === 'Categorical Attribute' ? `${profile.column_name} categorical attribute`
                : role === 'Text Attribute' ? `${profile.column_name} text attribute`
                  : role === 'Binary Label' || role === 'Target Column' ? `${profile.column_name} target signal`
                    : `${profile.column_name} numeric measure`
  return {
    column_name: profile.column_name,
    approved_or_detected_meaning: meaning,
    generic_role: role,
    expected_scale: detectedScale,
    detected_scale: detectedScale,
    expected_unit: detectedUnit,
    detected_unit: detectedUnit,
    value_direction: valueDirection,
    source_columns: [profile.column_name],
    computation_logic: 'direct column profile',
    semantic_signature: `${role.replace(/\s+/g, '_').toLowerCase()}|${detectedScale}|${detectedUnit.replace(/\s+/g, '_')}`,
  }
}

function composeSemanticSignature(profile: SemanticProfile) {
  return [
    profile.generic_role.replace(/\s+/g, '_').toLowerCase(),
    (profile.expected_scale || profile.detected_scale || 'unknown').replace(/\s+/g, '_').toLowerCase(),
    (profile.expected_unit || profile.detected_unit || 'unitless').replace(/\s+/g, '_').toLowerCase(),
  ].join('|')
}

function buildDatasetFingerprint(profiles: ColumnProfile[], semantics: SemanticProfile[]): DatasetFingerprint {
  return {
    column_names: profiles.map((item) => item.column_name),
    roles: semantics.map((item) => item.generic_role),
    types: profiles.map((item) => item.inferred_type),
    scale_patterns: profiles.map((item) => item.scale_pattern),
    important_columns: semantics.filter((item) => ['Identifier', 'Timestamp', 'Target Column', 'Score / Rating', 'Count / Activity', 'Rate / Percentage'].includes(item.generic_role)).map((item) => item.column_name),
  }
}

function similarityRatio(a: string[], b: string[]) {
  if (!a.length || !b.length) return 0
  const bSet = new Set(b.map((item) => item.toLowerCase()))
  const overlap = a.filter((item) => bSet.has(item.toLowerCase())).length
  return overlap / Math.max(a.length, b.length)
}

function matchFamilies(fingerprint: DatasetFingerprint, versions: StoredVersion[]): FamilyMatch[] {
  return versions.map((version) => {
    const fp = version.dataset_fingerprint
    const columnScore = similarityRatio(fingerprint.column_names, fp.column_names)
    const roleScore = similarityRatio(fingerprint.roles, fp.roles)
    const typeScore = similarityRatio(fingerprint.types, fp.types)
    const importantScore = similarityRatio(fingerprint.important_columns, fp.important_columns)
    const scaleScore = similarityRatio(fingerprint.scale_patterns, fp.scale_patterns)
    const match_score = (columnScore * 0.35) + (roleScore * 0.25) + (typeScore * 0.15) + (importantScore * 0.15) + (scaleScore * 0.1)
    return {
      family_id: version.dataset_family_id,
      family_name: version.dataset_name.replace(/_v\d+$/, '') || version.dataset_family_id,
      version_number: version.version_number,
      version_id: version.version_id,
      match_score,
    }
  }).sort((left, right) => right.match_score - left.match_score)
}

function segmentDataset(rows: DatasetRow[], roles: Record<string, GenericRole>) {
  const timestampColumn = Object.keys(roles).find((name) => roles[name] === 'Timestamp')
  if (timestampColumn) {
    const sorted = [...rows].sort((a, b) => (parseDateValue(a[timestampColumn]) ?? 0) - (parseDateValue(b[timestampColumn]) ?? 0))
    return { compared_by: 'time_window', segments: quartileSegments(sorted) }
  }
  const identifierColumn = Object.keys(roles).find((name) => roles[name] === 'Identifier')
  if (identifierColumn) {
    const groups = new Map<string, DatasetRow[]>()
    rows.forEach((row) => {
      const key = String(row[identifierColumn] ?? 'unknown')
      const bucket = groups.get(key) || []
      bucket.push(row)
      groups.set(key, bucket)
    })
    const entries = Array.from(groups.entries()).slice(0, 4)
    if (entries.length >= 2) {
      return {
        compared_by: identifierColumn,
        segments: entries.map(([key, bucket]) => ({ label: key, rows: bucket })),
      }
    }
  }
  return { compared_by: 'row_window', segments: quartileSegments(rows) }
}

function quartileSegments(rows: DatasetRow[]) {
  const size = Math.max(1, Math.ceil(rows.length / 4))
  return [0, 1, 2, 3]
    .map((index) => ({
      label: `Rows ${index * size + 1}-${Math.min(rows.length, (index + 1) * size)}`,
      rows: rows.slice(index * size, (index + 1) * size),
    }))
    .filter((segment) => segment.rows.length > 0)
}

function buildInternalDrift(profiles: ColumnProfile[], roles: Record<string, GenericRole>, rows: DatasetRow[]): InternalDriftResult[] {
  const { compared_by, segments } = segmentDataset(rows, roles)
  return profiles.map((profile) => {
    const role = roles[profile.column_name]
    const segmentSummaries = segments.map((segment) => {
      const segmentProfile = buildColumnProfile(profile.column_name, segment.rows, Object.keys(segment.rows[0] || {}).length || profile.column_count)
      return {
        segment: segment.label,
        scale: segmentProfile.scale_pattern,
        mean: segmentProfile.mean,
        unique_percent: segmentProfile.unique_percent,
      }
    })
    const scaleSet = new Set(segmentSummaries.map((item) => item.scale))
    const meanValues = segmentSummaries.map((item) => item.mean).filter((value): value is number => value != null)
    const meanSpread = meanValues.length ? Math.max(...meanValues) - Math.min(...meanValues) : 0
    let drift_severity: DriftSeverity = 'NONE'
    const evidence: string[] = []
    if (role === 'Identifier') {
      const identifierPatterns = new Set(
        rows
          .map((row) => inferIdentifierPattern(row[profile.column_name]))
          .filter((value) => value !== 'empty'),
      )
      const uniquenessValues = segmentSummaries.map((item) => item.unique_percent)
      const uniquenessSpread = uniquenessValues.length ? Math.max(...uniquenessValues) - Math.min(...uniquenessValues) : 0
      const segmentMissingRatios = segments.map((segment) => {
        const total = segment.rows.length || 1
        const missing = segment.rows.filter((row) => {
          const value = row[profile.column_name]
          return value == null || String(value).trim() === ''
        }).length
        return missing / total
      })
      const missingSpread = segmentMissingRatios.length ? Math.max(...segmentMissingRatios) - Math.min(...segmentMissingRatios) : 0
      if (identifierPatterns.size > 1) {
        drift_severity = 'MODERATE'
        evidence.push(`Identifier format changes across rows: ${Array.from(identifierPatterns).join(', ')}`)
      }
      if (uniquenessSpread > 0.35) {
        drift_severity = drift_severity === 'NONE' ? 'LOW' : drift_severity
        evidence.push(`Identifier uniqueness spread is ${uniquenessSpread.toFixed(2)}.`)
      }
      if (missingSpread > 0.2) {
        drift_severity = 'MODERATE'
        evidence.push(`Identifier missingness varies by ${formatPct(missingSpread)} across segments.`)
      }
      if (!evidence.length) {
        evidence.push('Identifier pattern, missingness, and uniqueness stay consistent across segments.')
      }
      return {
        column_name: profile.column_name,
        compared_by: `${compared_by} (identifier consistency)`,
        segment_summaries: segmentSummaries,
        drift_severity,
        evidence,
        explanation: drift_severity === 'MODERATE'
          ? 'Identifier behavior changes across segments and should be reviewed.'
          : drift_severity === 'LOW'
            ? 'Identifier behavior shows small consistency shifts only.'
            : 'Identifier pattern and coverage are stable across the dataset.',
        recommended_action: drift_severity === 'MODERATE'
          ? 'Review identifier format and completeness before release.'
          : 'No action needed.',
      }
    }
    if (scaleSet.size > 1 && !scaleSet.has('unknown')) {
      drift_severity = 'HIGH'
      evidence.push(`Segments show multiple scale patterns: ${Array.from(scaleSet).join(', ')}`)
    } else if (meanSpread > Math.max(1, Math.abs(profile.mean ?? 0) * 0.35)) {
      drift_severity = 'MODERATE'
      evidence.push(`Segment mean spread is ${meanSpread.toFixed(2)}.`)
    } else if (meanSpread > Math.max(0.5, Math.abs(profile.mean ?? 0) * 0.15)) {
      drift_severity = 'LOW'
      evidence.push(`Segment mean spread is ${meanSpread.toFixed(2)} but scale stays consistent.`)
    } else {
      evidence.push('Segments follow a consistent scale and interpretation.')
    }
    return {
      column_name: profile.column_name,
      compared_by,
      segment_summaries: segmentSummaries,
      drift_severity,
      evidence,
      explanation: drift_severity === 'HIGH'
        ? 'The column appears to change meaning or scale across segments in the same dataset.'
        : drift_severity === 'MODERATE'
          ? 'The column shows noticeable internal movement, but likely keeps the same meaning.'
          : drift_severity === 'LOW'
            ? 'The column has small internal movement only.'
            : 'No internal semantic inconsistency detected.',
      recommended_action: drift_severity === 'HIGH'
        ? 'Quarantine this column until the scale or meaning is standardized.'
        : drift_severity === 'MODERATE'
          ? 'Review the column before release.'
          : 'No action needed.',
    }
  })
}

function findSuggestedRole(profile: ColumnProfile, assignedRole: GenericRole): MappingReviewFinding | null {
  const name = profile.column_name.toLowerCase()
  const hasBinaryKeyword = keywordMatch(name, BINARY_KEYWORDS)
  if (assignedRole === 'Timestamp' && (profile.inferred_type === 'boolean' || profile.binary_like_percent >= 0.8 || hasBinaryKeyword)) {
    return {
      column_name: profile.column_name,
      current_role: assignedRole,
      suggested_role: 'Binary Label',
      reason: `${profile.column_name} looks binary and should not be treated as a timestamp.`,
    }
  }
  if (assignedRole === 'Timestamp' && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed')) {
    return {
      column_name: profile.column_name,
      current_role: assignedRole,
      suggested_role: 'Numeric Measure',
      reason: `${profile.column_name} is numeric and should be treated as a measured value, not a timestamp.`,
    }
  }
  return null
}

function buildExternalDrift(currentSemantics: SemanticProfile[], baselineVersion: StoredVersion | null, currentVersionLabel: string): ExternalDriftResult[] {
  if (!baselineVersion) return []
  const baselineMap = new Map(baselineVersion.semantic_profiles.map((item) => [item.column_name, item]))
  return currentSemantics
    .filter((item) => baselineMap.has(item.column_name))
    .map((item) => {
      const baseline = baselineMap.get(item.column_name)!
      let drift_severity: DriftSeverity = 'NONE'
      const evidence: string[] = []
      if (baseline.generic_role !== item.generic_role) {
        drift_severity = 'HIGH'
        evidence.push(`Role changed from ${baseline.generic_role} to ${item.generic_role}.`)
      } else if (baseline.detected_scale !== item.detected_scale) {
        drift_severity = 'HIGH'
        evidence.push(`Scale changed from ${baseline.detected_scale} to ${item.detected_scale}.`)
      } else if (baseline.detected_unit !== item.detected_unit) {
        drift_severity = 'HIGH'
        evidence.push(`Unit changed from ${baseline.detected_unit} to ${item.detected_unit}.`)
      } else if (baseline.value_direction !== item.value_direction) {
        drift_severity = 'MODERATE'
        evidence.push(`Value direction changed from ${baseline.value_direction} to ${item.value_direction}.`)
      } else {
        evidence.push('Meaning, scale, and unit remain aligned with the baseline.')
      }

      return {
        column_name: item.column_name,
        baseline_version: `v${baselineVersion.version_number}`,
        current_version: currentVersionLabel,
        baseline_meaning: `${baseline.approved_or_detected_meaning} (${baseline.detected_scale})`,
        current_detected_meaning: `${item.approved_or_detected_meaning} (${item.detected_scale})`,
        drift_severity,
        evidence,
        explanation: drift_severity === 'HIGH'
          ? 'A semantic meaning, scale, or unit change was detected against the selected baseline.'
          : drift_severity === 'MODERATE'
            ? 'A softer meaning or direction change was detected against the selected baseline.'
            : 'No external semantic drift detected.',
        recommended_action: drift_severity === 'HIGH'
          ? 'Quarantine or transform current values back to the expected baseline meaning.'
          : drift_severity === 'MODERATE'
            ? 'Review the column before approval.'
            : 'No action needed.',
      }
    })
}

function cleanCategoryValue(value: DatasetValue) {
  return String(value ?? '').trim().toLowerCase()
}

function valueFrequency(values: string[]) {
  const counts = new Map<string, number>()
  values.forEach((value) => {
    counts.set(value, (counts.get(value) || 0) + 1)
  })
  return counts
}

function totalVariationDistance(left: Map<string, number>, right: Map<string, number>) {
  const keys = new Set([...left.keys(), ...right.keys()])
  if (!keys.size) return 0
  let distance = 0
  keys.forEach((key) => {
    distance += Math.abs((left.get(key) || 0) - (right.get(key) || 0))
  })
  return distance / 2
}

function normalizedDistribution(values: string[]) {
  const counts = valueFrequency(values)
  const total = Math.max(1, values.length)
  const normalized = new Map<string, number>()
  counts.forEach((count, key) => {
    normalized.set(key, count / total)
  })
  return normalized
}

function buildStatisticalDrift(
  profiles: ColumnProfile[],
  roles: Record<string, GenericRole>,
  rows: DatasetRow[],
  baselineVersion: StoredVersion | null,
  currentVersionLabel: string,
): StatisticalDriftResult[] {
  if (!baselineVersion) return []
  const baselineRows = baselineVersion.dataset_rows || []
  const baselineProfileMap = new Map((baselineVersion.column_profiles || []).map((item) => [item.column_name, item]))
  return profiles.flatMap((profile) => {
    const role = roles[profile.column_name]
    const currentValues = rows.map((row) => row[profile.column_name]).filter((value) => value != null && String(value).trim() !== '')
    const baselineValues = baselineRows.map((row) => row[profile.column_name]).filter((value) => value != null && String(value).trim() !== '')
    if (!currentValues.length || !baselineValues.length) return []

    const result: StatisticalDriftResult = {
      column_name: profile.column_name,
      baseline_version: `v${baselineVersion.version_number}`,
      current_version: currentVersionLabel,
      field_type: 'categorical',
      drift_severity: 'NONE',
      score: 0,
      evidence: [],
      explanation: 'No statistical drift detected.',
      recommended_action: 'No action needed.',
    }

    if (['Numeric Measure', 'Count / Activity', 'Rate / Percentage', 'Score / Rating'].includes(role) || profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') {
      const currentNumeric = currentValues.map(parseNumberish).filter((value): value is number => value != null)
      const baselineNumeric = baselineValues.map(parseNumberish).filter((value): value is number => value != null)
      if (!currentNumeric.length || !baselineNumeric.length) return []

      const allValues = [...currentNumeric, ...baselineNumeric]
      const min = Math.min(...allValues)
      const max = Math.max(...allValues)
      const binCount = Math.min(10, Math.max(4, Math.round(Math.sqrt(Math.max(currentNumeric.length, baselineNumeric.length)))))
      const buildHistogram = (values: number[]) => {
        const bins = Array.from({ length: binCount }, () => 0)
        const span = max - min || 1
        values.forEach((value) => {
          const rawIndex = Math.floor(((value - min) / span) * binCount)
          const index = Math.min(binCount - 1, Math.max(0, Number.isFinite(rawIndex) ? rawIndex : 0))
          bins[index] += 1
        })
        const total = Math.max(1, values.length)
        return bins.map((count) => count / total)
      }

      const currentHistogram = buildHistogram(currentNumeric)
      const baselineHistogram = buildHistogram(baselineNumeric)
      const tvd = currentHistogram.reduce((sum, value, index) => sum + Math.abs(value - baselineHistogram[index]), 0) / 2
      const currentMean = average(currentNumeric) ?? 0
      const baselineMean = average(baselineNumeric) ?? 0
      const currentStd = stdDev(currentNumeric)
      const baselineStd = stdDev(baselineNumeric)
      const meanDelta = Math.abs(currentMean - baselineMean)
      const stdDelta = Math.abs(currentStd - baselineStd)
      const currentMissing = profile.missing_percent
      const baselineMissing = baselineProfileMap.get(profile.column_name)?.missing_percent ?? 0
      const missingDelta = Math.abs(currentMissing - baselineMissing)
      const rangeDelta = Math.abs((profile.max ?? 0) - (baselineProfileMap.get(profile.column_name)?.max ?? 0))
      let score = Math.max(tvd, 0.05)

      if (missingDelta > 0.15) {
        score = Math.max(score, 0.45)
        result.evidence.push(`Missingness changed by ${formatPct(missingDelta)}.`)
      }
      if (meanDelta > Math.max(1, Math.abs(baselineMean) * 0.4, baselineStd * 0.75)) {
        score = Math.max(score, 0.7)
        result.evidence.push(`Mean shifted from ${safeFixed(baselineMean)} to ${safeFixed(currentMean)}.`)
      } else if (meanDelta > Math.max(0.5, Math.abs(baselineMean) * 0.2, baselineStd * 0.35)) {
        score = Math.max(score, 0.42)
        result.evidence.push(`Mean shifted moderately from ${safeFixed(baselineMean)} to ${safeFixed(currentMean)}.`)
      }
      if (stdDelta > Math.max(1, baselineStd * 0.75)) {
        score = Math.max(score, 0.62)
        result.evidence.push(`Spread changed from ${safeFixed(baselineStd)} to ${safeFixed(currentStd)}.`)
      } else if (stdDelta > Math.max(0.35, baselineStd * 0.3)) {
        score = Math.max(score, 0.34)
        result.evidence.push(`Spread shifted slightly from ${safeFixed(baselineStd)} to ${safeFixed(currentStd)}.`)
      }
      if (rangeDelta > Math.max(2, Math.abs((baselineProfileMap.get(profile.column_name)?.max ?? 0) - (baselineProfileMap.get(profile.column_name)?.min ?? 0)) * 0.35)) {
        score = Math.max(score, 0.5)
        result.evidence.push('Observed value range changed noticeably.')
      }
      if (tvd > 0.4) {
        score = Math.max(score, 0.78)
        result.evidence.push(`Distribution changed materially (distance ${tvd.toFixed(2)}).`)
      } else if (tvd > 0.22) {
        score = Math.max(score, 0.48)
        result.evidence.push(`Distribution changed moderately (distance ${tvd.toFixed(2)}).`)
      } else if (tvd > 0.1) {
        score = Math.max(score, 0.25)
        result.evidence.push(`Distribution shifted slightly (distance ${tvd.toFixed(2)}).`)
      }

      result.field_type = 'numeric'
      result.score = Math.min(1, score)
      if (result.score >= 0.7) result.drift_severity = 'HIGH'
      else if (result.score >= 0.35) result.drift_severity = 'MODERATE'
      else if (result.score >= 0.15) result.drift_severity = 'LOW'
      if (!result.evidence.length) result.evidence.push('Numeric distribution remains aligned with the baseline.')
      result.explanation = result.drift_severity === 'HIGH'
        ? 'Numeric distribution changed materially against the selected baseline.'
        : result.drift_severity === 'MODERATE'
          ? 'Numeric distribution shifted enough to warrant a review.'
          : result.drift_severity === 'LOW'
            ? 'Numeric distribution shifted slightly.'
            : 'No statistical drift detected.'
      result.recommended_action = result.drift_severity === 'HIGH'
        ? 'Investigate the distribution shift before release.'
        : result.drift_severity === 'MODERATE'
          ? 'Review the metric trend and baseline alignment.'
          : 'No action needed.'
      return [result]
    }

    if (['Categorical Attribute', 'Binary Label', 'Target Column', 'Text Attribute'].includes(role)) {
      const currentCategories = currentValues.map(cleanCategoryValue).filter(Boolean)
      const baselineCategories = baselineValues.map(cleanCategoryValue).filter(Boolean)
      if (!currentCategories.length || !baselineCategories.length) return []

      const currentDist = normalizedDistribution(currentCategories)
      const baselineDist = normalizedDistribution(baselineCategories)
      const tvd = totalVariationDistance(currentDist, baselineDist)
      const baselineSet = new Set(baselineCategories)
      const currentSet = new Set(currentCategories)
      const newCategoryRate = currentCategories.filter((value) => !baselineSet.has(value)).length / Math.max(1, currentCategories.length)
      const disappearedRate = baselineCategories.filter((value) => !currentSet.has(value)).length / Math.max(1, baselineCategories.length)
      const currentMode = [...currentDist.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] || 'n/a'
      const baselineMode = [...baselineDist.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] || 'n/a'
      let score = Math.max(tvd, newCategoryRate * 0.75, disappearedRate * 0.65)

      if (newCategoryRate > 0.25) {
        score = Math.max(score, 0.75)
        result.evidence.push(`New categories appeared in ${formatPct(newCategoryRate)} of rows.`)
      } else if (newCategoryRate > 0.1) {
        score = Math.max(score, 0.42)
        result.evidence.push(`Some new categories appeared (${formatPct(newCategoryRate)} of rows).`)
      }
      if (disappearedRate > 0.25) {
        score = Math.max(score, 0.68)
        result.evidence.push(`Baseline categories disappeared in ${formatPct(disappearedRate)} of rows.`)
      } else if (disappearedRate > 0.1) {
        score = Math.max(score, 0.34)
        result.evidence.push(`Some baseline categories disappeared (${formatPct(disappearedRate)} of rows).`)
      }
      if (tvd > 0.45) {
        score = Math.max(score, 0.82)
        result.evidence.push(`Category distribution changed materially (distance ${tvd.toFixed(2)}).`)
      } else if (tvd > 0.25) {
        score = Math.max(score, 0.5)
        result.evidence.push(`Category distribution shifted moderately (distance ${tvd.toFixed(2)}).`)
      } else if (tvd > 0.12) {
        score = Math.max(score, 0.22)
        result.evidence.push(`Category distribution shifted slightly (distance ${tvd.toFixed(2)}).`)
      }
      if (role === 'Binary Label' || role === 'Target Column') {
        if (currentSet.size !== baselineSet.size || [...currentSet].some((value) => !baselineSet.has(value))) {
          score = Math.max(score, 0.7)
          result.evidence.push('Label values changed against the baseline.')
        }
      }

      result.field_type = 'categorical'
      result.score = Math.min(1, score)
      if (result.score >= 0.7) result.drift_severity = 'HIGH'
      else if (result.score >= 0.35) result.drift_severity = 'MODERATE'
      else if (result.score >= 0.15) result.drift_severity = 'LOW'
      if (!result.evidence.length) result.evidence.push(`Categorical distribution remains aligned with the baseline (${baselineMode} -> ${currentMode}).`)
      result.explanation = result.drift_severity === 'HIGH'
        ? 'Categorical distribution changed materially against the selected baseline.'
        : result.drift_severity === 'MODERATE'
          ? 'Categorical distribution shifted enough to warrant a review.'
          : result.drift_severity === 'LOW'
            ? 'Categorical distribution shifted slightly.'
            : 'No statistical drift detected.'
      result.recommended_action = result.drift_severity === 'HIGH'
        ? 'Inspect category churn and baseline alignment before release.'
        : result.drift_severity === 'MODERATE'
          ? 'Review the category distribution change.'
          : 'No action needed.'
      return [result]
    }

    return []
  })
}

function buildBehavioralDrift(
  preReleaseResults: ReleaseResult[],
  baselineVersion: StoredVersion | null,
  currentVersionLabel: string,
): BehavioralDriftResult[] {
  if (!baselineVersion) return []
  const baselineMap = new Map((baselineVersion.release_results || []).map((item) => [item.column_name, item]))
  const statusRank: Record<FeatureStatus, number> = { READY: 0, CONDITIONAL: 1, QUARANTINED: 2 }
  return preReleaseResults.map((item) => {
    const baseline = baselineMap.get(item.column_name)
    if (!baseline) {
      return {
        column_name: item.column_name,
        baseline_version: `v${baselineVersion.version_number}`,
        current_version: currentVersionLabel,
        baseline_release_status: 'READY' as FeatureStatus,
        current_release_status: item.release_status,
        release_status_delta: statusRank[item.release_status],
        drift_severity: 'NONE' as DriftSeverity,
        evidence: ['No baseline release history exists for this column.'],
        explanation: 'No behavioral drift comparison available for this column.',
        recommended_action: 'No action needed.',
      }
    }

    const delta = statusRank[item.release_status] - statusRank[baseline.release_status]
    const failureDelta = item.critical_failures.length - baseline.critical_failures.length
    const warningDelta = item.warnings.length - baseline.warnings.length
    let score = 0
    const evidence: string[] = []

    if (item.release_status !== baseline.release_status) {
      score = Math.max(score, Math.abs(delta) >= 2 ? 0.85 : 0.45)
      evidence.push(`Release status changed from ${baseline.release_status} to ${item.release_status}.`)
    }
    if (failureDelta > 0) {
      score = Math.max(score, failureDelta >= 2 ? 0.8 : 0.5)
      evidence.push(`${failureDelta} additional critical failure${failureDelta === 1 ? '' : 's'} appeared.`)
    }
    if (warningDelta > 0) {
      score = Math.max(score, warningDelta >= 2 ? 0.45 : 0.25)
      evidence.push(`${warningDelta} additional warning${warningDelta === 1 ? '' : 's'} appeared.`)
    }
    if (!evidence.length) evidence.push('Release behavior remains aligned with the baseline.')

    const driftSeverity: DriftSeverity = score >= 0.75 ? 'HIGH' : score >= 0.35 ? 'MODERATE' : score >= 0.15 ? 'LOW' : 'NONE'
    return {
      column_name: item.column_name,
      baseline_version: `v${baselineVersion.version_number}`,
      current_version: currentVersionLabel,
      baseline_release_status: baseline.release_status,
      current_release_status: item.release_status,
      release_status_delta: delta,
      drift_severity: driftSeverity,
      evidence,
      explanation: driftSeverity === 'HIGH'
        ? 'Downstream release behavior changed materially against the baseline.'
        : driftSeverity === 'MODERATE'
          ? 'Downstream release behavior changed enough to review.'
          : driftSeverity === 'LOW'
            ? 'Downstream release behavior shifted slightly.'
            : 'No behavioral drift detected.',
      recommended_action: driftSeverity === 'HIGH'
        ? 'Review the downstream impact before promotion.'
        : driftSeverity === 'MODERATE'
          ? 'Check why the release status changed.'
          : 'No action needed.',
    }
  })
}

function buildReleaseResults(
  profiles: ColumnProfile[],
  roles: Record<string, GenericRole>,
  assessments: Record<string, { confidence: number }>,
  internal: Record<string, InternalDriftResult>,
  external: Record<string, ExternalDriftResult>,
  statistical: Record<string, StatisticalDriftResult>,
  behavioral: Record<string, BehavioralDriftResult>,
) {
  return profiles.map((profile) => {
    const role = roles[profile.column_name]
    const internalSeverity = internal[profile.column_name]?.drift_severity ?? 'NONE'
    const externalSeverity = external[profile.column_name]?.drift_severity ?? 'NONE'
    const statisticalSeverity = statistical[profile.column_name]?.drift_severity ?? 'NONE'
    const behavioralSeverity = behavioral[profile.column_name]?.drift_severity ?? 'NONE'
    const critical_failures: string[] = []
    const warnings: string[] = []

    if (profile.missing_percent > 0.45) critical_failures.push('Severe missingness')
    else if (profile.missing_percent > 0.2) warnings.push('Higher-than-normal missingness')
    if (role === 'Timestamp' && profile.valid_date_percent < 0.75) critical_failures.push('Invalid datetime pattern')
    if (role === 'Count / Activity' && (profile.min ?? 0) < 0) critical_failures.push('Negative count values')
    if (role === 'Rate / Percentage' && !['0-1', '0-100'].includes(profile.scale_pattern)) critical_failures.push('Rate scale is invalid')
    if (role === 'Score / Rating' && !['0-1', '0-100', '1-5', '1-10'].includes(profile.scale_pattern)) critical_failures.push('Score scale is invalid')
    if (assessments[profile.column_name].confidence < 0.7) warnings.push('Weak role confidence')
    if (profile.outlier_percent > 0.2) warnings.push('Outlier warning')
    if (role === 'Unknown / Unmapped') warnings.push('Unknown columns should stay in profiling-only mode')
    if (statisticalSeverity === 'HIGH') critical_failures.push('High statistical drift')
    else if (statisticalSeverity === 'MODERATE') warnings.push('Moderate statistical drift')
    if (behavioralSeverity === 'HIGH') critical_failures.push('High behavioral drift')
    else if (behavioralSeverity === 'MODERATE') warnings.push('Moderate behavioral drift')
    if (statisticalSeverity === 'LOW') warnings.push('Low statistical drift')
    if (behavioralSeverity === 'LOW') warnings.push('Low behavioral drift')

    let validation_status: 'PASS' | 'WARN' | 'FAIL' = 'PASS'
    if (critical_failures.length) validation_status = 'FAIL'
    else if (warnings.length) validation_status = 'WARN'

    let release_status: FeatureStatus = 'READY'
    if (internalSeverity === 'HIGH' || externalSeverity === 'HIGH' || statisticalSeverity === 'HIGH' || behavioralSeverity === 'HIGH' || critical_failures.length) {
      release_status = 'QUARANTINED'
    } else if (internalSeverity === 'MODERATE' || externalSeverity === 'MODERATE' || statisticalSeverity === 'MODERATE' || behavioralSeverity === 'MODERATE' || validation_status === 'WARN') {
      release_status = 'CONDITIONAL'
    }

    const driftEvidence = [
      internal[profile.column_name]?.evidence?.[0],
      external[profile.column_name]?.evidence?.[0],
      statistical[profile.column_name]?.evidence?.[0],
      behavioral[profile.column_name]?.evidence?.[0],
    ].filter(Boolean) as string[]

    const explanation =
      release_status === 'READY'
        ? 'Column meaning is stable and validation checks passed.'
        : release_status === 'CONDITIONAL'
          ? `${warnings[0] || driftEvidence[0] || 'Moderate drift detected'}, admin review recommended.`
          : `${critical_failures[0] || driftEvidence[0] || 'Critical semantic issue detected'}.`

    return {
      column_name: profile.column_name,
      role,
      validation_status,
      internal_drift_severity: internalSeverity,
      external_drift_severity: externalSeverity,
      statistical_drift_severity: statisticalSeverity,
      behavioral_drift_severity: behavioralSeverity,
      release_status,
      critical_failures,
      warnings,
      explanation,
      recommended_action: release_status === 'READY'
        ? 'Approve for governed use.'
        : release_status === 'CONDITIONAL'
          ? 'Review before promotion.'
          : 'Quarantine until the semantic issue is resolved.',
    }
  })
}

/** Upload header -> baseline column when that baseline field exists (drift demos / common renames). */
const BASELINE_COLUMN_UPLOAD_ALIASES: Record<string, string[]> = {
  trend_name: ['label', 'trend_title', 'trendlabel'],
  trend_score: ['momentum_idx', 'heat_index', 'popularity_index'],
  sales_amount: ['sales_amt', 'revenue'],
  quantity: ['qty', 'units'],
  shop_name: ['store_title', 'shop_title'],
  location: ['city_name', 'city'],
  phone_number: ['contact_phone', 'tel'],
  name: ['full_name', 'customer_name', 'product_name'],
  email: ['login_email', 'user_email', 'customer_email'],
  phone: ['contact_phone', 'mobile', 'tel'],
  price_LKR: ['retail_price_lkr', 'unit_price_lkr'],
}

function resolveUploadColumnToBaselineName(uploadCol: string, baselineColumns: string[]): string | null {
  if (baselineColumns.includes(uploadCol)) {
    return uploadCol
  }
  for (const baselineCol of baselineColumns) {
    const aliases = BASELINE_COLUMN_UPLOAD_ALIASES[baselineCol]
    if (aliases?.includes(uploadCol)) {
      return baselineCol
    }
  }
  return null
}

function runVersionSanityCheck(currentColumns: string[], baselineVersion: StoredVersion | null): SanityCheckResult {
  if (!baselineVersion) {
    return {
      passed: true,
      requiredColumns: [],
      importantColumns: [],
      missingColumns: [],
      extraColumns: [],
      columnCountDelta: 0,
    }
  }
  const baselineColumns = baselineVersion.column_names || []
  const coveredBaseline = new Set<string>()
  for (const column of currentColumns) {
    const mapped = resolveUploadColumnToBaselineName(column, baselineColumns)
    if (mapped) {
      coveredBaseline.add(mapped)
    }
  }
  const importantColumns = (baselineVersion.dataset_fingerprint?.important_columns || []).filter(Boolean)
  const requiredColumns = importantColumns.length ? importantColumns : baselineColumns.slice(0, Math.min(5, baselineColumns.length))
  const missingColumns = baselineColumns.filter((column) => !coveredBaseline.has(column))
  const missingImportant = requiredColumns.filter((column) => !coveredBaseline.has(column))
  const extraColumns = currentColumns.filter((column) => resolveUploadColumnToBaselineName(column, baselineColumns) === null)
  const columnCountDelta = Math.abs(currentColumns.length - baselineColumns.length)
  const passed = missingColumns.length === 0 && missingImportant.length === 0 && columnCountDelta <= Math.max(2, Math.ceil(baselineColumns.length * 0.2))
  return {
    passed,
    requiredColumns,
    importantColumns,
    missingColumns,
    extraColumns,
    columnCountDelta,
  }
}

function buildVersionPairComparison(left: StoredVersion | null, right: StoredVersion | null): VersionPairComparison | null {
  if (!left || !right) return null
  const external = buildExternalDrift(right.semantic_profiles || [], left, `v${right.version_number}`)
  const externalMap = external.reduce<Record<string, ExternalDriftResult>>((acc, item) => {
    acc[item.column_name] = item
    return acc
  }, {})
  const releaseByColumn = (right.release_results || []).reduce<Record<string, ReleaseResult>>((acc, row) => {
    acc[row.column_name] = row
    return acc
  }, {})
  const severityCounts = external.reduce((acc, row) => {
    acc[row.drift_severity] += 1
    return acc
  }, { NONE: 0, LOW: 0, MODERATE: 0, HIGH: 0 } as Record<DriftSeverity, number>)
  Object.keys(releaseByColumn).forEach((column) => {
    if (!externalMap[column]) {
      severityCounts.NONE += 1
    }
  })
  return {
    left,
    right,
    external,
    releaseByColumn,
    severityCounts,
    comparedColumns: Math.max(external.length, Object.keys(releaseByColumn).length),
  }
}

function buildDatasetContentSignature(rows: DatasetRow[], fallback?: {
  row_count?: number | null
  column_count?: number | null
  column_names?: string[]
  dataset_fingerprint?: DatasetFingerprint | null
}) {
  if (rows.length) {
    const normalizedRows = rows.map((row) => Object.keys(row).sort().reduce<Record<string, DatasetValue>>((acc, key) => {
      const value = row[key]
      if (value == null) acc[key] = null
      else if (typeof value === 'boolean') acc[key] = value
      else acc[key] = String(value).trim()
      return acc
    }, {}))
    const canonicalRows = normalizedRows
      .map((row) => JSON.stringify(row))
      .sort()
    return JSON.stringify(canonicalRows)
  }
  return JSON.stringify({
    row_count: fallback?.row_count ?? null,
    column_count: fallback?.column_count ?? null,
    column_names: fallback?.column_names || [],
    dataset_fingerprint: fallback?.dataset_fingerprint || null,
  })
}

function readDatasetText(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('Failed to read file'))
    reader.readAsText(file)
  })
}

function parseCsvLine(line: string) {
  const output: string[] = []
  let current = ''
  let quoted = false
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i]
    if (char === '"') {
      const next = line[i + 1]
      if (quoted && next === '"') {
        current += '"'
        i += 1
      } else {
        quoted = !quoted
      }
      continue
    }
    if (char === ',' && !quoted) {
      output.push(current.trim())
      current = ''
      continue
    }
    current += char
  }
  output.push(current.trim())
  return output
}

function parseDelimitedDataset(content: string): DatasetRow[] {
  const lines = content.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (lines.length < 2) return []
  const headers = parseCsvLine(lines[0])
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line)
    return headers.reduce<DatasetRow>((row, header, index) => {
      row[header] = cells[index] ?? ''
      return row
    }, {})
  })
}

function parseJsonDataset(content: string): DatasetRow[] {
  const raw = JSON.parse(content)
  if (Array.isArray(raw)) return raw.filter((item) => item && typeof item === 'object') as DatasetRow[]
  if (raw && Array.isArray(raw.rows)) return raw.rows.filter((item: unknown) => item && typeof item === 'object') as DatasetRow[]
  return []
}

function recommendationCompatibility(semantics: SemanticProfile[]) {
  const names = semantics.map((item) => item.column_name.toLowerCase())
  const hasQuery = names.some((name) => ['query', 'search', 'prompt'].some((word) => name.includes(word)))
  const hasItem = names.some((name) => ['product', 'item', 'name', 'title', 'description'].some((word) => name.includes(word)))
  const hasDescriptor = names.some((name) => ['category', 'style', 'color', 'brand'].some((word) => name.includes(word)))
  const hasPrice = names.some((name) => name.includes('price'))
  const hasBehavior = semantics.some((item) => item.generic_role === 'Count / Activity' || item.generic_role === 'Score / Rating')
  const hasLabel = semantics.some((item) => item.generic_role === 'Binary Label' || item.generic_role === 'Target Column')
  return hasQuery && hasItem && hasBehavior && hasLabel && (hasDescriptor || hasPrice)
}

function confidenceTone(value: number) {
  if (value >= 0.9) return { bg: '#dcfce7', text: '#166534' }
  if (value >= 0.7) return { bg: '#fffbeb', text: '#92400e' }
  return { bg: '#fee2e2', text: '#991b1b' }
}

function releaseTone(status: FeatureStatus) {
  if (status === 'READY') return { bg: '#f0fdf4', text: '#166534', border: '#86efac' }
  if (status === 'CONDITIONAL') return { bg: '#fffbeb', text: '#92400e', border: '#fcd34d' }
  return { bg: '#fef2f2', text: '#991b1b', border: '#fca5a5' }
}

function messageTone(type: StatusMessage['type']) {
  if (type === 'pending') return { bg: '#eff6ff', border: '#bfdbfe', text: '#1d4ed8' }
  if (type === 'success') return { bg: '#f0fdf4', border: '#bbf7d0', text: '#166534' }
  if (type === 'warning') return { bg: '#fffbeb', border: '#fde68a', text: '#92400e' }
  if (type === 'error') return { bg: '#fef2f2', border: '#fecaca', text: '#991b1b' }
  return { bg: '#eff6ff', border: '#bfdbfe', text: '#1d4ed8' }
}

function workflowStatusLabel(status: WorkflowStatus) {
  if (status === 'completed') return 'COMPLETE'
  if (status === 'running') return 'RUNNING'
  if (status === 'skipped') return 'SKIPPED'
  if (status === 'failed') return 'FAILED'
  return 'PENDING'
}

function workflowStatusTone(status: WorkflowStatus) {
  if (status === 'completed') return { bg: '#f0fdf4', border: '#bbf7d0', text: '#166534' }
  if (status === 'running') return { bg: '#eff6ff', border: '#bfdbfe', text: '#1d4ed8' }
  if (status === 'skipped') return { bg: '#f8fafc', border: '#cbd5e1', text: '#475569' }
  if (status === 'failed') return { bg: '#fef2f2', border: '#fecaca', text: '#991b1b' }
  return { bg: '#fff7ed', border: '#fed7aa', text: '#9a3412' }
}

function summarizeReleaseResults(results: ReleaseResult[]) {
  const counts = results.reduce(
    (acc, row) => {
      acc[row.release_status] += 1
      return acc
    },
    { READY: 0, CONDITIONAL: 0, QUARANTINED: 0 } as Record<FeatureStatus, number>
  )
  return `${counts.READY} READY / ${counts.CONDITIONAL} CONDITIONAL / ${counts.QUARANTINED} QUARANTINED`
}

type WorkflowStatus = 'pending' | 'running' | 'completed' | 'skipped' | 'failed'

type WorkflowStep = {
  label: string
  status: WorkflowStatus
  agent: string
  detail: string
  duration: string
  reason?: string
}

function buildWorkflowSteps(mode: 'baseline' | 'version', stage: number, failed = false, columnCount = 0): WorkflowStep[] {
  const baselineSteps: Array<Omit<WorkflowStep, 'status'>> = [
    { label: '1. Dataset Upload', agent: 'Ingestion Agent', detail: 'Uploaded dataset accepted and staged for semantic monitoring.', duration: '0.4s' },
    { label: '2. Column Profiling', agent: 'Profiling Agent', detail: `${columnCount || 0} columns profiled for type, scale, missingness, and patterns.`, duration: '0.9s' },
    { label: '3. Semantic Profile Creation', agent: 'Semantic Profile Agent', detail: 'Generic roles, units, and semantic signatures generated.', duration: '1.0s' },
    { label: '4. Internal Drift Check', agent: 'Semantic Drift Agent', detail: `${columnCount || 0} columns checked inside the uploaded dataset.`, duration: '1.2s' },
    { label: '5. External Drift Check', agent: 'Baseline Comparison Agent', detail: 'Skipped because a brand-new baseline has no previous version to compare against.', duration: 'skipped' },
    { label: '6. Release Gate & Registry Update', agent: 'Release Gate Agent', detail: 'Release decisions recorded and baseline family saved into the registry.', duration: '0.8s' },
  ]
  const versionSteps: Array<Omit<WorkflowStep, 'status'>> = [
    { label: '1. Dataset Upload', agent: 'Ingestion Agent', detail: 'Uploaded dataset accepted and staged for semantic monitoring.', duration: '0.4s' },
    { label: '2. Column Profiling', agent: 'Profiling Agent', detail: `${columnCount || 0} columns profiled for type, scale, missingness, and patterns.`, duration: '0.9s' },
    { label: '3. Semantic Profile Creation', agent: 'Semantic Profile Agent', detail: 'Generic roles, units, and semantic signatures generated.', duration: '1.0s' },
    { label: '4. Internal Drift Check', agent: 'Semantic Drift Agent', detail: `${columnCount || 0} columns checked inside the uploaded dataset.`, duration: '1.2s' },
    { label: '5. External Drift Check', agent: 'Baseline Comparison Agent', detail: 'Current upload compared against the selected saved baseline version.', duration: '1.1s' },
    { label: '6. Release Gate & Registry Update', agent: 'Release Gate Agent', detail: 'Release decisions recorded and new version saved into the registry.', duration: '0.9s' },
  ]
  const steps = mode === 'baseline' ? baselineSteps : versionSteps
  return steps.map((step, index) => {
    const current = index + 1
    if (failed && current === stage) return { ...step, status: 'failed' }
    if (mode === 'baseline' && current === 5) return { ...step, status: 'skipped' }
    if (current < stage) return { ...step, status: 'completed' }
    if (current === stage) return { ...step, status: 'running' }
    return { ...step, status: 'pending' }
  })
}

export type FeatureOpsWorkflowPanelProps = {
  /** Full-page registry / upload timeline (same tables as Open History). Keeps one state tree with DE Workflow. */
  timelineSurface?: boolean
}

export default function FeatureOpsWorkflowPanel({ timelineSurface = false }: FeatureOpsWorkflowPanelProps = {}) {
  const apiBase = getAgenticApiBase()
  const [uploadedRows, setUploadedRows] = useState<DatasetRow[] | null>(null)
  const [datasetName, setDatasetName] = useState('')
  const [datasetError, setDatasetError] = useState<string | null>(null)
  const [manualRoles, setManualRoles] = useState<Record<string, GenericRole | undefined>>({})
  const [manualSemanticOverrides, setManualSemanticOverrides] = useState<Record<string, SemanticProfileOverride>>({})
  const [messages, setMessages] = useState<StatusMessage[]>([])
  const [families, setFamilies] = useState<FamilyRecord[]>([])
  const [familyVersions, setFamilyVersions] = useState<Record<string, StoredVersion[]>>({})
  const [driftRuns, setDriftRuns] = useState<DriftRunRecord[]>([])
  const [selectedFamilyId, setSelectedFamilyId] = useState<string>('')
  const [selectedVersionNumber, setSelectedVersionNumber] = useState<number | null>(null)
  const [viewFamilyId, setViewFamilyId] = useState<string>('')
  const [showFullPreview, setShowFullPreview] = useState(false)
  const [versionNote, setVersionNote] = useState('')
  const [uploadTime, setUploadTime] = useState('')
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showHistoryModal, setShowHistoryModal] = useState(false)
  const [uploadChoiceMode, setUploadChoiceMode] = useState<'select' | 'baseline' | 'version'>('select')
  const [pendingSaveAction, setPendingSaveAction] = useState<{ mode: 'baseline' | 'version'; familyId?: string } | null>(null)
  const [lastRecordedUploadKey, setLastRecordedUploadKey] = useState('')
  const [savingWorkflow, setSavingWorkflow] = useState(false)
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([])
  const [lastWorkflowMode, setLastWorkflowMode] = useState<'baseline' | 'version' | null>(null)
  const [reportText, setReportText] = useState('')
  const [evidenceFilter, setEvidenceFilter] = useState<'All' | 'Drifted' | 'Conditional' | 'Quarantined'>('All')
  const [releaseFilter, setReleaseFilter] = useState<'All' | FeatureStatus>('All')
  const [selectedCompareVersions, setSelectedCompareVersions] = useState<number[]>([])
  const [historyModalViewMode, setHistoryModalViewMode] = useState<'comparison' | 'left' | 'right'>('comparison')
  const [dashboardCompareViewMode, setDashboardCompareViewMode] = useState<'comparison' | 'left' | 'right'>('comparison')
  const [sanityCheckResult, setSanityCheckResult] = useState<SanityCheckResult | null>(null)
  const [duplicateDatasetResult, setDuplicateDatasetResult] = useState<DuplicateDatasetResult | null>(null)
  const [expandedSummaryKey, setExpandedSummaryKey] = useState<string | null>(null)
  const [expandedWorkflowStepKey, setExpandedWorkflowStepKey] = useState<string | null>(null)
  
  // Backend drift detection state
  const [backendDriftResults, setBackendDriftResults] = useState<Record<string, any>>({})
  const [driftDetectionLoading, setDriftDetectionLoading] = useState(false)

  // ML-based orchestrator state (new)
  const [driftAnalysis, setDriftAnalysis] = useState<any>(null)
  const [driftAnalysisLoading, setDriftAnalysisLoading] = useState(false)
  const [driftDetectionError, setDriftDetectionError] = useState<string | null>(null)
  const [predefinedBaselines, setPredefinedBaselines] = useState<PredefinedBaseline[]>([])
  const [selectedPredefinedBaselineKey, setSelectedPredefinedBaselineKey] = useState('')
  const [reviewWorkspaceTab, setReviewWorkspaceTab] = useState<'mapping' | 'drift'>('drift')

  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const pendingVersionFamilyIdRef = useRef<string | null>(null)
  /** When set, the next baseline save prefers the architecture template family name and baseline key */
  const pendingArchitectureTemplateKeyRef = useRef<string | null>(null)

  const datasetRows = uploadedRows ?? []
  const hasUpload = datasetRows.length > 0
  const columns = useMemo(() => Array.from(new Set(datasetRows.flatMap((row) => Object.keys(row)))), [datasetRows])
  const currentDatasetSignature = useMemo(
    () => buildDatasetContentSignature(datasetRows, { row_count: datasetRows.length, column_count: columns.length, column_names: columns }),
    [columns, datasetRows],
  )
  const profiles = useMemo(() => columns.map((column) => buildColumnProfile(column, datasetRows, columns.length)), [columns, datasetRows])
  const detections = useMemo(() => profiles.reduce<Record<string, RoleDetection>>((acc, profile) => {
    acc[profile.column_name] = detectRole(profile)
    return acc
  }, {}), [profiles])
  const roles = useMemo(() => profiles.reduce<Record<string, GenericRole>>((acc, profile) => {
    acc[profile.column_name] = manualRoles[profile.column_name] || detections[profile.column_name].detected_role
    return acc
  }, {}), [detections, manualRoles, profiles])
  const assessments = useMemo(() => profiles.reduce<Record<string, { confidence: number; reason: string; lowConfidence: boolean }>>((acc, profile) => {
    acc[profile.column_name] = assessRoleFit(profile, roles[profile.column_name], detections[profile.column_name])
    return acc
  }, {}), [detections, profiles, roles])
  const mappingReviewFindings = useMemo(
    () => profiles
      .map((profile) => findSuggestedRole(profile, roles[profile.column_name]))
      .filter((item): item is MappingReviewFinding => item != null),
    [profiles, roles],
  )
  const semanticProfiles = useMemo(() => profiles.map((profile) => {
    const baseProfile = buildSemanticProfile(profile, roles[profile.column_name])
    const overrides = manualSemanticOverrides[profile.column_name]
    if (!overrides) return baseProfile
    const merged = { ...baseProfile, ...overrides }
    return {
      ...merged,
      semantic_signature: composeSemanticSignature(merged),
    }
  }), [manualSemanticOverrides, profiles, roles])
  const fingerprint = useMemo(() => buildDatasetFingerprint(profiles, semanticProfiles), [profiles, semanticProfiles])
  const allVersions = useMemo(() => Object.values(familyVersions).flat(), [familyVersions])
  const matches = useMemo(() => matchFamilies(fingerprint, allVersions).slice(0, 3), [allVersions, fingerprint])
  const matchedBaseline = matches[0] || null
  const selectedBaseline = useMemo(() => {
    if (!selectedFamilyId || selectedVersionNumber == null) return null
    return (familyVersions[selectedFamilyId] || []).find((item) => item.version_number === selectedVersionNumber) || null
  }, [familyVersions, selectedFamilyId, selectedVersionNumber])
  const registryLatestVersion = useMemo(() => {
    if (!selectedFamilyId) return null
    const list = familyVersions[selectedFamilyId] || []
    if (!list.length) return null
    return list.reduce((best, item) => (item.version_number > best.version_number ? item : best), list[0])
  }, [familyVersions, selectedFamilyId])
  const externalDriftBaseline = useMemo(() => {
    if (hasUpload && selectedFamilyId && registryLatestVersion) {
      return registryLatestVersion
    }
    return selectedBaseline
  }, [hasUpload, registryLatestVersion, selectedBaseline, selectedFamilyId])
  const internalDrift = useMemo(() => buildInternalDrift(profiles, roles, datasetRows), [datasetRows, profiles, roles])
  const internalMap = useMemo(() => internalDrift.reduce<Record<string, InternalDriftResult>>((acc, item) => {
    acc[item.column_name] = item
    return acc
  }, {}), [internalDrift])
  const statisticalDrift = useMemo(() => buildStatisticalDrift(profiles, roles, datasetRows, externalDriftBaseline, 'current_upload'), [datasetRows, externalDriftBaseline, profiles, roles])
  const statisticalMap = useMemo(() => statisticalDrift.reduce<Record<string, StatisticalDriftResult>>((acc, item) => {
    acc[item.column_name] = item
    return acc
  }, {}), [statisticalDrift])
  const externalDrift = useMemo(() => buildExternalDrift(semanticProfiles, externalDriftBaseline, 'current_upload'), [externalDriftBaseline, semanticProfiles])
  const externalMap = useMemo(() => externalDrift.reduce<Record<string, ExternalDriftResult>>((acc, item) => {
    acc[item.column_name] = item
    return acc
  }, {}), [externalDrift])
  const preBehavioralReleaseResults = useMemo(() => buildReleaseResults(profiles, roles, assessments, internalMap, externalMap, statisticalMap, {}), [assessments, externalMap, internalMap, profiles, roles, statisticalMap])
  const behavioralDrift = useMemo(() => buildBehavioralDrift(preBehavioralReleaseResults, externalDriftBaseline, 'current_upload'), [externalDriftBaseline, preBehavioralReleaseResults])
  const behavioralMap = useMemo(() => behavioralDrift.reduce<Record<string, BehavioralDriftResult>>((acc, item) => {
    acc[item.column_name] = item
    return acc
  }, {}), [behavioralDrift])
  const releaseResults = useMemo(() => buildReleaseResults(profiles, roles, assessments, internalMap, externalMap, statisticalMap, behavioralMap), [assessments, behavioralMap, externalMap, internalMap, profiles, roles, statisticalMap])
  const releaseCounts = useMemo(() => releaseResults.reduce((acc, row) => {
    acc[row.release_status] += 1
    return acc
  }, { READY: 0, CONDITIONAL: 0, QUARANTINED: 0 } as Record<FeatureStatus, number>), [releaseResults])
  const isRecommendationCompatible = useMemo(() => recommendationCompatibility(semanticProfiles), [semanticProfiles])
  const workflowMode = isRecommendationCompatible ? 'Recommendation-compatible' : 'FeatureOps-only'
  const matchedConfidence = matchedBaseline ? Math.round(matchedBaseline.match_score * 100) : 0
  const internalSeverityCounts = useMemo(() => internalDrift.reduce((acc, row) => {
    acc[row.drift_severity] += 1
    return acc
  }, { NONE: 0, LOW: 0, MODERATE: 0, HIGH: 0 } as Record<DriftSeverity, number>), [internalDrift])
  const externalSeverityCounts = useMemo(() => externalDrift.reduce((acc, row) => {
    acc[row.drift_severity] += 1
    return acc
  }, { NONE: 0, LOW: 0, MODERATE: 0, HIGH: 0 } as Record<DriftSeverity, number>), [externalDrift])
  const roleDistribution = useMemo(() => {
    const counts = profiles.reduce((acc, profile) => {
      const role = roles[profile.column_name]
      acc[role] = (acc[role] || 0) + 1
      return acc
    }, {} as Partial<Record<GenericRole, number>>)
    return ROLE_OPTIONS
      .map((role) => ({ role, count: counts[role] || 0 }))
      .filter((item) => item.count > 0)
  }, [profiles, roles])
  const trustScores = useMemo(() => releaseResults.map((row) => {
    const base = Math.round((assessments[row.column_name]?.confidence ?? 0.5) * 100)
    const internalPenalty = row.internal_drift_severity === 'HIGH' ? 35 : row.internal_drift_severity === 'MODERATE' ? 18 : row.internal_drift_severity === 'LOW' ? 6 : 0
    const externalPenalty = row.external_drift_severity === 'HIGH' ? 35 : row.external_drift_severity === 'MODERATE' ? 18 : row.external_drift_severity === 'LOW' ? 6 : 0
    const releasePenalty = row.release_status === 'QUARANTINED' ? 20 : row.release_status === 'CONDITIONAL' ? 8 : 0
    return {
      column_name: row.column_name,
      trust: Math.max(0, Math.min(100, base - internalPenalty - externalPenalty - releasePenalty)),
      release_status: row.release_status,
    }
  }).sort((left, right) => right.trust - left.trust), [assessments, releaseResults])
  const driftEvidenceRows = useMemo(() => releaseResults.map((row) => ({
    column_name: row.column_name,
    role: row.role,
    internal_drift: row.internal_drift_severity,
    external_drift: row.external_drift_severity,
    statistical_drift: row.statistical_drift_severity,
    behavioral_drift: row.behavioral_drift_severity,
    release_status: row.release_status,
    evidence: [
      ...(internalMap[row.column_name]?.evidence || []),
      ...(externalMap[row.column_name]?.evidence || []),
      ...(statisticalMap[row.column_name]?.evidence || []),
      ...(behavioralMap[row.column_name]?.evidence || []),
      ...(row.critical_failures || []),
      ...(row.warnings || []),
    ].filter(Boolean).join(' ') || row.explanation,
  })), [behavioralMap, externalMap, internalMap, releaseResults, statisticalMap])
  const visibleDriftEvidenceRows = useMemo(() => {
    if (evidenceFilter === 'Drifted') {
      return driftEvidenceRows.filter((row) => row.internal_drift !== 'NONE' || row.external_drift !== 'NONE' || row.statistical_drift !== 'NONE' || row.behavioral_drift !== 'NONE')
    }
    if (evidenceFilter === 'Conditional') {
      return driftEvidenceRows.filter((row) => row.release_status === 'CONDITIONAL')
    }
    if (evidenceFilter === 'Quarantined') {
      return driftEvidenceRows.filter((row) => row.release_status === 'QUARANTINED')
    }
    return driftEvidenceRows
  }, [driftEvidenceRows, evidenceFilter])
  const visibleReleaseRows = useMemo(() => {
    if (releaseFilter === 'All') return releaseResults
    return releaseResults.filter((row) => row.release_status === releaseFilter)
  }, [releaseFilter, releaseResults])
  const activeWorkflowType = lastWorkflowMode === 'baseline'
    ? 'Create New Baseline'
    : lastWorkflowMode === 'version'
      ? 'Add New Version'
      : workflowMode
  const overallReleaseStats = useMemo(() => Object.values(familyVersions).flat().reduce(
    (acc, version) => {
      version.release_results.forEach((row) => {
        acc[row.release_status] += 1
      })
      return acc
    },
    { READY: 0, CONDITIONAL: 0, QUARANTINED: 0 } as Record<FeatureStatus, number>,
  ), [familyVersions])
  const totalSavedDatasets = useMemo(() => Object.values(familyVersions).reduce((sum, items) => sum + items.length, 0), [familyVersions])
  /** Version count from family registry records (reliable even when version payloads are still loading). */
  const totalVersionsFromRegistry = useMemo(
    () =>
      families
        .filter((item) => !item.is_architecture_template)
        .reduce((sum, item) => sum + Number(item.version_count ?? (item.versions || []).length ?? 0), 0),
    [families],
  )
  const savedVersionsKpi = useMemo(
    () => Math.max(totalSavedDatasets, totalVersionsFromRegistry),
    [totalSavedDatasets, totalVersionsFromRegistry],
  )
  /** Sum of row_count across loaded registry versions (non-template families only). */
  const totalRegistryRowsFromVersions = useMemo(() => {
    let sum = 0
    for (const family of families) {
      if (family.is_architecture_template) continue
      const fid = family.family_id
      const vers = familyVersions[fid] || []
      for (const v of vers) {
        const n = Number(v.row_count)
        if (Number.isFinite(n)) sum += n
      }
    }
    return sum
  }, [families, familyVersions])
  const uploadEventsTotalRows = useMemo(
    () => driftRuns.reduce((acc, run) => acc + (Number(run.dataset_rows) || 0), 0),
    [driftRuns],
  )
  const registryRowsKpi = useMemo(
    () => (totalRegistryRowsFromVersions > 0 ? totalRegistryRowsFromVersions : uploadEventsTotalRows),
    [totalRegistryRowsFromVersions, uploadEventsTotalRows],
  )
  /** Registry families plus predefined architecture templates not yet represented in the registry (for pickers / modals). */
  const familiesDisplayRows = useMemo(() => {
    const extras = predefinedBaselines
      .filter((pre) => !predefinedTemplateCoveredByRegistry(pre, families))
      .map((pre) => buildArchitectureTemplateFamilyRecord(pre))
    return [...families, ...extras]
  }, [families, predefinedBaselines])
  const registryFamilyCount = useMemo(() => families.filter((item) => !item.is_architecture_template).length, [families])
  const templateFamilyCount = useMemo(() => families.filter((item) => item.is_architecture_template).length, [families])
  const linkedUploadCount = useMemo(() => driftRuns.filter((run) => !!run.family_id).length, [driftRuns])
  const unlinkedUploadCount = useMemo(() => Math.max(0, driftRuns.length - linkedUploadCount), [driftRuns.length, linkedUploadCount])
  const uploadActivitySeries = useMemo(() => {
    const days: string[] = []
    for (let i = 13; i >= 0; i -= 1) {
      const d = new Date()
      d.setDate(d.getDate() - i)
      days.push(d.toISOString().slice(0, 10))
    }
    const counts = days.map((day) => driftRuns.filter((r) => String(r.created_at || '').slice(0, 10) === day).length)
    return { days, counts }
  }, [driftRuns])
  const uploadRowsSparkline = useMemo(() => {
    const sorted = [...driftRuns].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    )
    const raw = sorted.map((r) => {
      const n = Number(r.dataset_rows)
      return Number.isFinite(n) && n > 0 ? Math.min(n, 250_000) : 0
    })
    const tail = raw.slice(-20)
    if (tail.length >= 2) return tail
    return tail.length === 1 ? [0, tail[0]] : [0, 1, 0]
  }, [driftRuns])
  const timelineSparkMax = useMemo(() => Math.max(...uploadRowsSparkline, 1), [uploadRowsSparkline])
  const timelineBarMax = useMemo(() => Math.max(...uploadActivitySeries.counts, 1), [uploadActivitySeries.counts])
  const linkUploadPct = useMemo(
    () => (driftRuns.length ? Math.round((linkedUploadCount / driftRuns.length) * 100) : 0),
    [driftRuns.length, linkedUploadCount],
  )
  const timelineLatestLabel = useMemo(() => {
    let best = 0
    driftRuns.forEach((run) => {
      const ms = new Date(run.created_at).getTime()
      if (!Number.isNaN(ms) && ms > best) best = ms
    })
    families.forEach((family) => {
      if (family.is_architecture_template) return
      const ms = new Date(family.updated_at).getTime()
      if (!Number.isNaN(ms) && ms > best) best = ms
    })
    return best ? new Date(best).toLocaleString('en-GB') : '—'
  }, [driftRuns, families])
  const totalFamilies = families.length
  const isNewBaselineFlow = lastWorkflowMode === 'baseline'
  const viewFamilyVersions = useMemo(() => (viewFamilyId ? (familyVersions[viewFamilyId] || []) : []), [familyVersions, viewFamilyId])
  const comparisonVersions = useMemo(() => {
    if (!viewFamilyId || selectedCompareVersions.length !== 2) return [null, null] as [StoredVersion | null, StoredVersion | null]
    const sortedNums = [...selectedCompareVersions].sort((left, right) => left - right)
    const versions = viewFamilyVersions
    const left = versions.find((item) => item.version_number === sortedNums[0]) || null
    const right = versions.find((item) => item.version_number === sortedNums[1]) || null
    return [left, right] as [StoredVersion | null, StoredVersion | null]
  }, [selectedCompareVersions, viewFamilyVersions, viewFamilyId])
  const versionPairComparison = useMemo(() => buildVersionPairComparison(comparisonVersions[0], comparisonVersions[1]), [comparisonVersions])
  const semanticExportBase = useMemo(() => `${String(apiBase).replace(/\/$/, '')}/semantic-drift/export`, [apiBase])
  const columnDriftExecutiveSummary = useMemo(() => {
    const releaseNeeds = releaseResults.filter((r) => r.release_status !== 'READY')
    const semanticRows = [...internalDrift, ...externalDrift]
    const highSemantic = semanticRows.filter((d) => String(d.drift_severity || '').toUpperCase() === 'HIGH')
    const driftDetected = releaseNeeds.length > 0 || semanticRows.length > 0
    const humanLoopNeeded =
      releaseNeeds.some((r) => r.release_status === 'CONDITIONAL' || r.release_status === 'QUARANTINED')
      || highSemantic.length > 0
    const columnsAtRisk = Array.from(
      new Set([...releaseNeeds.map((r) => r.column_name), ...semanticRows.map((d) => d.column_name)]),
    )
    const healLines = releaseNeeds.slice(0, 14).map((r) => ({
      column: r.column_name,
      action: r.recommended_action || r.explanation || 'Review mapping and baseline alignment.',
    }))
    const baselineRows = externalDriftBaseline && typeof (externalDriftBaseline as any).row_count === 'number'
      ? Number((externalDriftBaseline as any).row_count)
      : null
    const uploadRows = datasetRows.length
    const rowDeltaVsBaseline =
      baselineRows != null && uploadRows >= 0 ? uploadRows - baselineRows : null
    return {
      driftDetected,
      humanLoopNeeded,
      columnsAtRisk,
      healLines,
      baselineRows,
      uploadRows,
      rowDeltaVsBaseline,
    }
  }, [datasetRows.length, externalDriftBaseline, externalDrift, internalDrift, releaseResults])
  const approvedBaselineColumns = useMemo(
    () => (Array.isArray(driftAnalysis?.baseline_creation) ? driftAnalysis.baseline_creation : []),
    [driftAnalysis],
  )
  const newDatasetProfilingRows = useMemo(
    () => (Array.isArray(driftAnalysis?.new_dataset_profiling) ? driftAnalysis.new_dataset_profiling : []),
    [driftAnalysis],
  )
  const columnMatchingRows = useMemo(
    () => (Array.isArray(driftAnalysis?.column_matching) ? driftAnalysis.column_matching : []),
    [driftAnalysis],
  )
  const selectedPredefinedBaseline = useMemo(
    () => predefinedBaselines.find((item) => item.baseline_key === selectedPredefinedBaselineKey) || null,
    [predefinedBaselines, selectedPredefinedBaselineKey],
  )

  function buildStoredVersionSignature(version: StoredVersion) {
    return buildDatasetContentSignature(version.dataset_rows || [], {
      row_count: version.row_count,
      column_count: version.column_count,
      column_names: version.column_names,
      dataset_fingerprint: version.dataset_fingerprint,
    })
  }

  function findDuplicateVersionInFamily(
    familyId: string,
    candidateSignature = currentDatasetSignature,
  ) {
    return (familyVersions[familyId] || []).find((version) => buildStoredVersionSignature(version) === candidateSignature) || null
  }

  function pushMessage(message: string, type: StatusMessage['type'] = 'info') {
    setMessages((previous) => [
      ...previous,
      {
        id: `${Date.now()}_${previous.length}`,
        ts: new Date().toISOString(),
        type,
        message,
      },
    ])
  }

  // Backend drift detection integration
  async function fetchInternalDriftFromBackend(datasetName: string, rows: DatasetRow[]) {
    try {
      setDriftDetectionLoading(true)
      setDriftDetectionError(null)
      const result = await detectInternalDrift(apiBase, datasetName, rows)
      setBackendDriftResults((prev) => ({
        ...prev,
        [`internal_${datasetName}`]: result,
      }))
      pushMessage(`Internal drift detected: ${result.severity}`, 'info')
      return result
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error'
      setDriftDetectionError(errorMsg)
      pushMessage(`Drift detection error: ${errorMsg}`, 'error')
      return null
    } finally {
      setDriftDetectionLoading(false)
    }
  }

  async function fetchExternalDriftFromBackend(
    datasetName: string,
    baselineVersion: string,
    currentVersion: string,
    baselineRows: DatasetRow[],
    currentRows: DatasetRow[]
  ) {
    try {
      setDriftDetectionLoading(true)
      setDriftDetectionError(null)
      const result = await detectExternalDrift(
        apiBase,
        datasetName,
        baselineVersion,
        currentVersion,
        baselineRows,
        currentRows
      )
      const resultKey = `external_${datasetName}_${baselineVersion}_${currentVersion}`
      setBackendDriftResults((prev) => ({
        ...prev,
        [resultKey]: result,
      }))
      pushMessage(`External drift detected: ${result.severity}`, 'info')
      return result
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error'
      setDriftDetectionError(errorMsg)
      pushMessage(`External drift detection error: ${errorMsg}`, 'error')
      return null
    } finally {
      setDriftDetectionLoading(false)
    }
  }

  function rowsToJsonFile(rows: DatasetRow[], name: string) {
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' })
    return new File([blob], name.toLowerCase().endsWith('.json') ? name : `${name.replace(/\.[^.]+$/, '') || 'dataset'}.json`, {
      type: 'application/json',
    })
  }

  async function runLearnedDriftAnalysis(file: File, baselineKey?: string) {
    try {
      setDriftAnalysisLoading(true)
      setDriftDetectionError(null)
      const analysis = await detectDriftFull(apiBase, file, baselineKey)
      setDriftAnalysis(analysis)
      if (analysis?.selected_predefined_baseline?.baseline_key) {
        setSelectedPredefinedBaselineKey(analysis.selected_predefined_baseline.baseline_key)
      }
      setReviewWorkspaceTab('drift')
      pushMessage(`Learned twin-baseline triage completed: ${analysis.final_label}.`, analysis.final_label === 'QUARANTINED' ? 'warning' : 'success')
      return analysis
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown learned drift analysis error'
      setDriftDetectionError(errorMsg)
      setDriftAnalysis(null)
      pushMessage(`Learned drift analysis failed: ${errorMsg}`, 'error')
      return null
    } finally {
      setDriftAnalysisLoading(false)
    }
  }

  async function runLearnedDriftAnalysisFromRows(name: string, rows: DatasetRow[], baselineKey?: string) {
    return runLearnedDriftAnalysis(rowsToJsonFile(rows, name), baselineKey)
  }

  async function syncLearnedInternalBaseline(name: string, rows: DatasetRow[]) {
    try {
      await setOrchestratorBaseline(apiBase, 'internal', name, rows)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unable to update internal learned baseline'
      pushMessage(errorMsg, 'warning')
    }
  }

  async function applyPredefinedBaselineToCurrentUpload(nextBaselineKey: string) {
    setSelectedPredefinedBaselineKey(nextBaselineKey)
    if (!uploadedRows?.length || !datasetName) return
    await runLearnedDriftAnalysisFromRows(datasetName, uploadedRows, nextBaselineKey || undefined)
    pushMessage(
      nextBaselineKey
        ? `Applied ${nextBaselineKey} baseline template to the current upload.`
        : 'Cleared the predefined baseline template for the current upload.',
      'info',
    )
  }

  function resetWorkflowState() {
    setManualRoles({})
    setManualSemanticOverrides({})
    setSelectedFamilyId('')
    setSelectedVersionNumber(null)
    setViewFamilyId('')
    setShowFullPreview(false)
    setVersionNote('')
    setWorkflowSteps([])
    setLastWorkflowMode(null)
    setReportText('')
    setEvidenceFilter('All')
    setReleaseFilter('All')
    setSelectedCompareVersions([])
    setHistoryModalViewMode('comparison')
    setDashboardCompareViewMode('comparison')
    setSanityCheckResult(null)
    setDuplicateDatasetResult(null)
    setBackendDriftResults({})
    setDriftAnalysis(null)
    setDriftDetectionError(null)
  }

  function openFilePickerForBaseline() {
    pendingVersionFamilyIdRef.current = null
    pendingArchitectureTemplateKeyRef.current = null
    setUploadChoiceMode('baseline')
    setDatasetError(null)
    fileInputRef.current?.click()
  }

  function openFilePickerForArchitectureTemplate(baselineKey: string) {
    pendingVersionFamilyIdRef.current = null
    pendingArchitectureTemplateKeyRef.current = baselineKey
    setSelectedPredefinedBaselineKey(baselineKey)
    setUploadChoiceMode('baseline')
    setDatasetError(null)
    fileInputRef.current?.click()
  }

  function openFilePickerForVersion(familyId: string) {
    if (familyId.startsWith(ARCH_TEMPLATE_FAMILY_PREFIX)) {
      const baselineKey = familyId.slice(ARCH_TEMPLATE_FAMILY_PREFIX.length)
      openFilePickerForArchitectureTemplate(baselineKey)
      return
    }
    pendingArchitectureTemplateKeyRef.current = null
    pendingVersionFamilyIdRef.current = familyId
    setSelectedFamilyId(familyId)
    const family = families.find((item) => item.family_id === familyId)
    setSelectedVersionNumber(family?.approved_baseline_version || family?.latest_version || null)
    setUploadChoiceMode('version')
    setDatasetError(null)
    fileInputRef.current?.click()
  }

  function normalizeFamilyName(value: string) {
    return value.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase()
  }

  function buildFeatureOpsReport(mode: 'baseline' | 'version', savedLabel: string, steps: WorkflowStep[] = workflowSteps) {
    const lines: string[] = []
    lines.push('FeatureOps Semantic Drift Report')
    lines.push(`Generated: ${new Date().toLocaleString('en-GB')}`)
    lines.push(`Dataset: ${datasetName}`)
    lines.push(`Saved as: ${savedLabel}`)
    lines.push(`Workflow: ${mode === 'baseline' ? 'Create New Baseline' : 'Add New Version'}`)
    lines.push(`Rows: ${datasetRows.length}`)
    lines.push(`Columns: ${columns.length}`)
    lines.push(`Release Summary: ${summarizeReleaseResults(releaseResults)}`)
    lines.push('')
    lines.push('Processing Progress')
    steps.forEach((step) => {
      lines.push(`${step.label} | ${step.status} | ${step.agent}${step.reason ? ` | ${step.reason}` : ''}`)
    })
    lines.push('')
    lines.push('Agents Worked')
    const reportAgents = Array.from(new Map(steps.map((step) => [step.agent, step.status])).entries())
    reportAgents.forEach(([agent, status]) => {
      lines.push(`${agent}: ${status}`)
    })
    return lines.join('\n')
  }

  function downloadFeatureOpsReport() {
    if (!reportText.trim()) return
    const blob = new Blob([reportText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `featureops_report_${Date.now()}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  function downloadCurrentUploadCsv() {
    if (!columns.length || !datasetRows.length) {
      pushMessage('Nothing to export — load or upload rows first.', 'warning')
      return
    }
    const esc = (v: DatasetValue) => {
      if (v == null) return ''
      const s = String(v)
      if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
      return s
    }
    const header = columns.join(',')
    const body = datasetRows.map((row) => columns.map((c) => esc(row[c] ?? null)).join(',')).join('\n')
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(datasetName || 'featureops-upload').replace(/[^\w.-]+/g, '_')}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    pushMessage('Current upload CSV download started.', 'success')
  }

  async function loadFamilies() {
    try {
      const response = await fetch(`${apiBase}/featureops/families`)
      const payload = await response.json()
      if (payload.status === 'ok') {
        setFamilies(payload.families || [])
        const versionsMap: Record<string, StoredVersion[]> = {}
        await Promise.all((payload.families || []).map(async (family: FamilyRecord) => {
          if (family.is_architecture_template) {
            versionsMap[family.family_id] = []
            return
          }
          const versionResponse = await fetch(`${apiBase}/featureops/families/${family.family_id}/versions`)
          const versionPayload = await versionResponse.json()
          versionsMap[family.family_id] = (versionPayload.versions || []).sort((a: StoredVersion, b: StoredVersion) => b.version_number - a.version_number)
        }))
        setFamilyVersions(versionsMap)
      }
      const runsResponse = await fetch(`${apiBase}/featureops/drift-runs`)
      const runsPayload = await runsResponse.json()
      if (runsPayload.status === 'ok') {
        setDriftRuns((runsPayload.runs || []).slice().reverse())
      }
    } catch (error) {
      pushMessage(`Unable to load FeatureOps history: ${String(error)}`, 'error')
    }
  }

  function toggleCompareVersion(versionNumber: number) {
    setSelectedCompareVersions((previous) => {
      if (previous.includes(versionNumber)) {
        return previous.filter((value) => value !== versionNumber)
      }
      if (previous.length >= 2) {
        return [...previous.slice(1), versionNumber].sort((left, right) => left - right)
      }
      return [...previous, versionNumber].sort((left, right) => left - right)
    })
  }

  useEffect(() => {
    void loadFamilies()
  }, [])

  useEffect(() => {
    if (timelineSurface) setShowHistoryModal(false)
  }, [timelineSurface])

  useEffect(() => {
    let cancelled = false
    async function loadPredefinedBaselineOptions() {
      try {
        const payload = await getPredefinedBaselines(apiBase)
        if (cancelled) return
        setPredefinedBaselines(Array.isArray(payload?.baselines) ? payload.baselines : [])
      } catch (error) {
        if (cancelled) return
        pushMessage('Unable to load predefined data architecture baselines.', 'warning')
      }
    }
    void loadPredefinedBaselineOptions()
    return () => {
      cancelled = true
    }
  }, [apiBase])

  useEffect(() => {
    if (!hasUpload) return
    if (matchedBaseline) {
      pushMessage(`Baseline match found: ${matchedBaseline.family_name}, ${Math.round(matchedBaseline.match_score * 100)}%.`, matchedBaseline.match_score >= 0.75 ? 'success' : 'warning')
      setSelectedFamilyId((current) => current || matchedBaseline.family_id)
      setSelectedVersionNumber((current) => current ?? matchedBaseline.version_number)
    } else {
      pushMessage('No strong baseline match found. You can save this upload as a new dataset family baseline.', 'warning')
    }
  }, [hasUpload, matchedBaseline])

  useEffect(() => {
    if (!hasUpload || !pendingSaveAction) return
    if (pendingSaveAction.mode === 'baseline') {
      void saveAsNewBaseline()
    } else if (pendingSaveAction.mode === 'version' && pendingSaveAction.familyId) {
      setSelectedFamilyId(pendingSaveAction.familyId)
      void addAsNewVersion(pendingSaveAction.familyId)
    }
    setPendingSaveAction(null)
  }, [hasUpload, pendingSaveAction])

  useEffect(() => {
    if (!hasUpload || !datasetName || !uploadTime) return
    const uploadKey = `${datasetName}_${uploadTime}`
    if (lastRecordedUploadKey === uploadKey) return
    const familyIdForRun = (selectedFamilyId && selectedFamilyId.trim()) || matchedBaseline?.family_id || null
    const versionNumberForRun = selectedVersionNumber ?? matchedBaseline?.version_number ?? null
    const versionIdForRun =
      selectedBaseline?.version_id
      || (familyIdForRun && versionNumberForRun != null ? `${familyIdForRun}_v${versionNumberForRun}` : null)
    const payload = {
      dataset_name: datasetName,
      family_id: familyIdForRun,
      version_id: versionIdForRun,
      version_number: versionNumberForRun,
      created_at: uploadTime,
      dataset_rows: datasetRows,
      dataset_fingerprint: fingerprint,
      internal_drift_results: internalDrift,
      external_drift_results: externalDrift,
      release_results: releaseResults,
    }
    void fetch(`${apiBase}/featureops/drift-runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(async (response) => {
      const result = await response.json()
      if (result.status === 'ok') {
        setLastRecordedUploadKey(uploadKey)
        await loadFamilies()
      }
    }).catch(() => {})
  }, [
    apiBase,
    datasetName,
    externalDrift,
    fingerprint,
    hasUpload,
    internalDrift,
    lastRecordedUploadKey,
    matchedBaseline,
    releaseResults,
    selectedBaseline,
    selectedFamilyId,
    selectedVersionNumber,
    uploadTime,
  ])

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const targetFamilyId = pendingVersionFamilyIdRef.current
    pendingVersionFamilyIdRef.current = null
    try {
      const content = await readDatasetText(file)
      const parsed = file.name.toLowerCase().endsWith('.json') ? parseJsonDataset(content) : parseDelimitedDataset(content)
      if (!parsed.length) {
        setDatasetError('No usable rows were found. Upload a CSV or JSON array with at least one row.')
        setUploadedRows(null)
        return
      }
      const cols = Array.from(new Set(parsed.flatMap((row) => Object.keys(row))))
      const uploadedSignature = buildDatasetContentSignature(parsed, {
        row_count: parsed.length,
        column_count: cols.length,
        column_names: cols,
      })

      if (targetFamilyId) {
        const suggestedBaselineKey = suggestPredefinedBaselineKey(file.name, parsed, predefinedBaselines)
        if (suggestedBaselineKey) {
          setSelectedPredefinedBaselineKey(suggestedBaselineKey)
        }
        const duplicateVersion = findDuplicateVersionInFamily(targetFamilyId, uploadedSignature)
        if (duplicateVersion) {
          const familyName = families.find((item) => item.family_id === targetFamilyId)?.family_name || targetFamilyId
          setDuplicateDatasetResult({
            familyId: targetFamilyId,
            familyName,
            versionNumber: duplicateVersion.version_number,
          })
          setPendingSaveAction(null)
          setShowUploadModal(false)
          setUploadChoiceMode('select')
          setDatasetError(null)
          pushMessage(`Duplicate dataset detected: ${familyName} v${duplicateVersion.version_number}.`, 'warning')
          return
        }
        resetWorkflowState()
        setUploadedRows(parsed)
        setDatasetName(file.name)
        setUploadTime(new Date().toISOString())
        setDatasetError(null)
        setMessages([])
        setShowUploadModal(false)
        setUploadChoiceMode('select')
        setSelectedFamilyId(targetFamilyId)
        const family = families.find((item) => item.family_id === targetFamilyId)
        const baselineNum = family?.approved_baseline_version ?? family?.latest_version ?? null
        setSelectedVersionNumber(baselineNum)
        const vers = familyVersions[targetFamilyId] || []
        const baselineRow = baselineNum != null ? vers.find((item) => item.version_number === baselineNum) : null
        const baselineForSanity = baselineRow || vers[0] || null
        const sanity = runVersionSanityCheck(cols, baselineForSanity)
        if (baselineForSanity?.dataset_rows?.length) {
          await syncLearnedInternalBaseline(baselineForSanity.file_name || baselineForSanity.dataset_name || 'baseline.json', baselineForSanity.dataset_rows)
        }
        void runLearnedDriftAnalysis(file, suggestedBaselineKey || undefined)
        if (!sanity.passed) {
          setSanityCheckResult(sanity)
          setPendingSaveAction(null)
          pushMessage('Basic sanity check failed. The uploaded file has different columns from the selected baseline.', 'error')
        } else {
          setPendingSaveAction({ mode: 'version', familyId: targetFamilyId })
          pushMessage('Dataset uploaded successfully.', 'success')
          pushMessage('Dataset profiled successfully.', 'success')
          pushMessage('Internal semantic consistency check completed.', 'success')
          pushMessage(`External drift checked against registry v${baselineForSanity?.version_number ?? baselineNum ?? '—'}.`, 'info')
        }
      } else {
        const suggestedBaselineKey = suggestPredefinedBaselineKey(file.name, parsed, predefinedBaselines)
        resetWorkflowState()
        setUploadedRows(parsed)
        setDatasetName(file.name)
        setUploadTime(new Date().toISOString())
        setDatasetError(null)
        setMessages([])
        setShowUploadModal(false)
        setUploadChoiceMode('select')
        setPendingSaveAction({ mode: 'baseline' })
        if (suggestedBaselineKey) {
          setSelectedPredefinedBaselineKey(suggestedBaselineKey)
        }
        void runLearnedDriftAnalysis(file, suggestedBaselineKey || undefined)
        pushMessage('Dataset uploaded successfully.', 'success')
        pushMessage('Dataset profiled successfully.', 'success')
        pushMessage('Internal semantic consistency check completed.', 'success')
      }
    } catch (error) {
      setDatasetError(`Unable to read dataset: ${String(error)}`)
      pushMessage('Dataset upload failed.', 'error')
    } finally {
      event.target.value = ''
    }
  }

  function loadDemoDataset() {
    const suggestedBaselineKey = suggestPredefinedBaselineKey(DEMO_NAME, demoDataset, predefinedBaselines)
    resetWorkflowState()
    setUploadedRows(demoDataset)
    setDatasetName(DEMO_NAME)
    setUploadTime(new Date().toISOString())
    setDatasetError(null)
    setMessages([])
    if (suggestedBaselineKey) {
      setSelectedPredefinedBaselineKey(suggestedBaselineKey)
    }
    void runLearnedDriftAnalysisFromRows(DEMO_NAME, demoDataset, suggestedBaselineKey || undefined)
    pushMessage('Dataset uploaded successfully.', 'success')
    pushMessage('Dataset profiled successfully.', 'success')
    pushMessage('Internal semantic consistency check completed.', 'success')
  }

  function clearCurrentUpload() {
    setUploadedRows(null)
    setDatasetName('')
    setUploadTime('')
    setDatasetError(null)
    resetWorkflowState()
    setMessages([])
    pushMessage('Current upload cleared.', 'info')
  }

  async function saveAsNewBaseline() {
    if (!hasUpload) return
    const templateKeyAtSave = pendingArchitectureTemplateKeyRef.current
    const predefTemplate = templateKeyAtSave ? predefinedBaselines.find((b) => b.baseline_key === templateKeyAtSave) : undefined
    const stemName = datasetName.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
    const familyName =
      (predefTemplate?.dataset_name ? predefTemplate.dataset_name.replace(/_/g, ' ') : stemName) || matchedBaseline?.family_name || 'Uploaded Dataset'
    if (!familyName) {
      pendingArchitectureTemplateKeyRef.current = null
      return
    }
    const idFromTemplate = predefTemplate ? slugifyFamilyId(predefTemplate.dataset_name) : null
    const existingFamily = families.find((item) => {
      if (item.is_architecture_template) return false
      if (normalizeFamilyName(String(item.family_name || '')) === normalizeFamilyName(familyName)) return true
      if (idFromTemplate && item.family_id === idFromTemplate) return true
      return false
    })
    if (existingFamily) {
      const duplicateVersion = findDuplicateVersionInFamily(existingFamily.family_id)
      if (duplicateVersion) {
        setDuplicateDatasetResult({
          familyId: existingFamily.family_id,
          familyName: existingFamily.family_name,
          versionNumber: duplicateVersion.version_number,
        })
        pushMessage(`Duplicate dataset detected: ${existingFamily.family_name} v${duplicateVersion.version_number}.`, 'warning')
        pendingArchitectureTemplateKeyRef.current = null
        return
      }
      const nextBaseline = (familyVersions[existingFamily.family_id] || []).find((item) => item.version_number === (existingFamily.approved_baseline_version || existingFamily.latest_version))
        || (familyVersions[existingFamily.family_id] || [])[0]
        || null
      setSelectedFamilyId(existingFamily.family_id)
      setSelectedVersionNumber(existingFamily.approved_baseline_version || existingFamily.latest_version || null)
      pushMessage(`Family "${existingFamily.family_name}" already exists. Saving this upload as a new version instead.`, 'info')
      await addAsNewVersion(existingFamily.family_id, nextBaseline)
      pendingArchitectureTemplateKeyRef.current = null
      return
    }
    setSavingWorkflow(true)
    setLastWorkflowMode('baseline')
    setWorkflowSteps(buildWorkflowSteps('baseline', 6, false, columns.length))
    pushMessage('Pending: creating new baseline family.', 'pending')
    const payload = {
      dataset_name: datasetName,
      file_name: datasetName,
      family_name: familyName,
      description: predefTemplate?.description || 'Semantic monitoring baseline',
      version_note: 'v1 baseline',
      created_at: uploadTime,
      row_count: datasetRows.length,
      column_count: columns.length,
      column_names: columns,
      dataset_rows: datasetRows,
      dataset_fingerprint: fingerprint,
      column_profiles: profiles,
      semantic_profiles: semanticProfiles,
      internal_drift_results: internalDrift,
      external_drift_results: [],
      statistical_drift_results: statisticalDrift,
      behavioral_drift_results: behavioralDrift,
      release_results: releaseResults,
    }
    try {
      const response = await fetch(`${apiBase}/featureops/families/baseline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await response.json()
      if (result.status === 'ok') {
        const completedSteps = buildWorkflowSteps('baseline', 7, false, columns.length)
        setWorkflowSteps(completedSteps)
        pushMessage(result.message || 'New dataset family baseline created successfully.', 'success')
        pushMessage('FeatureOps registry updated.', 'success')
        await loadFamilies()
        setSelectedFamilyId(result.family?.family_id || '')
        setSelectedVersionNumber(1)
        setViewFamilyId(result.family?.family_id || '')
        setReportText(buildFeatureOpsReport('baseline', `${result.family?.family_name || familyName} v1`, completedSteps))
        setShowUploadModal(false)
        setUploadChoiceMode('select')
      } else {
        setWorkflowSteps(buildWorkflowSteps('baseline', 6, true, columns.length))
        pushMessage(result.detail || result.message || 'Unable to create baseline.', 'error')
      }
    } catch (error) {
      setWorkflowSteps(buildWorkflowSteps('baseline', 6, true, columns.length))
      pushMessage(`Unable to create baseline: ${String(error)}`, 'error')
    } finally {
      pendingArchitectureTemplateKeyRef.current = null
      setSavingWorkflow(false)
    }
  }

  async function addAsNewVersion(targetFamilyId?: string, baselineOverride?: StoredVersion | null) {
    const familyId = targetFamilyId || selectedFamilyId
    if (!familyId || !hasUpload) return
    const duplicateVersion = findDuplicateVersionInFamily(familyId)
    if (duplicateVersion) {
      const familyName = families.find((item) => item.family_id === familyId)?.family_name || familyId
      setDuplicateDatasetResult({
        familyId,
        familyName,
        versionNumber: duplicateVersion.version_number,
      })
      pushMessage(`Duplicate dataset detected: ${familyName} v${duplicateVersion.version_number}.`, 'warning')
      return
    }
    const baselineToCheck = baselineOverride || (familyId === selectedFamilyId ? selectedBaseline : null) || (familyVersions[familyId] || [])[0] || null
    const sanity = runVersionSanityCheck(columns, baselineToCheck)
    if (!sanity.passed) {
      setSanityCheckResult(sanity)
      pushMessage('Basic sanity check failed. The uploaded file has different columns from the selected baseline.', 'error')
      return
    }
    const note = versionNote || 'Semantic drift follow-up version'
    setSavingWorkflow(true)
    setLastWorkflowMode('version')
    setWorkflowSteps(buildWorkflowSteps('version', 6, false, columns.length))
    pushMessage('Pending: saving dataset as a new version.', 'pending')
    const payload = {
      dataset_name: datasetName,
      file_name: datasetName,
      family_id: familyId,
      version_note: note || undefined,
      created_at: uploadTime,
      row_count: datasetRows.length,
      column_count: columns.length,
      column_names: columns,
      dataset_rows: datasetRows,
      dataset_fingerprint: fingerprint,
      column_profiles: profiles,
      semantic_profiles: semanticProfiles,
      internal_drift_results: internalDrift,
      external_drift_results: externalDrift,
      statistical_drift_results: statisticalDrift,
      behavioral_drift_results: behavioralDrift,
      release_results: releaseResults,
    }
    try {
      const response = await fetch(`${apiBase}/featureops/families/${familyId}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await response.json()
      if (result.status === 'ok') {
        const completedSteps = buildWorkflowSteps('version', 7, false, columns.length)
        setWorkflowSteps(completedSteps)
        pushMessage('External semantic drift comparison completed.', 'success')
        pushMessage(result.message || 'Dataset added as a new version.', 'success')
        pushMessage('FeatureOps registry updated.', 'success')
        await loadFamilies()
        setSelectedFamilyId(familyId)
        setSelectedVersionNumber(result.version?.version_number || null)
        setViewFamilyId(familyId)
        setReportText(buildFeatureOpsReport('version', `${result.version?.family_name || familyId} v${result.version?.version_number || ''}`, completedSteps))
        setShowUploadModal(false)
        setUploadChoiceMode('select')
      } else {
        setWorkflowSteps(buildWorkflowSteps('version', 6, true, columns.length))
        pushMessage(result.detail || result.message || 'Unable to add version.', 'error')
      }
    } catch (error) {
      setWorkflowSteps(buildWorkflowSteps('version', 6, true, columns.length))
      pushMessage(`Unable to add version: ${String(error)}`, 'error')
    } finally {
      setSavingWorkflow(false)
    }
  }

  async function recordDriftRun() {
    if (!hasUpload) return
    if (!selectedBaseline) {
      pushMessage('External drift skipped because no baseline was selected.', 'warning')
      return
    }
    pushMessage('External semantic drift comparison started.', 'info')
    const payload = {
      dataset_name: datasetName,
      family_id: selectedFamilyId || null,
      version_id: selectedBaseline?.version_id || null,
      version_number: selectedBaseline?.version_number || null,
      created_at: uploadTime,
      dataset_rows: datasetRows,
      dataset_fingerprint: fingerprint,
      internal_drift_results: internalDrift,
      external_drift_results: externalDrift,
      statistical_drift_results: statisticalDrift,
      behavioral_drift_results: behavioralDrift,
      release_results: releaseResults,
    }
    const response = await fetch(`${apiBase}/featureops/drift-runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const result = await response.json()
    if (result.status === 'ok') {
      pushMessage('External semantic drift comparison completed.', 'success')
      pushMessage('Release gate completed.', 'success')
      pushMessage(result.message || 'FeatureOps registry updated.', 'success')
    }
  }

  async function loadVersion(familyId: string, versionNumber: number) {
    const response = await fetch(`${apiBase}/featureops/families/${familyId}/versions/${versionNumber}`)
    const payload = await response.json()
    if (payload.status === 'ok') {
      if (payload.version?.dataset_rows?.length) {
        resetWorkflowState()
        setUploadedRows(payload.version.dataset_rows)
        setDatasetName(payload.version.file_name || payload.version.dataset_name || '')
        setUploadTime(payload.version.created_at || '')
        setDatasetError(null)
        await syncLearnedInternalBaseline(payload.version.file_name || payload.version.dataset_name || 'baseline.json', payload.version.dataset_rows)
        void runLearnedDriftAnalysisFromRows(payload.version.file_name || payload.version.dataset_name || 'dataset.json', payload.version.dataset_rows)
      }
      setSelectedFamilyId(familyId)
      setSelectedVersionNumber(versionNumber)
      setViewFamilyId(familyId)
      setLastWorkflowMode('version')
      pushMessage('Saved dataset version loaded successfully.', 'success')
    }
  }

  async function loadDriftRun(run: DriftRunRecord) {
    if (run.dataset_rows?.length) {
      resetWorkflowState()
      setUploadedRows(run.dataset_rows)
      setDatasetName(run.dataset_name)
      setUploadTime(run.created_at)
      setDatasetError(null)
      await syncLearnedInternalBaseline(run.dataset_name || 'baseline.json', run.dataset_rows)
      void runLearnedDriftAnalysisFromRows(run.dataset_name || 'dataset.json', run.dataset_rows)
      if (run.family_id) {
        setSelectedFamilyId(run.family_id)
      }
      pushMessage('Uploaded dataset restored from history.', 'success')
    } else {
      pushMessage('This history record does not include dataset rows to reload.', 'warning')
    }
  }

  async function approveVersion(familyId: string, versionNumber: number) {
    const response = await fetch(`${apiBase}/featureops/families/${familyId}/versions/${versionNumber}/approve`, {
      method: 'POST',
    })
    const payload = await response.json()
    if (payload.status === 'ok') {
      pushMessage(payload.message || 'Approved baseline updated.', 'success')
      await loadFamilies()
    }
  }

  async function deleteVersion(familyId: string, versionNumber: number) {
    pushMessage(`Pending: deleting version v${versionNumber}.`, 'pending')
    const response = await fetch(`${apiBase}/featureops/families/${familyId}/versions/${versionNumber}`, {
      method: 'DELETE',
    })
    const payload = await response.json()
    if (payload.status === 'ok') {
      pushMessage(payload.message || `Version v${versionNumber} deleted.`, 'success')
      setSelectedCompareVersions((previous) => previous.filter((value) => value !== versionNumber))
      if (selectedFamilyId === familyId && selectedVersionNumber === versionNumber) {
        setUploadedRows(null)
        setDatasetName('')
        setUploadTime('')
        setDatasetError(null)
        setLastWorkflowMode(null)
        setSelectedVersionNumber(null)
      }
      if (payload.result?.family_deleted) {
        if (viewFamilyId === familyId) setViewFamilyId('')
        if (selectedFamilyId === familyId) {
          setSelectedFamilyId('')
          setSelectedVersionNumber(null)
        }
      } else if (selectedVersionNumber === versionNumber) {
        setSelectedVersionNumber(null)
      }
      await loadFamilies()
    } else {
      pushMessage(payload.detail || 'Unable to delete dataset version.', 'error')
    }
  }

  async function deleteFamily(familyId: string) {
    const familyName = families.find((item) => item.family_id === familyId)?.family_name || familyId
    pushMessage(`Pending: deleting dataset family "${familyName}".`, 'pending')
    const response = await fetch(`${apiBase}/featureops/families/${familyId}`, {
      method: 'DELETE',
    })
    const payload = await response.json()
    if (payload.status === 'ok') {
      pushMessage(payload.message || 'Dataset family deleted successfully.', 'success')
      setSelectedCompareVersions([])
      if (viewFamilyId === familyId) setViewFamilyId('')
      if (selectedFamilyId === familyId) {
        setSelectedFamilyId('')
        setSelectedVersionNumber(null)
      }
      await loadFamilies()
    } else {
      pushMessage(payload.detail || 'Unable to delete dataset family.', 'error')
    }
  }

  async function deleteDriftRun(runId: string) {
    pushMessage('Pending: deleting upload history record.', 'pending')
    const runToDelete = driftRuns.find((item) => item.run_id === runId) || null
    const linkedVersion = runToDelete?.family_id
      ? (familyVersions[runToDelete.family_id] || []).find((version) =>
          version.created_at === runToDelete.created_at
          && (version.file_name === runToDelete.dataset_name || version.dataset_name === runToDelete.dataset_name),
        ) || null
      : null
    if (linkedVersion && runToDelete?.family_id) {
      await deleteVersion(runToDelete.family_id, linkedVersion.version_number)
      await fetch(`${apiBase}/featureops/drift-runs/${runId}`, { method: 'DELETE' }).catch(() => null)
      if (datasetName === runToDelete.dataset_name && uploadTime === runToDelete.created_at) {
        setUploadedRows(null)
        setDatasetName('')
        setUploadTime('')
        setDatasetError(null)
        setLastWorkflowMode(null)
      }
      await loadFamilies()
      return
    }
    const response = await fetch(`${apiBase}/featureops/drift-runs/${runId}`, {
      method: 'DELETE',
    })
    const payload = await response.json()
    if (payload.status === 'ok') {
      pushMessage(payload.message || 'Upload history record deleted.', 'success')
      if (runToDelete && datasetName === runToDelete.dataset_name && uploadTime === runToDelete.created_at) {
        setUploadedRows(null)
        setDatasetName('')
        setUploadTime('')
        setDatasetError(null)
        setLastWorkflowMode(null)
      }
      await loadFamilies()
    } else {
      pushMessage(payload.detail || 'Unable to delete upload history record.', 'error')
    }
  }

  return (
    <section
      className="df-dashboard-shell featureops-shell"
      style={{ padding: '12px 0 24px', display: 'grid', gap: 12, width: '100%', maxWidth: 'none', background: timelineSurface ? '#f8fafc' : undefined }}
    >
      <input ref={fileInputRef} type="file" accept=".csv,.json" onChange={handleFileUpload} style={{ display: 'none' }} />
      {timelineSurface && (
        <div style={{ width: '100%', display: 'grid', gap: 12 }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>Dataset registry timeline</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4, lineHeight: 1.5 }}>
              Same tables as <strong>Open History</strong> in DE Workflow—family registry, upload events, and version comparison. Use the top nav to switch sections.
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(168px, 1fr))', gap: 10 }}>
            {[
              ['Registry families', String(registryFamilyCount), 'Saved dataset families (excludes template-only rows).'],
              ['Architecture templates', String(templateFamilyCount), 'Predefined data-architecture baselines in the picker.'],
              [
                'Saved versions',
                String(savedVersionsKpi),
                totalVersionsFromRegistry >= totalSavedDatasets
                  ? 'Version rows summed from family registry (version_count).'
                  : 'Version payloads loaded; also reconciled with registry counts.',
              ],
              [
                'Total rows (data)',
                registryRowsKpi.toLocaleString('en-GB'),
                totalRegistryRowsFromVersions > 0
                  ? 'Sum of row_count across saved registry versions.'
                  : 'No version payloads yet — sum of dataset_rows on upload events as a proxy.',
              ],
              ['Upload events', String(driftRuns.length), 'Drift run records from workflow uploads.'],
              ['Linked uploads', String(linkedUploadCount), 'Upload events tied to a registry family.'],
              ['Latest activity', timelineLatestLabel, 'Newest upload timestamp or family update.'],
            ].map(([label, value, hint]) => (
              <div key={String(label)} style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 4 }}>
                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 700 }}>{label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{value}</div>
                <div style={{ fontSize: 10, color: '#94a3b8', lineHeight: 1.35 }}>{hint}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, width: '100%' }}>
            <div style={{ borderRadius: 12, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Upload activity (14 days)</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 88, paddingTop: 4 }}>
                {uploadActivitySeries.counts.map((c, i) => (
                  <div key={uploadActivitySeries.days[i]} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 0 }}>
                    <div
                      title={`${uploadActivitySeries.days[i]}: ${c} uploads`}
                      style={{
                        width: '100%',
                        maxWidth: 18,
                        margin: '0 auto',
                        height: `${Math.max(6, (c / timelineBarMax) * 72)}px`,
                        borderRadius: 4,
                        background: c > 0 ? 'linear-gradient(180deg, #38bdf8, #2563eb)' : '#e2e8f0',
                      }}
                    />
                    <span style={{ fontSize: 8, color: '#94a3b8', fontWeight: 700 }}>{uploadActivitySeries.days[i].slice(8)}</span>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 10, color: '#64748b' }}>Event-style counts per UTC day (aligned with Data Architecture timeline KPIs).</div>
            </div>

            <div style={{ borderRadius: 12, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Upload size trend (recent)</div>
              <svg width="100%" height="90" viewBox="0 0 200 90" preserveAspectRatio="none" style={{ display: 'block' }}>
                <polygon
                  fill="rgba(124,58,237,0.12)"
                  points={`0,90 ${uploadRowsSparkline
                    .map((v, i) => {
                      const x = (i / Math.max(uploadRowsSparkline.length - 1, 1)) * 200
                      const y = 82 - (v / timelineSparkMax) * 72
                      return `${x},${y}`
                    })
                    .join(' ')} 200,90`}
                />
                <polyline
                  fill="none"
                  stroke="#7c3aed"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  points={uploadRowsSparkline
                    .map((v, i) => {
                      const x = (i / Math.max(uploadRowsSparkline.length - 1, 1)) * 200
                      const y = 82 - (v / timelineSparkMax) * 72
                      return `${x},${y}`
                    })
                    .join(' ')}
                />
              </svg>
              <div style={{ fontSize: 10, color: '#64748b' }}>Rows per upload event (capped for scale). Flat line means missing row counts on older runs.</div>
            </div>

            <div style={{ borderRadius: 12, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Linked vs unlinked uploads</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                <div
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: '50%',
                    background: `conic-gradient(#22c55e 0% ${linkUploadPct}%, #e2e8f0 ${linkUploadPct}% 100%)`,
                    display: 'grid',
                    placeItems: 'center',
                  }}
                >
                  <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#fff', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 800, color: '#0f172a' }}>
                    {linkUploadPct}%
                  </div>
                </div>
                <div style={{ display: 'grid', gap: 6, fontSize: 11, color: '#475569' }}>
                  <div>
                    <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: '#22c55e', marginRight: 6, verticalAlign: 'middle' }} />
                    Linked: <strong>{linkedUploadCount}</strong>
                  </div>
                  <div>
                    <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: '#cbd5e1', marginRight: 6, verticalAlign: 'middle' }} />
                    Unlinked: <strong>{unlinkedUploadCount}</strong>
                  </div>
                  <div style={{ fontSize: 10, color: '#94a3b8' }}>Total events: {driftRuns.length}</div>
                </div>
              </div>
            </div>

            <div style={{ borderRadius: 12, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Registry scale</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, height: 100 }}>
                {[
                  { label: 'Families', value: registryFamilyCount, color: '#0ea5e9' },
                  { label: 'Versions', value: savedVersionsKpi, color: '#6366f1' },
                  { label: 'Uploads', value: driftRuns.length, color: '#f97316' },
                ].map((bar) => {
                  const vmax = Math.max(registryFamilyCount, savedVersionsKpi, driftRuns.length, 1)
                  const h = Math.max(12, (bar.value / vmax) * 80)
                  return (
                    <div key={bar.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      <div
                        title={`${bar.label}: ${bar.value}`}
                        style={{
                          width: '70%',
                          maxWidth: 48,
                          height: `${h}px`,
                          borderRadius: 8,
                          background: `linear-gradient(180deg, ${bar.color}, ${bar.color}99)`,
                        }}
                      />
                      <div style={{ fontSize: 18, fontWeight: 800, color: '#0f172a' }}>{bar.value}</div>
                      <div style={{ fontSize: 10, color: '#64748b', fontWeight: 700 }}>{bar.label}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="featureops-history-modal" style={{ borderRadius: 14, background: '#f8fbff', border: '1px solid #dbeafe', padding: '16px 0', display: 'grid', gap: 12, boxShadow: '0 8px 28px rgba(15, 23, 42, 0.08)', width: '100%', maxWidth: 'none' }}>
            <FeatureOpsDatasetHistoryTables
              familiesDisplayRows={familiesDisplayRows}
              families={families}
              driftRuns={driftRuns}
              viewFamilyId={viewFamilyId}
              viewFamilyVersions={viewFamilyVersions}
              selectedCompareVersions={selectedCompareVersions}
              toggleCompareVersion={toggleCompareVersion}
              versionPairComparison={versionPairComparison}
              historyModalViewMode={historyModalViewMode}
              setHistoryModalViewMode={setHistoryModalViewMode}
              setViewFamilyId={setViewFamilyId}
              setSelectedCompareVersions={setSelectedCompareVersions}
              openFilePickerForVersion={openFilePickerForVersion}
              loadVersion={loadVersion}
              loadDriftRun={loadDriftRun}
              deleteFamily={deleteFamily}
              deleteDriftRun={deleteDriftRun}
              approveVersion={approveVersion}
              deleteVersion={deleteVersion}
            />
          </div>
        </div>
      )}

      {!timelineSurface && (
        <>
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap', padding: '14px 0' }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: '#ecf6ff' }}>Agentic AI DE Workflow</div>
          <div style={{ fontSize: 12, color: '#98abc8', marginTop: 4 }}>Semantic Drift Monitoring and FeatureOps Release Gate.</div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="df-btn" onClick={() => { setShowUploadModal(true); setUploadChoiceMode('select') }}>
            Upload New Dataset
          </button>
          <button type="button" className="df-btn secondary" onClick={() => setShowHistoryModal(true)}>Open History</button>
          <button type="button" className="df-btn secondary" onClick={clearCurrentUpload} disabled={!hasUpload && !datasetName}>Clear Upload</button>
          <button type="button" className="df-btn secondary" onClick={downloadFeatureOpsReport} disabled={!reportText.trim()}>Download Report</button>
        </div>
      </div>

      <div className="featureops-release-grid featureops-kpi-strip">
        {[
          ['Dataset families', String(totalFamilies)],
          ['Saved versions', String(totalSavedDatasets)],
          ['Total READY features', String(overallReleaseStats.READY)],
          ['Total CONDITIONAL features', String(overallReleaseStats.CONDITIONAL)],
          ['Total QUARANTINED features', String(overallReleaseStats.QUARANTINED)],
                  ].map(([label, value]) => (
          <div key={label} className="featureops-status-card">
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      {datasetError && (
        <div style={{ borderRadius: 8, border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', padding: '10px 12px', fontSize: 11.5 }}>
          {datasetError}
        </div>
      )}

      {driftDetectionError && (
        <div style={{ borderRadius: 8, border: '1px solid #fecaca', background: '#fff1f2', color: '#9f1239', padding: '10px 12px', fontSize: 11.5 }}>
          Learned drift analysis error: {driftDetectionError}
        </div>
      )}

      {hasUpload && mappingReviewFindings.length > 0 && (
        <article style={{ borderRadius: 10, border: '1px solid #fde68a', background: '#fffbeb', padding: 12, display: 'grid', gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#92400e' }}>Mapping review needed</div>
          <div style={{ fontSize: 11.5, color: '#78350f', lineHeight: 1.6 }}>
            Some columns may be incorrectly mapped. Please review mappings before approving this dataset.
          </div>
          <div style={{ display: 'grid', gap: 4, fontSize: 11.5, color: '#78350f' }}>
            {mappingReviewFindings.map((item) => (
              <div key={`mapping-review-${item.column_name}`}>
                - {item.column_name} should be {item.suggested_role}, not {item.current_role}
              </div>
            ))}
          </div>
          <div>
            <button
              type="button"
              className="df-btn secondary"
              onClick={() => {
                setReviewWorkspaceTab('mapping')
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}
            >
              Review Mapping
            </button>
          </div>
        </article>
      )}
        </>
      )}

      {sanityCheckResult && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.5)', display: 'grid', placeItems: 'center', zIndex: 65, padding: 16 }}>
          <div style={{ width: 'min(640px, 100%)', borderRadius: 16, background: '#ffffff', border: '1px solid #fecaca', color: '#0f172a', padding: 18, display: 'grid', gap: 12 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, color: '#991b1b' }}>Basic sanity check failed</div>
              <div style={{ fontSize: 12, color: '#334155', marginTop: 10, lineHeight: 1.6 }}>
                This dataset does not match the selected baseline family.
              </div>
            </div>
            <div style={{ display: 'grid', gap: 8, fontSize: 11.5, color: '#1e293b' }}>
              <div><strong>Reason:</strong></div>
              <div style={{ color: '#475569', lineHeight: 1.6 }}>
                The uploaded file has different columns from the selected baseline.
              </div>
            </div>
            <div style={{ display: 'grid', gap: 8, fontSize: 11.5, color: '#1e293b' }}>
              <div><strong>What you can do:</strong></div>
              <div style={{ color: '#475569', lineHeight: 1.6 }}>- Choose the correct baseline family</div>
              <div style={{ color: '#475569', lineHeight: 1.6 }}>- Upload the correct version of this dataset</div>
              <div style={{ color: '#475569', lineHeight: 1.6 }}>- Create a new baseline family for this dataset</div>
            </div>
            <details style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#f8fafc', padding: '10px 12px' }}>
              <summary style={{ cursor: 'pointer', fontSize: 11.5, fontWeight: 700, color: '#334155' }}>
                Show technical details
              </summary>
              <div style={{ display: 'grid', gap: 6, fontSize: 11.5, color: '#1e293b', marginTop: 10 }}>
                <div><strong>Required columns:</strong> {sanityCheckResult.requiredColumns.join(', ') || 'None'}</div>
                <div><strong>Important columns:</strong> {sanityCheckResult.importantColumns.join(', ') || 'None'}</div>
                <div><strong>Missing columns:</strong> {sanityCheckResult.missingColumns.join(', ') || 'None'}</div>
                <div><strong>New extra columns:</strong> {sanityCheckResult.extraColumns.join(', ') || 'None'}</div>
                <div><strong>Column count delta:</strong> {sanityCheckResult.columnCountDelta}</div>
              </div>
            </details>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="df-btn secondary"
                onClick={() => {
                  setSanityCheckResult(null)
                  setSelectedFamilyId('')
                  setSelectedVersionNumber(null)
                  setShowUploadModal(true)
                  setUploadChoiceMode('version')
                }}
              >
                Choose Another Baseline
              </button>
              <button type="button" className="df-btn" onClick={() => { setSanityCheckResult(null); void saveAsNewBaseline() }}>
                Create New Baseline Family
              </button>
              <button type="button" className="df-btn secondary" onClick={() => setSanityCheckResult(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {duplicateDatasetResult && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.5)', display: 'grid', placeItems: 'center', zIndex: 66, padding: 16 }}>
          <div style={{ width: 'min(620px, 100%)', borderRadius: 16, background: '#ffffff', border: '1px solid #fed7aa', color: '#0f172a', padding: 18, display: 'grid', gap: 12 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, color: '#9a3412' }}>Duplicate dataset detected</div>
              <div style={{ fontSize: 12, color: '#334155', marginTop: 10, lineHeight: 1.6 }}>
                This exact dataset was already uploaded and cannot be uploaded again.
              </div>
            </div>
            <div style={{ display: 'grid', gap: 8, fontSize: 11.5, color: '#1e293b' }}>
              <div><strong>Existing version:</strong> {duplicateDatasetResult.familyName} v{duplicateDatasetResult.versionNumber}</div>
              <div style={{ color: '#475569', lineHeight: 1.6 }}>
                We checked the dataset content, not just the file name. Because the uploaded data matches an existing saved dataset exactly, the upload has been blocked.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="df-btn"
                onClick={() => {
                  void loadVersion(duplicateDatasetResult.familyId, duplicateDatasetResult.versionNumber)
                  setDuplicateDatasetResult(null)
                }}
              >
                Load Existing Version
              </button>
              <button type="button" className="df-btn secondary" onClick={() => setDuplicateDatasetResult(null)}>
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {showUploadModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)', display: 'grid', placeItems: 'center', zIndex: 60, padding: 16 }}>
          <div className="featureops-history-modal featureops-light-modal" style={{ width: 'min(760px, 100%)', borderRadius: 16, background: '#f8fbff', border: '1px solid #dbeafe', color: '#0f172a', padding: 16, display: 'grid', gap: 12, boxShadow: '0 28px 60px rgba(15, 23, 42, 0.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a' }}>Add Dataset</div>
                <div className="featureops-history-muted" style={{ fontSize: 11.5, fontWeight: 600 }}>Choose whether to create a new baseline family or add a version to an existing family.</div>
              </div>
              <button type="button" onClick={() => { setShowUploadModal(false); setUploadChoiceMode('select') }} style={{ border: 'none', background: 'transparent', color: '#64748b', fontSize: 18, cursor: 'pointer' }}>x</button>
            </div>

            {uploadChoiceMode === 'select' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                <button type="button" onClick={() => setUploadChoiceMode('baseline')} style={{ borderRadius: 12, border: '1px solid #bfdbfe', background: '#eff6ff', color: '#1d4ed8', padding: '16px 14px', fontSize: 12, fontWeight: 800, cursor: 'pointer', textAlign: 'left' }}>
                  Create Baseline Family
                  <div style={{ marginTop: 6, fontSize: 11, fontWeight: 500, color: '#475569' }}>Upload a dataset and save it as version v1 of a new family.</div>
                </button>
                <button type="button" onClick={() => setUploadChoiceMode('version')} style={{ borderRadius: 12, border: '1px solid #cbd5e1', background: '#ffffff', color: '#0f172a', padding: '16px 14px', fontSize: 12, fontWeight: 800, cursor: 'pointer', textAlign: 'left' }}>
                  Add Version to Existing Family
                  <div style={{ marginTop: 6, fontSize: 11, fontWeight: 500, color: '#475569' }}>Select a family, then upload a new version under it.</div>
                </button>
              </div>
            )}

            {uploadChoiceMode === 'baseline' && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div className="featureops-history-muted" style={{ fontSize: 11.5, fontWeight: 600 }}>
                  Create a new baseline family and upload the file to save as version v1.
                  Family name and baseline metadata are detected automatically.
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button type="button" className="df-btn" onClick={openFilePickerForBaseline} disabled={savingWorkflow}>Choose Dataset File</button>
                  <button type="button" className="df-btn secondary" onClick={() => setUploadChoiceMode('select')}>Back</button>
                </div>
              </div>
            )}

            {uploadChoiceMode === 'version' && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div className="featureops-history-muted" style={{ fontSize: 11.5, fontWeight: 600 }}>Select a dataset family, then click Upload New Dataset for that family.</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#0f172a' }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        {['Dataset Family', 'Versions', 'Latest Version', 'Last Updated', 'Actions'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {familiesDisplayRows.map((family) => (
                        <tr key={family.family_id}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>
                            {family.family_name}
                            {family.is_architecture_template ? (
                              <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, color: '#1d4ed8', border: '1px solid #bfdbfe', borderRadius: 6, padding: '1px 6px', verticalAlign: 'middle' }}>Predefined baseline</span>
                            ) : null}
                          </td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{family.is_architecture_template ? '—' : (family.version_count ?? family.versions.length)}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{family.is_architecture_template ? '—' : `v${family.latest_version}`}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{family.is_architecture_template ? '—' : new Date(family.updated_at).toLocaleDateString('en-GB', { month: 'short', day: '2-digit' })}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                              <button type="button" onClick={() => openFilePickerForVersion(family.family_id)} style={{ borderRadius: 999, border: '1px solid #2563eb', background: '#eff6ff', color: '#1d4ed8', padding: '6px 10px', fontSize: 10.5, fontWeight: 700, cursor: 'pointer' }}>
                                {family.is_architecture_template ? 'Upload to create registry family' : '+ Upload New Dataset'}
                              </button>
                              {!family.is_architecture_template ? (
                                <button type="button" onClick={() => void deleteFamily(family.family_id)} style={{ borderRadius: 999, border: '1px solid #fecaca', background: '#fff1f2', color: '#b91c1c', padding: '6px 10px', fontSize: 10.5, fontWeight: 700, cursor: 'pointer' }}>Delete Family</button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!familiesDisplayRows.length && (
                  <div style={{ borderRadius: 8, border: '1px dashed #cbd5e1', background: '#f8fafc', color: '#475569', padding: '12px', fontSize: 11.5 }}>
                    No dataset families or architecture templates available. Check the API connection and try again.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {showHistoryModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)', display: 'grid', placeItems: 'center', zIndex: 60, padding: 16 }}>
          <div className="featureops-history-modal" style={{ width: 'min(1120px, 100%)', borderRadius: 16, background: '#f8fbff', border: '1px solid #dbeafe', color: '#0f172a', padding: 16, display: 'grid', gap: 12, boxShadow: '0 28px 60px rgba(15, 23, 42, 0.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a' }}>Dataset History</div>
                <div className="featureops-history-muted" style={{ fontSize: 11.5, fontWeight: 600 }}>Browse saved families, staged uploads, and registry versions (high-contrast table below).</div>
              </div>
              <button type="button" onClick={() => setShowHistoryModal(false)} style={{ border: 'none', background: 'transparent', color: '#64748b', fontSize: 18, cursor: 'pointer' }}>x</button>
            </div>
            <FeatureOpsDatasetHistoryTables
              familiesDisplayRows={familiesDisplayRows}
              families={families}
              driftRuns={driftRuns}
              viewFamilyId={viewFamilyId}
              viewFamilyVersions={viewFamilyVersions}
              selectedCompareVersions={selectedCompareVersions}
              toggleCompareVersion={toggleCompareVersion}
              versionPairComparison={versionPairComparison}
              historyModalViewMode={historyModalViewMode}
              setHistoryModalViewMode={setHistoryModalViewMode}
              setViewFamilyId={setViewFamilyId}
              setSelectedCompareVersions={setSelectedCompareVersions}
              openFilePickerForVersion={openFilePickerForVersion}
              loadVersion={loadVersion}
              loadDriftRun={loadDriftRun}
              deleteFamily={deleteFamily}
              deleteDriftRun={deleteDriftRun}
              approveVersion={approveVersion}
              deleteVersion={deleteVersion}
              afterNavigate={() => setShowHistoryModal(false)}
            />

          </div>
        </div>
      )}

      {!timelineSurface && (
        <>
      <div className="featureops-top-detail-grid">
        <article className="featureops-light-panel" style={{ borderRadius: 12, padding: 14, display: 'grid', gap: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>Workflow Messages</div>
          {workflowSteps.length > 0 ? (
            <div style={{ display: 'grid', gap: 8 }}>
              {workflowSteps.map((step) => {
                const tone = workflowStatusTone(step.status)
                const isExpanded = expandedWorkflowStepKey === step.label
                return (
                  <button
                    key={`workflow-message-${step.label}`}
                    type="button"
                    onClick={() => setExpandedWorkflowStepKey((current) => (current === step.label ? null : step.label))}
                    className="featureops-expand-card"
                    style={{ borderRadius: 10, border: `1px solid ${tone.border}`, background: '#ffffff', padding: '10px 12px', display: 'grid', gap: 6 }}
                    title={isExpanded ? 'Collapse details' : 'Show full details'}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                      <strong className={isExpanded ? '' : 'featureops-truncate-single'} style={{ fontSize: 11.5, color: '#0f172a', textAlign: 'left' }}>{step.label}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                      <div style={{ display: 'grid', gap: 6, minWidth: 0, flex: '1 1 260px' }}>
                        <div className={isExpanded ? '' : 'featureops-truncate-single'} style={{ fontSize: 11, color: '#334155', textAlign: 'left' }}>{step.detail}</div>
                        <div className={isExpanded ? '' : 'featureops-truncate-single'} style={{ fontSize: 10.5, color: '#64748b', textAlign: 'left' }}>{step.agent}</div>
                      </div>
                      <div style={{ display: 'grid', gap: 6, justifyItems: 'end', alignSelf: 'center', flex: '0 0 auto' }}>
                        <span style={{ fontSize: 10.5, color: '#64748b', fontWeight: 700 }}>{step.duration}</span>
                        <span style={{ borderRadius: 999, background: tone.bg, color: tone.text, border: `1px solid ${tone.border}`, padding: '3px 8px', fontSize: 10.5, fontWeight: 800 }}>
                          {workflowStatusLabel(step.status)}
                        </span>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="featureops-empty-state">
              Workflow steps will appear here after you save a baseline or version.
            </div>
          )}
          <div className="featureops-message-list">
            {messages.length ? messages.slice(-4).reverse().map((item) => {
              const tone = messageTone(item.type)
              return (
                <div key={item.id} className="featureops-message-item" style={{ background: tone.bg, borderColor: tone.border, color: tone.text }}>
                  <span style={{ fontSize: 11.5 }}>{item.message}</span>
                  <strong style={{ fontSize: 11 }}>{item.type.toUpperCase()}</strong>
                </div>
              )
            }) : (
              <div className="featureops-empty-state">
                Workflow messages will appear here after an upload or save action.
              </div>
            )}
          </div>
        </article>

        <article className="featureops-light-panel" style={{ borderRadius: 12, padding: 14, display: 'grid', gap: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>Current Upload Summary</div>
          {!hasUpload ? (
            <div className="featureops-empty-state">
              No dataset is loaded. Upload a CSV or JSON file to start the workflow.
            </div>
          ) : (
            <>
              <div className="featureops-overview-grid">
                {[
                  ['Dataset', datasetName],
                  ['Rows / Columns', `${datasetRows.length} rows / ${columns.length} columns`],
                  ['Workflow type', activeWorkflowType],
                  ['Selected baseline', selectedBaseline ? `${selectedBaseline.dataset_name} v${selectedBaseline.version_number}` : isNewBaselineFlow ? 'New baseline flow' : matchedBaseline ? `${matchedBaseline.family_name} v${matchedBaseline.version_number}` : 'Not selected'],
                  ...(isNewBaselineFlow
                    ? [['Drift scope', 'Internal drift only for this new dataset family']]
                    : [[
                        'Drift vs registry latest',
                        hasUpload && selectedFamilyId && registryLatestVersion ? `Compared with saved v${registryLatestVersion.version_number}` : selectedBaseline ? `Compared with v${selectedBaseline.version_number}` : 'N/A',
                      ], ['Match confidence', matchedBaseline ? `${matchedConfidence}%` : 'N/A']]),
                ].map(([label, value]) => {
                  const cardKey = `${label}:${String(value)}`
                  const isExpanded = expandedSummaryKey === cardKey
                  return (
                    <button
                      type="button"
                      key={label}
                      className="featureops-summary-card featureops-expand-card"
                      onClick={() => setExpandedSummaryKey((current) => (current === cardKey ? null : cardKey))}
                      title={isExpanded ? 'Collapse details' : 'Show full details'}
                    >
                      <span>{label}</span>
                      <strong className={isExpanded ? '' : 'featureops-truncate-single'}>{value}</strong>
                    </button>
                  )
                })}
              </div>
              <div className="featureops-summary-inline featureops-summary-inline--upload">
                <span>Uploaded time</span>
                <strong>{uploadTime ? new Date(uploadTime).toLocaleString('en-GB') : 'N/A'}</strong>
              </div>
              {!isNewBaselineFlow && versionPairComparison && (
                <div className="featureops-history-compare-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Current Comparison: v{versionPairComparison.left.version_number} vs v{versionPairComparison.right.version_number}</div>
                    <div style={{ fontSize: 11, color: '#475569' }}>Compared versions: v{versionPairComparison.left.version_number} vs v{versionPairComparison.right.version_number} | Columns compared: {versionPairComparison.comparedColumns} | No drift: {versionPairComparison.severityCounts.NONE} | Low drift: {versionPairComparison.severityCounts.LOW} | Moderate drift: {versionPairComparison.severityCounts.MODERATE} | High drift: {versionPairComparison.severityCounts.HIGH}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <button type="button" className={`featureops-filter-pill${dashboardCompareViewMode === 'left' ? ' active' : ''}`} onClick={() => setDashboardCompareViewMode('left')}>View v{versionPairComparison.left.version_number} Summary</button>
                    <button type="button" className={`featureops-filter-pill${dashboardCompareViewMode === 'right' ? ' active' : ''}`} onClick={() => setDashboardCompareViewMode('right')}>View v{versionPairComparison.right.version_number} Summary</button>
                    <button type="button" className={`featureops-filter-pill${dashboardCompareViewMode === 'comparison' ? ' active' : ''}`} onClick={() => setDashboardCompareViewMode('comparison')}>View Comparison</button>
                  </div>
                </div>
                <div style={{ overflowX: 'auto', marginTop: 10 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#0f172a' }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {(dashboardCompareViewMode === 'comparison'
                          ? ['Column', `v${versionPairComparison.left.version_number} Meaning`, `v${versionPairComparison.right.version_number} Meaning`, `v${versionPairComparison.left.version_number} Scale`, `v${versionPairComparison.right.version_number} Scale`, 'Drift', 'Release', 'Reason']
                          : ['Column', 'Role', 'Scale', 'Release', 'Summary'])
                          .map((header) => (
                            <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                          ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(dashboardCompareViewMode === 'comparison'
                        ? versionPairComparison.external.map((row) => {
                            const release = versionPairComparison.releaseByColumn[row.column_name]
                            const leftScale = versionPairComparison.left.semantic_profiles.find((item) => item.column_name === row.column_name)?.detected_scale || '-'
                            const rightScale = versionPairComparison.right.semantic_profiles.find((item) => item.column_name === row.column_name)?.detected_scale || '-'
                            return (
                              <tr key={`summary-compare-${row.column_name}`}>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', fontWeight: 700 }}>{row.column_name}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{row.baseline_meaning}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{row.current_detected_meaning}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{leftScale}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{rightScale}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{row.drift_severity}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{release?.release_status || '-'}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>{row.evidence.join(' ') || release?.explanation || '-'}</td>
                              </tr>
                            )
                          })
                        : (dashboardCompareViewMode === 'left' ? versionPairComparison.left : versionPairComparison.right).semantic_profiles.map((profile) => {
                            const source = dashboardCompareViewMode === 'left' ? versionPairComparison.left : versionPairComparison.right
                            const release = source.release_results.find((item) => item.column_name === profile.column_name)
                            return (
                              <tr key={`summary-${dashboardCompareViewMode}-${profile.column_name}`}>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', fontWeight: 700 }}>{profile.column_name}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{profile.generic_role}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{profile.detected_scale}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{release?.release_status || '-'}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>{profile.approved_or_detected_meaning}</td>
                              </tr>
                            )
                          })
                      )}
                    </tbody>
                  </table>
                </div>
                </div>
              )}
              <div className="featureops-preview-wrap" style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                  <thead>
                    <tr>
                      {columns.slice(0, showFullPreview ? columns.length : 8).map((column) => (
                        <th key={column} style={{ textAlign: 'left', padding: '8px 10px', borderBottom: '1px solid #eef2f6' }}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {datasetRows.slice(0, showFullPreview ? Math.min(datasetRows.length, 25) : 5).map((row, rowIndex) => (
                      <tr key={`preview-${rowIndex}`}>
                        {columns.slice(0, showFullPreview ? columns.length : 8).map((column) => (
                          <td key={`${rowIndex}-${column}`} style={{ padding: '8px 10px', borderBottom: '1px solid #f1f5f9', maxWidth: 160, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {String(row[column] ?? '-')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button type="button" onClick={() => setShowFullPreview((value) => !value)} style={{ justifySelf: 'start', border: 'none', background: 'transparent', color: '#2563eb', fontSize: 11, fontWeight: 700, cursor: 'pointer', padding: 0 }}>
                {showFullPreview ? 'Show fewer rows' : 'View full'}
              </button>
            </>
          )}
        </article>
      </div>

      <section style={{ display: 'grid', gap: 12 }}>
        <article className="featureops-light-panel" style={{ borderRadius: 12, padding: 16, display: 'grid', gap: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>Review Workspace</div>
              <div className="muted-text" style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>Use the tabs below to review mappings, semantic profiles, and drift/release outcomes.</div>
            </div>
            <div className="featureops-tab-strip">
              <button
                type="button"
                className={`featureops-workspace-tab${reviewWorkspaceTab === 'mapping' ? ' active' : ''}`}
                onClick={() => setReviewWorkspaceTab('mapping')}
              >
                Mapping Details
              </button>
              <button
                type="button"
                className={`featureops-workspace-tab${reviewWorkspaceTab === 'drift' ? ' active' : ''}`}
                onClick={() => setReviewWorkspaceTab('drift')}
              >
                Drift & Release
              </button>
            </div>
          </div>

          {reviewWorkspaceTab === 'mapping' ? (
            <div style={{ display: 'grid', gap: 12 }}>
              <div className="featureops-nested-panel">
                <div style={{ fontSize: 12, fontWeight: 700, color: '#111827', marginBottom: 10 }}>Mapping Details</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {['Column', 'Detected type', 'Assigned role', 'Confidence', 'Why', 'Change role'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {profiles.map((profile) => {
                        const detection = detections[profile.column_name]
                        const assessment = assessments[profile.column_name]
                        const tone = confidenceTone(assessment.confidence)
                        const role = roles[profile.column_name]
                        const suggestedRole = findSuggestedRole(profile, role)
                        return (
                          <tr key={`mapping-tab-${profile.column_name}`} style={suggestedRole ? { background: '#fffbeb' } : undefined}>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{profile.column_name}</td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{profile.inferred_type}</td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{role}</td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                              <span style={{ borderRadius: 999, background: tone.bg, color: tone.text, padding: '3px 8px', fontSize: 10, fontWeight: 800 }}>
                                {Math.round(assessment.confidence * 100)}%
                              </span>
                            </td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#64748b' }}>
                              {suggestedRole
                                ? `Mapping review needed. ${suggestedRole.reason}`
                                : manualRoles[profile.column_name]
                                  ? `${assessment.reason} Manual mapping applied.`
                                  : detection.reason}
                            </td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                              <select
                                value={manualRoles[profile.column_name] || role}
                                onChange={(event) => {
                                  const nextRole = event.target.value as GenericRole
                                  setManualRoles((previous) => ({ ...previous, [profile.column_name]: nextRole }))
                                  pushMessage('Role mapping updated.', 'success')
                                  pushMessage('Release gate recalculated.', 'info')
                                }}
                                style={{ minWidth: 170 }}
                              >
                                {ROLE_OPTIONS.map((option) => (
                                  <option key={`${profile.column_name}-${option}`} value={option}>{option}</option>
                                ))}
                              </select>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="featureops-nested-panel">
                <div style={{ fontSize: 12, fontWeight: 700, color: '#111827', marginBottom: 10 }}>Semantic Profiles</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {['Column', 'Role', 'Meaning', 'Expected scale', 'Expected unit', 'Value direction', 'Semantic signature'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {semanticProfiles.map((profile) => (
                        <tr key={`semantic-tab-${profile.column_name}`}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{profile.column_name}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{profile.generic_role}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <input
                              type="text"
                              value={profile.approved_or_detected_meaning}
                              onChange={(event) => {
                                const nextValue = event.target.value
                                setManualSemanticOverrides((previous) => ({
                                  ...previous,
                                  [profile.column_name]: { ...previous[profile.column_name], approved_or_detected_meaning: nextValue },
                                }))
                              }}
                              onBlur={() => pushMessage('Semantic meaning updated.', 'success')}
                              style={{ width: '100%' }}
                            />
                          </td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <input
                              type="text"
                              value={profile.expected_scale}
                              onChange={(event) => {
                                const nextValue = event.target.value
                                setManualSemanticOverrides((previous) => ({
                                  ...previous,
                                  [profile.column_name]: { ...previous[profile.column_name], expected_scale: nextValue },
                                }))
                              }}
                              onBlur={() => pushMessage('Expected scale updated.', 'info')}
                              style={{ width: '100%' }}
                            />
                          </td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <input
                              type="text"
                              value={profile.expected_unit}
                              onChange={(event) => {
                                const nextValue = event.target.value
                                setManualSemanticOverrides((previous) => ({
                                  ...previous,
                                  [profile.column_name]: { ...previous[profile.column_name], expected_unit: nextValue },
                                }))
                              }}
                              onBlur={() => pushMessage('Expected unit updated.', 'info')}
                              style={{ width: '100%' }}
                            />
                          </td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <input
                              type="text"
                              value={profile.value_direction}
                              onChange={(event) => {
                                const nextValue = event.target.value
                                setManualSemanticOverrides((previous) => ({
                                  ...previous,
                                  [profile.column_name]: { ...previous[profile.column_name], value_direction: nextValue },
                                }))
                              }}
                              onBlur={() => pushMessage('Value direction updated.', 'info')}
                              style={{ width: '100%' }}
                            />
                          </td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#64748b' }}>{profile.semantic_signature}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="featureops-nested-panel">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <div style={{ display: 'grid', gap: 4 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Data Architecture Baselines</div>
                    <div className="muted-text" style={{ fontSize: 11 }}>
                      Choose one of the five approved baseline templates from data architecture so the upload can be reviewed against a known table meaning.
                    </div>
                  </div>
                  <div style={{ display: 'grid', gap: 8, minWidth: 260 }}>
                    <select
                      value={selectedPredefinedBaselineKey}
                      onChange={(event) => { void applyPredefinedBaselineToCurrentUpload(event.target.value) }}
                      style={{ minWidth: 260 }}
                    >
                      <option value="">Select baseline template</option>
                      {predefinedBaselines.map((baseline) => (
                        <option key={baseline.baseline_key} value={baseline.baseline_key}>
                          {baseline.baseline_key} ({baseline.column_count} columns)
                        </option>
                      ))}
                    </select>
                    <div className="muted-text" style={{ fontSize: 10.5 }}>
                      Available options: {predefinedBaselines.map((baseline) => baseline.baseline_key).join(', ') || 'Loading...'}
                    </div>
                  </div>
                </div>

                {selectedPredefinedBaseline && (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#0f172a' }}>
                      Selected baseline: {selectedPredefinedBaseline.dataset_name} ({selectedPredefinedBaseline.source_table})
                    </div>
                    <div className="muted-text" style={{ fontSize: 10.5 }}>
                      {selectedPredefinedBaseline.description}
                    </div>
                    <pre style={{ margin: 0, padding: 12, borderRadius: 10, background: '#eaf1f8', color: '#0f172a', fontSize: 10.5, overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
{JSON.stringify(selectedPredefinedBaseline, null, 2)}
                    </pre>
                  </div>
                )}

                {!selectedPredefinedBaseline && (
                  <div className="featureops-empty-state">
                    Upload a dataset and select one of these baseline templates: products, users, transactions, shops, or trends.
                  </div>
                )}
              </div>

              <div className="featureops-nested-panel">
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Baseline Creation Module</div>
                  <div className="muted-text" style={{ fontSize: 11 }}>Approved semantic baseline fields and stored business meaning for each baseline column.</div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {['Column', 'Business meaning', 'Role', 'Domain', 'Unit', 'Scale', 'Data type', 'Value direction', 'Baseline version'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {approvedBaselineColumns.map((row: any) => (
                        <tr key={`baseline-module-${row.column_name}`}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.column_name}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.business_meaning}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.role}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.domain}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.unit}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.scale}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.data_type}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.value_direction}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.baseline_version}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!approvedBaselineColumns.length && (
                  <div className="featureops-empty-state">
                    Baseline creation results will appear here after the baseline profile is available.
                  </div>
                )}
              </div>

              <div className="featureops-nested-panel">
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>New Dataset Profiling Module</div>
                  <div className="muted-text" style={{ fontSize: 11 }}>Profiles the newly uploaded dataset using names, data types, sample values, nearby columns, and value patterns.</div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {['Column', 'Detected data type', 'Sample values', 'Nearby columns', 'Value pattern', 'Possible meaning', 'Possible domain', 'Possible role'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {newDatasetProfilingRows.map((row: any) => (
                        <tr key={`profiling-module-${row.column_name}`}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.column_name}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.detected_data_type}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{Array.isArray(row.sample_values) ? row.sample_values.join(', ') : '-'}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{Array.isArray(row.nearby_columns) ? row.nearby_columns.join(', ') : '-'}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.value_pattern}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.possible_business_meaning}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.possible_domain}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.possible_role}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!newDatasetProfilingRows.length && (
                  <div className="featureops-empty-state">
                    New dataset profiling results will appear here after upload analysis finishes.
                  </div>
                )}
              </div>

              <div className="featureops-nested-panel">
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Column Matching Module</div>
                  <div className="muted-text" style={{ fontSize: 11 }}>Matches uploaded columns with baseline columns using exact, normalized, synonym, and semantic similarity checks.</div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {['Incoming column', 'Baseline column', 'Match method', 'Match score', 'Incoming role', 'Baseline role', 'Reason'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {columnMatchingRows.map((row: any) => (
                        <tr key={`matching-module-${row.incoming_column}`}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.incoming_column}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.baseline_column || 'No baseline match'}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.match_method}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{Math.round(Number(row.match_score || 0) * 100)}%</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.incoming_role || '-'}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.baseline_role || '-'}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!columnMatchingRows.length && (
                  <div className="featureops-empty-state">
                    Column matching results will appear here after baseline and profiling data are ready.
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 12 }}>
              <div className="featureops-nested-panel">
                <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Summary Cards</div>
                <div className="featureops-release-grid">
                  {(['READY', 'CONDITIONAL', 'QUARANTINED'] as FeatureStatus[]).map((status) => {
                    const tone = releaseTone(status)
                    return (
                      <div key={`review-${status}`} className="featureops-status-card" style={{ borderColor: tone.border, background: tone.bg }}>
                        <span style={{ color: '#1f2937' }}>{status}</span>
                        <strong style={{ color: '#0f172a' }}>{releaseCounts[status]}</strong>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="featureops-nested-panel">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Drift outcome (column-level)</div>
                    <div className="muted-text" style={{ fontSize: 11 }}>
                      Row-wise cross-field checks are not used here. Use release flags, semantic drift rows, and exports to decide what changed and how to fix it.
                    </div>
                  </div>
                  <span
                    style={{
                      borderRadius: 999,
                      padding: '6px 12px',
                      fontSize: 11,
                      fontWeight: 800,
                      background: columnDriftExecutiveSummary.driftDetected ? '#fef3c7' : '#dcfce7',
                      color: columnDriftExecutiveSummary.driftDetected ? '#92400e' : '#14532d',
                      border: `1px solid ${columnDriftExecutiveSummary.driftDetected ? '#fcd34d' : '#86efac'}`,
                    }}
                  >
                    {columnDriftExecutiveSummary.driftDetected ? 'Drift detected' : 'No column drift'}
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 10, marginTop: 10 }}>
                  <div style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#f8fafc', padding: 10, display: 'grid', gap: 6 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#0f172a' }}>Columns to inspect</div>
                    <div className="muted-text" style={{ fontSize: 10.5, lineHeight: 1.5 }}>
                      {columnDriftExecutiveSummary.columnsAtRisk.length
                        ? columnDriftExecutiveSummary.columnsAtRisk.slice(0, 24).join(', ')
                        : 'None flagged — all mapped columns are READY for release.'}
                    </div>
                  </div>
                  <div style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#f8fafc', padding: 10, display: 'grid', gap: 6 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#0f172a' }}>How to heal</div>
                    <ul style={{ margin: 0, paddingLeft: 16, fontSize: 10.5, color: '#475569', lineHeight: 1.45 }}>
                      {(columnDriftExecutiveSummary.healLines.length
                        ? columnDriftExecutiveSummary.healLines
                        : [{ column: '—', action: 'Run drift against a saved baseline version, then follow recommended actions in the tables below.' }]
                      ).map((line, idx) => (
                        <li key={`heal-${idx}-${line.column}`}>
                          <strong style={{ color: '#111827' }}>{line.column}:</strong> {line.action}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#f8fafc', padding: 10, display: 'grid', gap: 6 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#0f172a' }}>Human loop</div>
                    <div style={{ fontSize: 10.5, color: '#475569', lineHeight: 1.5 }}>
                      {columnDriftExecutiveSummary.humanLoopNeeded
                        ? 'A reviewer should confirm CONDITIONAL / QUARANTINED columns (or high-severity semantic drift) before production release.'
                        : 'No mandatory human gate from current column signals — still review mapping if the dataset is new.'}
                    </div>
                  </div>
                  <div style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#f8fafc', padding: 10, display: 'grid', gap: 6 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#0f172a' }}>Rows vs registry baseline</div>
                    <div style={{ fontSize: 10.5, color: '#475569', lineHeight: 1.5 }}>
                      Current upload: <strong>{columnDriftExecutiveSummary.uploadRows}</strong> rows.
                      {columnDriftExecutiveSummary.baselineRows != null && (
                        <>
                          {' '}Selected baseline version: <strong>{columnDriftExecutiveSummary.baselineRows}</strong> rows.
                          {columnDriftExecutiveSummary.rowDeltaVsBaseline != null && (
                            <>
                              {' '}Delta (upload − baseline): <strong>{columnDriftExecutiveSummary.rowDeltaVsBaseline >= 0 ? '+' : ''}{columnDriftExecutiveSummary.rowDeltaVsBaseline}</strong>.
                            </>
                          )}
                        </>
                      )}
                      {' '}Saving a new family version records this upload as a new version; downstream governed tables (for example Chroma sales) are updated only through the semantic ingest / export path, not silently by this screen alone.
                    </div>
                  </div>
                </div>

                <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <button type="button" className="df-btn secondary" onClick={downloadCurrentUploadCsv} disabled={!datasetRows.length}>
                    Download current upload (CSV)
                  </button>
                  <a className="df-btn secondary" href={`${semanticExportBase}/sales`} download style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>
                    Export Chroma sales (CSV)
                  </a>
                  <a className="df-btn secondary" href={`${semanticExportBase}/batches`} download style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>
                    Export ingest batches (CSV)
                  </a>
                  <span className="muted-text" style={{ fontSize: 10 }}>
                    Use batch id from the latest semantic ingest response with <code style={{ fontSize: 10 }}>{semanticExportBase}/drift-results/&lt;batch_id&gt;</code> for drift rows.
                  </span>
                </div>
              </div>

              <div className="featureops-nested-panel">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Semantic Drift Detected</div>
                    <div className="muted-text" style={{ fontSize: 11 }}>Internal and external semantic drift with explanations and recommended actions.</div>
                  </div>
                </div>

                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {['Column', 'Drift source', 'Severity', 'Explanation', 'Recommended action'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ...internalDrift.map((row) => ({
                          key: `internal-review-${row.column_name}`,
                          column_name: row.column_name,
                          source: `Internal (${row.compared_by})`,
                          severity: row.drift_severity,
                          explanation: row.explanation || row.evidence.join(' '),
                          recommended_action: row.recommended_action,
                        })),
                        ...externalDrift.map((row) => ({
                          key: `external-review-${row.column_name}`,
                          column_name: row.column_name,
                          source: `External (${row.baseline_version})`,
                          severity: row.drift_severity,
                          explanation: row.explanation || row.evidence.join(' '),
                          recommended_action: row.recommended_action,
                        })),
                      ].slice(0, 18).map((row) => (
                        <tr key={row.key}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.column_name}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.source}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.severity}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.explanation}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.recommended_action}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {!internalDrift.length && !externalDrift.length && (
                  <div className="featureops-empty-state">
                    No semantic drift was detected yet. Upload a dataset or compare against a saved family version.
                  </div>
                )}
              </div>

              <div className="featureops-nested-panel">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>Release Decisions</div>
                    <div className="muted-text" style={{ fontSize: 11 }}>Feature release labels with explanations and actions.</div>
                  </div>
                  <div className="featureops-filter-row">
                    {(['All', 'READY', 'CONDITIONAL', 'QUARANTINED'] as const).map((tab) => (
                      <button key={tab} type="button" className={`featureops-filter-pill${releaseFilter === tab ? ' active' : ''}`} onClick={() => setReleaseFilter(tab)}>
                        {tab}
                      </button>
                    ))}
                  </div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5 }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {['Column', 'Role', 'Release', 'Explanation', 'Recommended action'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {visibleReleaseRows.slice(0, 16).map((row) => {
                        const tone = releaseTone(row.release_status)
                        return (
                          <tr key={`release-review-${row.column_name}`}>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.column_name}</td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.role}</td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                              <span style={{ borderRadius: 999, background: tone.text, color: '#ffffff', padding: '4px 8px', fontSize: 10, fontWeight: 800 }}>{row.release_status}</span>
                            </td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.explanation}</td>
                            <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.recommended_action}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </article>
      </section>
        </>
      )}
    </section>
  )
}



