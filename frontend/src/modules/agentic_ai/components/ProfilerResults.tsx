import React, { useState } from 'react'

interface ColumnProfile {
  column_name: string
  inferred_type: 'numeric' | 'datetime' | 'boolean' | 'text' | 'mixed' | 'unknown'
  missing_percent: number
  unique_percent: number
  min: number | null
  max: number | null
  mean: number | null
  std: number | null
  sample_values: string[]
  scale_pattern: string
  detected_unit: string
  detected_direction: string
}

interface ProfilerResultsProps {
  columnProfiles: ColumnProfile[]
  datasetName: string
  rowCount: number
  columnCount: number
  isLoading?: boolean
}

const TypeIcon = ({ type }: { type: string }) => {
  const icons: Record<string, string> = {
    numeric: '#',
    datetime: '📅',
    boolean: '☑️',
    text: '📝',
    mixed: '⚡',
    unknown: '❓',
  }
  return <span>{icons[type] || '?'}</span>
}

const ScalePatternBadge = ({ pattern }: { pattern: string }) => {
  const colors: Record<string, { bg: string; text: string }> = {
    '0-1': { bg: '#DDD6FE', text: '#4F46E5' },
    '0-100': { bg: '#DBEAFE', text: '#0284C7' },
    count: { bg: '#D1FAE5', text: '#059669' },
    continuous: { bg: '#FEE2E2', text: '#DC2626' },
    'raw_sensor_adc': { bg: '#F3E8FF', text: '#7C3AED' },
  }

  const style = colors[pattern] || { bg: '#F3F4F6', text: '#6B7280' }

  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 600,
        background: style.bg,
        color: style.text,
        padding: '3px 8px',
        borderRadius: 4,
      }}
    >
      {pattern}
    </span>
  )
}

