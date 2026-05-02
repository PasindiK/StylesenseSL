import React, { useEffect, useMemo, useRef, useState } from 'react'
import '../../data_fabric/components/DataFabricTestingPage.css'
import './FeatureOpsWorkflowPanel.css'

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

type ReleaseResult = {
  column_name: string
  role: GenericRole
  validation_status: 'PASS' | 'WARN' | 'FAIL'
  internal_drift_severity: DriftSeverity
  external_drift_severity: DriftSeverity
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
  const parsed = Number(trimmed.replace(/[^0-9.+-]/g, ''))
  return Number.isFinite(parsed) ? parsed : null
}

function parseDateValue(value: DatasetValue): number | null {
  if (value == null || value === '') return null
  const date = new Date(String(value))
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
  const lowered = columnName.toLowerCase()
  return keywords.some((keyword) => lowered.includes(keyword))
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

  if (keywordMatch(name, IDENTIFIER_KEYWORDS) && (profile.unique_percent >= 0.2 || name.endsWith('id'))) {
    detectedRole = 'Identifier'
    confidence = profile.unique_percent >= 0.75 ? 0.98 : 0.86
    reason = profile.unique_percent >= 0.75
      ? 'Contains ID keyword and behaves like a high-uniqueness identifier.'
      : 'Contains ID keyword and behaves like a repeated entity identifier.'
  } else if (keywordMatch(name, TIMESTAMP_KEYWORDS) || profile.valid_date_percent >= 0.9) {
    detectedRole = 'Timestamp'
    confidence = keywordMatch(name, TIMESTAMP_KEYWORDS) && profile.valid_date_percent >= 0.75 ? 0.99 : 0.84
    reason = 'Parsed as datetime and/or contains a timestamp keyword.'
  } else if (keywordMatch(name, TARGET_KEYWORDS)) {
    if (profile.binary_like_percent >= 0.8 || profile.inferred_type === 'boolean') {
      detectedRole = 'Target Column'
      confidence = 0.95
      reason = 'Contains target/label keyword and values look like a target signal.'
    } else if (profile.inferred_type === 'text' && profile.unique_percent <= 0.4) {
      detectedRole = 'Target Column'
      confidence = 0.86
      reason = 'Contains target/label keyword and behaves like a repeated class field.'
    }
  } else if ((keywordMatch(name, BINARY_KEYWORDS) || profile.inferred_type === 'boolean') && profile.binary_like_percent >= 0.8) {
    detectedRole = 'Binary Label'
    confidence = 0.92
    reason = 'Boolean/binary pattern matched.'
  } else if (keywordMatch(name, SCORE_KEYWORDS) && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed')) {
    detectedRole = 'Score / Rating'
    confidence = ['0-1', '0-100', '1-5', '1-10'].includes(profile.scale_pattern) ? 0.95 : 0.82
    reason = 'Score keyword matched and values behave like a score.'
  } else if (keywordMatch(name, COUNT_KEYWORDS) && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed')) {
    detectedRole = 'Count / Activity'
    confidence = profile.integer_like_percent >= 0.7 && (profile.min ?? 0) >= 0 ? 0.9 : 0.76
    reason = 'Count/activity keyword matched and values look like activity counts.'
  } else if ((keywordMatch(name, RATE_KEYWORDS) || name.includes('humidity')) && (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') && ['0-1', '0-100'].includes(profile.scale_pattern) && (profile.min ?? 0) >= 0) {
    detectedRole = 'Rate / Percentage'
    confidence = keywordMatch(name, RATE_KEYWORDS) || name.includes('humidity') ? 0.88 : 0.74
    reason = 'Value range behaves like a bounded percentage or ratio.'
  } else if (profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') {
    detectedRole = 'Numeric Measure'
    confidence = 0.85
    reason = 'Continuous numeric sensor or business measurement.'
  } else if (profile.inferred_type === 'text' && profile.unique_percent <= 0.6) {
    detectedRole = 'Categorical Attribute'
    confidence = 0.9
    reason = 'Repeated text values indicate a categorical attribute.'
  } else if (profile.inferred_type === 'text' && (keywordMatch(name, TEXT_KEYWORDS) || profile.avg_string_length >= 12)) {
    detectedRole = 'Text Attribute'
    confidence = 0.82
    reason = 'String values look like a descriptive text field.'
  }

  if (name.endsWith('status') && profile.inferred_type === 'text') {
    detectedRole = 'Categorical Attribute'
    confidence = Math.max(confidence, 0.9)
    reason = 'Status values are categorical labels, not binary targets.'
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

function buildReleaseResults(profiles: ColumnProfile[], roles: Record<string, GenericRole>, assessments: Record<string, { confidence: number }>, internal: Record<string, InternalDriftResult>, external: Record<string, ExternalDriftResult>) {
  return profiles.map((profile) => {
    const role = roles[profile.column_name]
    const internalSeverity = internal[profile.column_name]?.drift_severity ?? 'NONE'
    const externalSeverity = external[profile.column_name]?.drift_severity ?? 'NONE'
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

    let validation_status: 'PASS' | 'WARN' | 'FAIL' = 'PASS'
    if (critical_failures.length) validation_status = 'FAIL'
    else if (warnings.length) validation_status = 'WARN'

    let release_status: FeatureStatus = 'READY'
    if (internalSeverity === 'HIGH' || externalSeverity === 'HIGH' || critical_failures.length) {
      release_status = 'QUARANTINED'
    } else if (internalSeverity === 'MODERATE' || externalSeverity === 'MODERATE' || validation_status === 'WARN') {
      release_status = 'CONDITIONAL'
    }

    const explanation =
      release_status === 'READY'
        ? 'Column meaning is stable and validation checks passed.'
        : release_status === 'CONDITIONAL'
          ? `${warnings[0] || 'Moderate semantic drift detected'}, admin review recommended.`
          : `${critical_failures[0] || external[profile.column_name]?.evidence?.[0] || internal[profile.column_name]?.evidence?.[0] || 'Critical semantic issue detected'}.`

    return {
      column_name: profile.column_name,
      role,
      validation_status,
      internal_drift_severity: internalSeverity,
      external_drift_severity: externalSeverity,
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
  const baselineSet = new Set(baselineColumns)
  const currentSet = new Set(currentColumns)
  const importantColumns = (baselineVersion.dataset_fingerprint?.important_columns || []).filter(Boolean)
  const requiredColumns = importantColumns.length ? importantColumns : baselineColumns.slice(0, Math.min(5, baselineColumns.length))
  const missingColumns = baselineColumns.filter((column) => !currentSet.has(column))
  const missingImportant = requiredColumns.filter((column) => !currentSet.has(column))
  const extraColumns = currentColumns.filter((column) => !baselineSet.has(column))
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

export default function FeatureOpsWorkflowPanel() {
  const apiBase = import.meta.env.VITE_API_URL || import.meta.env.VITE_AGENTIC_API_URL || '/api'
  const [uploadedRows, setUploadedRows] = useState<DatasetRow[] | null>(null)
  const [datasetName, setDatasetName] = useState('')
  const [datasetError, setDatasetError] = useState<string | null>(null)
  const [manualRoles, setManualRoles] = useState<Record<string, GenericRole | undefined>>({})
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
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const pendingVersionFamilyIdRef = useRef<string | null>(null)

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
  const semanticProfiles = useMemo(() => profiles.map((profile) => buildSemanticProfile(profile, roles[profile.column_name])), [profiles, roles])
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
  const externalDrift = useMemo(() => buildExternalDrift(semanticProfiles, externalDriftBaseline, 'current_upload'), [externalDriftBaseline, semanticProfiles])
  const externalMap = useMemo(() => externalDrift.reduce<Record<string, ExternalDriftResult>>((acc, item) => {
    acc[item.column_name] = item
    return acc
  }, {}), [externalDrift])
  const releaseResults = useMemo(() => buildReleaseResults(profiles, roles, assessments, internalMap, externalMap), [assessments, externalMap, internalMap, profiles, roles])
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
    release_status: row.release_status,
    evidence: [
      ...(internalMap[row.column_name]?.evidence || []),
      ...(externalMap[row.column_name]?.evidence || []),
      ...(row.critical_failures || []),
      ...(row.warnings || []),
    ].filter(Boolean).join(' ') || row.explanation,
  })), [externalMap, internalMap, releaseResults])
  const visibleDriftEvidenceRows = useMemo(() => {
    if (evidenceFilter === 'Drifted') {
      return driftEvidenceRows.filter((row) => row.internal_drift !== 'NONE' || row.external_drift !== 'NONE')
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

  function resetWorkflowState() {
    setManualRoles({})
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
  }

  function openFilePickerForBaseline() {
    pendingVersionFamilyIdRef.current = null
    setUploadChoiceMode('baseline')
    setDatasetError(null)
    fileInputRef.current?.click()
  }

  function openFilePickerForVersion(familyId: string) {
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

  async function loadFamilies() {
    try {
      const response = await fetch(`${apiBase}/featureops/families`)
      const payload = await response.json()
      if (payload.status === 'ok') {
        setFamilies(payload.families || [])
        const versionsMap: Record<string, StoredVersion[]> = {}
        await Promise.all((payload.families || []).map(async (family: FamilyRecord) => {
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
    const payload = {
      dataset_name: datasetName,
      family_id: null,
      version_id: null,
      version_number: null,
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
  }, [apiBase, datasetName, externalDrift, fingerprint, hasUpload, internalDrift, lastRecordedUploadKey, releaseResults, uploadTime])

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
        if (!sanity.passed) {
          setSanityCheckResult(sanity)
          setPendingSaveAction(null)
          pushMessage('Basic sanity check failed. The uploaded file has different columns from the selected baseline.', 'error')
        } else {
          setPendingSaveAction({ mode: 'version', familyId: targetFamilyId })
          pushMessage('Dataset uploaded successfully.', 'success')
          pushMessage('Dataset profiled successfully.', 'success')
          pushMessage('Internal semantic consistency check completed.', 'success')
          pushMessage(`External drift checked against registry v${baselineForSanity?.version_number ?? baselineNum ?? 'Ã¢â‚¬â€'}.`, 'info')
        }
      } else {
        resetWorkflowState()
        setUploadedRows(parsed)
        setDatasetName(file.name)
        setUploadTime(new Date().toISOString())
        setDatasetError(null)
        setMessages([])
        setShowUploadModal(false)
        setUploadChoiceMode('select')
        setPendingSaveAction({ mode: 'baseline' })
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
    resetWorkflowState()
    setUploadedRows(demoDataset)
    setDatasetName(DEMO_NAME)
    setUploadTime(new Date().toISOString())
    setDatasetError(null)
    setMessages([])
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
    const familyName = datasetName.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim() || matchedBaseline?.family_name || 'Uploaded Dataset'
    if (!familyName) return
    const existingFamily = families.find((item) => normalizeFamilyName(String(item.family_name || '')) === normalizeFamilyName(familyName))
    if (existingFamily) {
      const duplicateVersion = findDuplicateVersionInFamily(existingFamily.family_id)
      if (duplicateVersion) {
        setDuplicateDatasetResult({
          familyId: existingFamily.family_id,
          familyName: existingFamily.family_name,
          versionNumber: duplicateVersion.version_number,
        })
        pushMessage(`Duplicate dataset detected: ${existingFamily.family_name} v${duplicateVersion.version_number}.`, 'warning')
        return
      }
      const nextBaseline = (familyVersions[existingFamily.family_id] || []).find((item) => item.version_number === (existingFamily.approved_baseline_version || existingFamily.latest_version))
        || (familyVersions[existingFamily.family_id] || [])[0]
        || null
      setSelectedFamilyId(existingFamily.family_id)
      setSelectedVersionNumber(existingFamily.approved_baseline_version || existingFamily.latest_version || null)
      pushMessage(`Family "${existingFamily.family_name}" already exists. Saving this upload as a new version instead.`, 'info')
      await addAsNewVersion(existingFamily.family_id, nextBaseline)
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
      description: 'Semantic monitoring baseline',
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
        setUploadedRows(payload.version.dataset_rows)
        setDatasetName(payload.version.file_name || payload.version.dataset_name || '')
        setUploadTime(payload.version.created_at || '')
        setDatasetError(null)
      }
      setSelectedFamilyId(familyId)
      setSelectedVersionNumber(versionNumber)
      setViewFamilyId(familyId)
      setLastWorkflowMode('version')
      pushMessage('Saved dataset version loaded successfully.', 'success')
    }
  }

  function loadDriftRun(run: DriftRunRecord) {
    if (run.dataset_rows?.length) {
      resetWorkflowState()
      setUploadedRows(run.dataset_rows)
      setDatasetName(run.dataset_name)
      setUploadTime(run.created_at)
      setDatasetError(null)
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
    <section className="df-dashboard-shell featureops-shell" style={{ padding: '12px 12px 24px', display: 'grid', gap: 12, width: '100%', maxWidth: 'none' }}>
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap', padding: '14px 16px' }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: '#ecf6ff' }}>Agentic AI DE Workflow</div>
          <div style={{ fontSize: 12, color: '#98abc8', marginTop: 4 }}>Semantic Drift Monitoring and FeatureOps Release Gate.</div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input ref={fileInputRef} type="file" accept=".csv,.json" onChange={handleFileUpload} style={{ display: 'none' }} />
          <button type="button" className="df-btn" onClick={() => { setShowUploadModal(true); setUploadChoiceMode('select') }}>
            Upload New Dataset
          </button>
          <button type="button" className="df-btn secondary" onClick={() => setShowHistoryModal(true)}>Open History</button>
          <button type="button" className="df-btn secondary" onClick={clearCurrentUpload} disabled={!hasUpload && !datasetName}>Clear Upload</button>
        </div>
      </div>

      {datasetError && (
        <div style={{ borderRadius: 8, border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', padding: '10px 12px', fontSize: 11.5 }}>
          {datasetError}
        </div>
      )}

      {showUploadModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)', display: 'grid', placeItems: 'center', zIndex: 60, padding: 16 }}>
          <div style={{ width: 'min(760px, 100%)', borderRadius: 16, background: '#ffffff', border: '1px solid #dbeafe', padding: 16, display: 'grid', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a' }}>Add Dataset</div>
                <div style={{ fontSize: 11.5, color: '#64748b' }}>Choose whether to create a new baseline family or add a version to an existing family.</div>
              </div>
              <button type="button" onClick={() => { setShowUploadModal(false); setUploadChoiceMode('select') }} style={{ border: 'none', background: 'transparent', color: '#64748b', fontSize: 18, cursor: 'pointer' }}>×</button>
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
                <div style={{ fontSize: 11.5, color: '#475569' }}>
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
                <div style={{ fontSize: 11.5, color: '#475569' }}>Select a dataset family, then click Upload New Dataset for that family.</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        {['Dataset Family', 'Versions', 'Latest Version', 'Last Updated', 'Actions'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {families.map((family) => (
                        <tr key={family.family_id}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{family.family_name}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{family.version_count ?? family.versions.length}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>v{family.latest_version}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{new Date(family.updated_at).toLocaleDateString('en-GB', { month: 'short', day: '2-digit' })}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <button type="button" onClick={() => openFilePickerForVersion(family.family_id)} style={{ borderRadius: 999, border: '1px solid #2563eb', background: '#eff6ff', color: '#1d4ed8', padding: '6px 10px', fontSize: 10.5, fontWeight: 700, cursor: 'pointer' }}>＋ Upload New Dataset</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!families.length && (
                  <div style={{ borderRadius: 8, border: '1px dashed #cbd5e1', background: '#f8fafc', color: '#475569', padding: '12px', fontSize: 11.5 }}>
                    No dataset families found yet. Create a baseline family first.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {showHistoryModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)', display: 'grid', placeItems: 'center', zIndex: 60, padding: 16 }}>
          <div style={{ width: 'min(980px, 100%)', borderRadius: 16, background: '#ffffff', border: '1px solid #dbeafe', padding: 16, display: 'grid', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a' }}>Dataset History</div>
                <div style={{ fontSize: 11.5, color: '#64748b' }}>Browse saved families, versions, and upload events.</div>
              </div>
              <button type="button" onClick={() => setShowHistoryModal(false)} style={{ border: 'none', background: 'transparent', color: '#64748b', fontSize: 18, cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    {['Dataset Family', 'Versions', 'Latest Version', 'Last Updated', 'Actions'].map((header) => (
                      <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {families.map((family) => (
                    <tr key={family.family_id}>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{family.family_name}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', textAlign: 'right' }}>{family.version_count ?? family.versions.length}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>v{family.latest_version}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{new Date(family.updated_at).toLocaleDateString('en-GB', { month: 'short', day: '2-digit' })}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          <button type="button" onClick={() => setViewFamilyId(family.family_id)} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>View Versions</button>
                          <button type="button" onClick={() => openFilePickerForVersion(family.family_id)} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>+ Add Dataset</button>
                          <button type="button" onClick={() => { void loadVersion(family.family_id, family.approved_baseline_version || family.latest_version); setShowHistoryModal(false) }} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>Load</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Uploaded Dataset History</div>
              {!driftRuns.length ? (
                <div style={{ borderRadius: 8, border: '1px dashed #cbd5e1', background: '#f8fafc', color: '#475569', padding: '12px', fontSize: 11.5 }}>
                  No upload events recorded yet.
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        {['Dataset Name', 'Uploaded At', 'Linked Family', 'Release Summary'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {driftRuns.slice().reverse().map((run) => (
                        <tr key={run.run_id}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{run.dataset_name}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{new Date(run.created_at).toLocaleString('en-GB')}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{run.family_id || 'Not linked'}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                              <span>{summarizeReleaseResults(run.release_results || [])}</span>
                              <button type="button" onClick={() => { loadDriftRun(run); setShowHistoryModal(false) }} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>
                                Load This Upload
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {viewFamilyId && (
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Saved versions for {families.find((family) => family.family_id === viewFamilyId)?.family_name || viewFamilyId}</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        {['Version', 'File Name', 'Created Date', 'Rows', 'Columns', 'Release Summary', 'Actions'].map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(familyVersions[viewFamilyId] || []).map((version) => (
                        <tr key={version.version_id}>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>v{version.version_number}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{version.file_name || version.dataset_name}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{new Date(version.created_at).toLocaleString('en-GB')}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{version.row_count}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{version.column_count}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{summarizeReleaseResults(version.release_results)}</td>
                          <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                              <button type="button" onClick={() => { void loadVersion(viewFamilyId, version.version_number); setShowHistoryModal(false) }} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>Load</button>
                              <button type="button" onClick={() => void approveVersion(viewFamilyId, version.version_number)} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>Set As Baseline</button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Current Upload</div>
        {!hasUpload ? (
          <div style={{ borderRadius: 8, border: '1px dashed #cbd5e1', background: '#f8fafc', color: '#475569', padding: '12px', fontSize: 11.5 }}>
            No dataset is loaded. Upload a CSV/JSON file to start the workflow.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 8 }}>
            {[
              ['File', datasetName],
              ['Rows', String(datasetRows.length)],
              ['Columns', String(columns.length)],
              ['Uploaded at', new Date(uploadTime).toLocaleString('en-GB')],
              ['Detected target column', targetColumn],
              ['Workflow type', workflowMode],
              ['Internal drift', internalDriftStatus],
            ].map(([label, value]) => (
              <div key={label} style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#f8fafc', padding: '9px 10px' }}>
                <div style={{ fontSize: 10.5, color: '#64748b' }}>{label}</div>
                <div style={{ fontSize: 12, fontWeight: 800, color: '#111827' }}>{value}</div>
              </div>
            ))}
          </div>
        )}
      </article>

      <article className="glass-card panel-section" style={{ borderRadius: 10, padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#ecf6ff' }}>Workflow Progress</div>
        {workflowSteps.length ? (
          <>
            <ul className="intake-step-list">
              {workflowSteps.map((step) => (
                <li key={step.label} className={`step-${step.status}`}>
                  <div className="featureops-step-copy">
                    <span>{step.label}</span>
                    <small>{step.agent}{step.reason ? ` | ${step.reason}` : ''}</small>
                  </div>
                  <strong>{step.status}</strong>
                </li>
              ))}
            </ul>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
              <div className="runtime-card">
                <h4>Agents</h4>
                <ul className="meta-list compact">
                  {agentStatuses.map((item) => (
                    <li key={item.agent}>
                      <span>{item.agent}</span>
                      <strong>{item.status}</strong>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="runtime-card">
                <h4>Counts</h4>
                <ul className="meta-list compact">
                  <li><span>Column profiles</span><strong>{profiles.length}</strong></li>
                  <li><span>Semantic profiles</span><strong>{semanticProfiles.length}</strong></li>
                  <li><span>Internal drift rows</span><strong>{internalDrift.length}</strong></li>
                  <li><span>External drift rows</span><strong>{lastWorkflowMode === 'version' ? externalDrift.length : 0}</strong></li>
                </ul>
              </div>
              <div className="runtime-card">
                <h4>Release Summary</h4>
                <ul className="meta-list compact">
                  <li><span>READY</span><strong>{releaseCounts.READY}</strong></li>
                  <li><span>CONDITIONAL</span><strong>{releaseCounts.CONDITIONAL}</strong></li>
                  <li><span>QUARANTINED</span><strong>{releaseCounts.QUARANTINED}</strong></li>
                </ul>
                <button type="button" className="df-btn" onClick={downloadFeatureOpsReport} disabled={!reportText.trim()}>
                  Download Workflow Report
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="featureops-empty-state">
            Workflow steps will appear after you save a baseline or version.
          </div>
        )}
      </article>

      <article className="glass-card panel-section" style={{ borderRadius: 10, padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
          <div className="runtime-card">
            <h4>Internal Semantic Drift</h4>
            <p className="muted-text">Checks drift within the currently uploaded dataset.</p>
            <ul className="meta-list compact">
              <li><span>Compared columns</span><strong>{internalDrift.length}</strong></li>
              <li><span>Status</span><strong>{hasUpload ? 'completed' : 'pending'}</strong></li>
            </ul>
          </div>
          <div className="runtime-card">
            <h4>External Semantic Drift</h4>
            {lastWorkflowMode === 'baseline' ? (
              <>
                <p className="muted-text">Skipped for first baseline creation because there is no previous baseline to compare.</p>
                <ul className="meta-list compact">
                  <li><span>Status</span><strong>skipped</strong></li>
                </ul>
              </>
            ) : (
              <>
                <p className="muted-text">Checks drift between this upload and the selected baseline version.</p>
                <ul className="meta-list compact">
                  <li><span>Compared columns</span><strong>{selectedBaseline ? externalDrift.length : 0}</strong></li>
                  <li><span>Status</span><strong>{selectedBaseline ? 'completed' : 'pending'}</strong></li>
                </ul>
              </>
            )}
          </div>
        </div>
      </article>


      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Dataset Snapshot</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
          {[
            ['File name', datasetName],
            ['Rows', String(datasetRows.length)],
            ['Columns', String(columns.length)],
            ['Uploaded at', new Date(uploadTime).toLocaleString('en-GB')],
            ['Workflow type', workflowMode],
            ['Closest baseline', matchedBaseline ? `${matchedBaseline.family_name} v${matchedBaseline.version_number}` : 'No strong match'],
            ['Match confidence', matchedBaseline ? `${Math.round(matchedBaseline.match_score * 100)}%` : 'N/A'],
            ['Selected comparison baseline', selectedBaseline ? `${selectedBaseline.dataset_name} v${selectedBaseline.version_number}` : 'Not selected'],
          ].map(([label, value]) => (
            <div key={label} style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#f8fafc', padding: '9px 10px' }}>
              <div style={{ fontSize: 10.5, color: '#64748b' }}>{label}</div>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#111827' }}>{value}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11.5, color: '#475569' }}>
          Top baseline matches:
          {' '}
          {matches.length ? matches.map((match) => `${match.family_name} ${Math.round(match.match_score * 100)}%`).join(' · ') : 'No saved dataset families yet.'}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {columns.slice(0, showFullPreview ? columns.length : 8).map((column) => (
                  <th key={column} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {datasetRows.slice(0, 5).map((row, rowIndex) => (
                <tr key={`preview-${rowIndex}`}>
                  {columns.slice(0, showFullPreview ? columns.length : 8).map((column) => (
                    <td key={`${rowIndex}-${column}`} style={{ padding: '7px 6px', borderBottom: '1px solid #f1f5f9', maxWidth: 160, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {String(row[column] ?? '-')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {columns.length > 8 && (
          <button type="button" onClick={() => setShowFullPreview((value) => !value)} style={{ justifySelf: 'start', border: 'none', background: 'transparent', color: '#2563eb', fontSize: 11, fontWeight: 700, cursor: 'pointer', padding: 0 }}>
            {showFullPreview ? 'Show fewer columns' : 'Show all columns'}
          </button>
        )}
      </article>

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Column Role Mapping</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {['Column', 'Detected type', 'Assigned role', 'Confidence', 'Why', 'Change role'].map((header) => (
                  <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {profiles.map((profile) => {
                const detection = detections[profile.column_name]
                const assessment = assessments[profile.column_name]
                const tone = confidenceTone(assessment.confidence)
                const role = roles[profile.column_name]
                return (
                  <tr key={`mapping-${profile.column_name}`}>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{profile.column_name}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{profile.inferred_type}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{role}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                      <span style={{ borderRadius: 999, background: tone.bg, color: tone.text, padding: '3px 8px', fontSize: 10, fontWeight: 800 }}>
                        {Math.round(assessment.confidence * 100)}%
                      </span>
                      {assessment.lowConfidence && (
                        <div style={{ marginTop: 4, fontSize: 10, color: '#b45309', fontWeight: 700 }}>Low confidence for selected role</div>
                      )}
                    </td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#64748b' }}>
                      {manualRoles[profile.column_name] ? `${assessment.reason} Manual mapping applied.` : detection.reason}
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
                        style={{ borderRadius: 8, border: '1px solid #d1d5db', background: '#ffffff', color: '#0f172a', fontSize: 11, padding: '5px 8px', minWidth: 170 }}
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
      </article>

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Semantic Profile Overview</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {['Column', 'Role', 'Detected scale', 'Detected unit', 'Value direction', 'Semantic signature', 'Sample values'].map((header) => (
                  <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {semanticProfiles.map((profile) => (
                <tr key={`semantic-${profile.column_name}`}>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{profile.column_name}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{profile.generic_role}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{profile.detected_scale}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{profile.detected_unit}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{profile.value_direction}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#64748b' }}>{profile.semantic_signature}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#64748b' }}>{profiles.find((item) => item.column_name === profile.column_name)?.sample_values.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Internal Semantic Drift</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {['Column', 'Compared using', 'Drift severity', 'Evidence', 'Explanation', 'Recommended action'].map((header) => (
                  <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {internalDrift.map((row) => (
                <tr key={`internal-${row.column_name}`}>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.column_name}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.compared_by}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.drift_severity}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#64748b' }}>{row.evidence.join(' ')}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.explanation}</td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.recommended_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>External Semantic Drift</div>
        {!selectedBaseline ? (
          <div style={{ borderRadius: 8, border: '1px solid #dbeafe', background: '#eff6ff', color: '#1e3a8a', padding: '10px 12px', fontSize: 11.5 }}>
            External drift has not run yet. Select a baseline version to compare.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  {['Column', 'Baseline meaning', 'Current meaning', 'Drift severity', 'Evidence', 'Explanation', 'Recommended action'].map((header) => (
                    <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {externalDrift.map((row) => (
                  <tr key={`external-${row.column_name}`}>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.column_name}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.baseline_meaning}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.current_detected_meaning}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.drift_severity}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#64748b' }}>{row.evidence.join(' ')}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.explanation}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.recommended_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Feature Release Gate</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
          {(['READY', 'CONDITIONAL', 'QUARANTINED'] as FeatureStatus[]).map((status) => {
            const tone = releaseTone(status)
            return (
              <div key={status} style={{ borderRadius: 8, border: `1px solid ${tone.border}`, background: tone.bg, padding: '10px 12px' }}>
                <div style={{ fontSize: 10.5, color: tone.text }}>{status}</div>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#111827' }}>{releaseCounts[status]}</div>
              </div>
            )
          })}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#334155' }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {['Column / feature', 'Role', 'Validation status', 'Internal drift', 'External drift', 'Release', 'Critical failures', 'Warnings', 'Reason / action'].map((header) => (
                  <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {releaseResults.map((row) => {
                const tone = releaseTone(row.release_status)
                return (
                  <tr key={`release-${row.column_name}`}>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>{row.column_name}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.role}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.validation_status}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.internal_drift_severity}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{row.external_drift_severity}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                      <span style={{ borderRadius: 999, background: tone.text, color: '#ffffff', padding: '4px 8px', fontSize: 10, fontWeight: 800 }}>{row.release_status}</span>
                    </td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.critical_failures.join('; ') || 'None'}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.warnings.join('; ') || 'None'}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', color: '#475569' }}>{row.explanation}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </article>

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Registry Summary</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
          {[
            ['Selected family', selectedFamilyId || 'Not selected'],
            ['Selected version', selectedVersionNumber != null ? `v${selectedVersionNumber}` : 'Not selected'],
            ['Comparison mode', selectedBaseline ? `Compared with ${selectedBaseline.dataset_family_id} v${selectedBaseline.version_number}` : 'No baseline comparison'],
            ['Release summary', summarizeReleaseResults(releaseResults)],
          ].map(([label, value]) => (
            <div key={label} style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#f8fafc', padding: '9px 10px' }}>
              <div style={{ fontSize: 10.5, color: '#64748b' }}>{label}</div>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#111827' }}>{value}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11.5, color: '#475569' }}>Last updated: {uploadTime ? new Date(uploadTime).toLocaleString('en-GB') : 'N/A'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
          {(['READY', 'CONDITIONAL', 'QUARANTINED'] as FeatureStatus[]).map((status) => {
            const rows = releaseResults.filter((row) => row.release_status === status)
            return (
              <div key={status} style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#ffffff', padding: '10px 12px', display: 'grid', gap: 6 }}>
                <div style={{ fontSize: 11.5, fontWeight: 700, color: '#111827' }}>{status} items</div>
                {rows.length ? rows.map((row) => (
                  <div key={`${status}-${row.column_name}`} style={{ fontSize: 10.5, color: '#475569' }}>
                    <strong>{row.column_name}</strong>: {row.explanation}
                  </div>
                )) : <div style={{ fontSize: 10.5, color: '#94a3b8' }}>None</div>}
              </div>
            )
          })}
        </div>
      </article>

      <article style={{ borderRadius: 10, border: '1px solid #e2e8f0', background: '#ffffff', padding: 12, display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Recommendation Readiness</div>
        {!isRecommendationCompatible ? (
          <div style={{ borderRadius: 8, border: '1px solid #dbeafe', background: '#eff6ff', color: '#1e3a8a', padding: '10px 12px', fontSize: 11.5 }}>
            This dataset is not recommendation-ready yet. The workflow runs FeatureOps semantic checks only.
          </div>
        ) : (
          <div style={{ borderRadius: 8, border: '1px solid #dbeafe', background: '#eff6ff', color: '#1e3a8a', padding: '10px 12px', fontSize: 11.5 }}>
            Recommendation-ready fields were detected. You can now enable recommendation validation on top of this workflow.
          </div>
        )}
      </article>
    </section>
  )
}