export const ProfilerResults: React.FC<ProfilerResultsProps> = ({
  columnProfiles = [],
  datasetName,
  rowCount,
  columnCount,
  isLoading = false,
}) => {
  const [expandedColumn, setExpandedColumn] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#6B7280' }}>
        Analyzing dataset...
      </div>
    )
  }

  if (!columnProfiles || columnProfiles.length === 0) {
    return (
      <div
        style={{
          padding: 20,
          textAlign: 'center',
          color: '#6B7280',
          border: '1px dashed #D1D5DB',
          borderRadius: 8,
          background: '#FAFAFA',
        }}
      >
        No profile data available
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          paddingBottom: 12,
          borderBottom: '1px solid #E5E7EB',
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#111827' }}>
            Dataset Profile: {datasetName}
          </div>
          <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>
            {rowCount} rows × {columnCount} columns
          </div>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 12,
            fontSize: 11,
          }}
        >
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: '#6B7280' }}>Numeric</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#111827' }}>
              {columnProfiles.filter((c) => c.inferred_type === 'numeric').length}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: '#6B7280' }}>Text</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#111827' }}>
              {columnProfiles.filter((c) => c.inferred_type === 'text').length}
            </div>
          </div>
        </div>
      </div>

      {/* Columns Grid */}
      <div style={{ display: 'grid', gap: 8, maxHeight: 500, overflowY: 'auto' }}>
        {columnProfiles.map((profile) => {
          const isExpanded = expandedColumn === profile.column_name

          return (
            <div
              key={profile.column_name}
              onClick={() =>
                setExpandedColumn(isExpanded ? null : profile.column_name)
              }
              style={{
                padding: 12,
                borderRadius: 8,
                border: '1px solid #E5E7EB',
                background: '#FAFAFA',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as any).style.background = '#F3F4F6'
                ;(e.currentTarget as any).style.borderColor = '#D1D5DB'
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as any).style.background = '#FAFAFA'
                ;(e.currentTarget as any).style.borderColor = '#E5E7EB'
              }}
            >
              {/* Collapsed View */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'auto 1fr auto auto auto',
                  gap: 12,
                  alignItems: 'center',
                }}
              >
                <TypeIcon type={profile.inferred_type} />
                <div style={{ fontSize: 11, fontWeight: 600, color: '#111827' }}>
                  {profile.column_name}
                </div>
                <ScalePatternBadge pattern={profile.scale_pattern} />
                <div style={{ fontSize: 10, color: '#6B7280' }}>
                  {profile.unique_percent > 0.5
                    ? `${(profile.unique_percent * 100).toFixed(0)}% unique`
                    : `${(profile.missing_percent * 100).toFixed(0)}% missing`}
                </div>
                <div
                  style={{
                    fontSize: 16,
                    color: '#6B7280',
                    transition: 'transform 0.2s',
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                  }}
                >
                  ▼
                </div>
              </div>

              {/* Expanded View */}
              {isExpanded && (
                <div style={{ display: 'grid', gap: 12, marginTop: 12, paddingTop: 12, borderTop: '1px solid #E5E7EB' }}>
                  {/* Type & Scale */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr 1fr',
                      gap: 8,
                      fontSize: 10,
                    }}
                  >
                    <div>
                      <div style={{ color: '#6B7280', marginBottom: 2 }}>Type</div>
                      <div style={{ fontWeight: 600, color: '#111827' }}>
                        {profile.inferred_type}
                      </div>
                    </div>
                    <div>
                      <div style={{ color: '#6B7280', marginBottom: 2 }}>Unit</div>
                      <div style={{ fontWeight: 600, color: '#111827' }}>
                        {profile.detected_unit}
                      </div>
                    </div>
                    <div>
                      <div style={{ color: '#6B7280', marginBottom: 2 }}>Direction</div>
                      <div style={{ fontWeight: 600, color: '#111827' }}>
                        {profile.detected_direction}
                      </div>
                    </div>
                  </div>

                  {/* Statistics */}
                  {(profile.inferred_type === 'numeric' || profile.inferred_type === 'mixed') && (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr 1fr 1fr',
                        gap: 8,
                        fontSize: 10,
                        padding: 8,
                        background: '#F0F9FF',
                        borderRadius: 6,
                        border: '1px solid #BFE7FF',
                      }}
                    >
                      <div>
                        <div style={{ color: '#0C4A6E', fontSize: 9 }}>Min</div>
                        <div style={{ fontWeight: 600, color: '#111827' }}>
                          {profile.min?.toFixed(2) || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: '#0C4A6E', fontSize: 9 }}>Max</div>
                        <div style={{ fontWeight: 600, color: '#111827' }}>
                          {profile.max?.toFixed(2) || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: '#0C4A6E', fontSize: 9 }}>Mean</div>
                        <div style={{ fontWeight: 600, color: '#111827' }}>
                          {profile.mean?.toFixed(2) || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: '#0C4A6E', fontSize: 9 }}>Std Dev</div>
                        <div style={{ fontWeight: 600, color: '#111827' }}>
                          {profile.std?.toFixed(2) || 'N/A'}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Sample Values */}
                  <div>
                    <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 4 }}>Sample Values</div>
                    <div style={{ display: 'grid', gap: 2, fontSize: 10 }}>
                      {profile.sample_values.map((val, idx) => (
                        <div
                          key={idx}
                          style={{
                            padding: '4px 8px',
                            background: '#F3F4F6',
                            borderRadius: 4,
                            color: '#374151',
                          }}
                        >
                          {val}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Missing & Unique */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 10 }}>
                    <div
                      style={{
                        padding: 8,
                        background: '#FEF2F2',
                        borderRadius: 6,
                        border: '1px solid #FECACA',
                      }}
                    >
                      <div style={{ color: '#7F1D1D', fontSize: 9 }}>Missing</div>
                      <div style={{ fontWeight: 600, color: '#111827' }}>
                        {(profile.missing_percent * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div
                      style={{
                        padding: 8,
                        background: '#F0FDF4',
                        borderRadius: 6,
                        border: '1px solid #BBFBEE',
                      }}
                    >
                      <div style={{ color: '#065F46', fontSize: 9 }}>Unique</div>
                      <div style={{ fontWeight: 600, color: '#111827' }}>
                        {(profile.unique_percent * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
