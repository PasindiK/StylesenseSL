import React, { useState } from 'react'

interface DriftExplanation {
  column_name: string
  drift_type: 'numeric' | 'categorical' | 'text' | 'relational'
  severity: 'none' | 'low' | 'moderate' | 'high'
  reason: string
  baseline_stats: Record<string, any>
  current_stats: Record<string, any>
  impact: string
  recommendation: string
}

interface DriftExplanationProps {
  drifts: DriftExplanation[]
  isLoading?: boolean
}

const getSeverityColor = (severity: string) => {
  switch (severity) {
    case 'none':
      return { bg: '#F0FDF4', border: '#BBFBEE', text: '#065F46', badge: '#059669' }
    case 'low':
      return { bg: '#FFFBEB', border: '#FEF08A', text: '#92400E', badge: '#CA8A04' }
    case 'moderate':
      return { bg: '#FEF3C7', border: '#FCD34D', text: '#78350F', badge: '#D97706' }
    case 'high':
      return { bg: '#FEF2F2', border: '#FECACA', text: '#7F1D1D', badge: '#DC2626' }
    default:
      return { bg: '#F3F4F6', border: '#E5E7EB', text: '#374151', badge: '#6B7280' }
  }
}

const DriftTypeIcon = ({ type }: { type: string }) => {
  const icons: Record<string, string> = {
    numeric: '📊',
    categorical: '🏷️',
    text: '📝',
    relational: '🔗',
  }
  return <span>{icons[type] || '?'}</span>
}

export const DriftExplanation: React.FC<DriftExplanationProps> = ({
  drifts = [],
  isLoading = false,
}) => {
  const [expandedColumn, setExpandedColumn] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#6B7280' }}>
        Analyzing drifts...
      </div>
    )
  }

  if (!drifts || drifts.length === 0) {
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
        No drift detected
      </div>
    )
  }

  const severityCounts = {
    none: drifts.filter((d) => d.severity === 'none').length,
    low: drifts.filter((d) => d.severity === 'low').length,
    moderate: drifts.filter((d) => d.severity === 'moderate').length,
    high: drifts.filter((d) => d.severity === 'high').length,
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* Header with Summary */}
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
            Drift Explanations
          </div>
          <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>
            {drifts.length} column{drifts.length !== 1 ? 's' : ''} analyzed
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 12,
            fontSize: 11,
          }}
        >
          {[
            { label: 'None', count: severityCounts.none, color: '#059669' },
            { label: 'Low', count: severityCounts.low, color: '#CA8A04' },
            { label: 'Moderate', count: severityCounts.moderate, color: '#D97706' },
            { label: 'High', count: severityCounts.high, color: '#DC2626' },
          ].map((item) => (
            <div key={item.label} style={{ textAlign: 'center' }}>
              <div style={{ color: '#6B7280', fontSize: 10 }}>{item.label}</div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 900,
                  color: item.color,
                  marginTop: 2,
                }}
              >
                {item.count}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Drifts List */}
      <div style={{ display: 'grid', gap: 8, maxHeight: 600, overflowY: 'auto' }}>
        {drifts.map((drift) => {
          const isExpanded = expandedColumn === drift.column_name
          const color = getSeverityColor(drift.severity)

          return (
            <div
              key={drift.column_name}
              onClick={() =>
                setExpandedColumn(isExpanded ? null : drift.column_name)
              }
              style={{
                padding: 12,
                borderRadius: 8,
                border: `1px solid ${color.border}`,
                background: color.bg,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as any).style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as any).style.boxShadow = 'none'
              }}
            >
              {/* Header Row */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'auto auto 1fr auto auto',
                  gap: 12,
                  alignItems: 'center',
                }}
              >
                <DriftTypeIcon type={drift.drift_type} />

                <div style={{ fontSize: 11, fontWeight: 600, color: color.text }}>
                  {drift.column_name}
                </div>

                <div style={{ fontSize: 11, color: color.text, flex: 1 }}>
                  {drift.reason}
                </div>

                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: '#FFFFFF',
                    background: color.badge,
                    padding: '3px 8px',
                    borderRadius: 4,
                    textTransform: 'uppercase',
                  }}
                >
                  {drift.severity}
                </div>

                <div
                  style={{
                    fontSize: 16,
                    color: color.text,
                    transition: 'transform 0.2s',
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                  }}
                >
                  ▼
                </div>
              </div>

              {/* Expanded Details */}
              {isExpanded && (
                <div
                  style={{
                    display: 'grid',
                    gap: 12,
                    marginTop: 12,
                    paddingTop: 12,
                    borderTop: `1px solid ${color.border}`,
                  }}
                >
                  {/* Comparison Tables */}
                  {Object.keys(drift.baseline_stats).length > 0 && (
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 600, color: color.text, marginBottom: 6 }}>
                        Statistics Comparison
                      </div>
                      <div
                        style={{
                          display: 'grid',
                          gap: 4,
                          fontSize: 10,
                        }}
                      >
                        {Object.entries(drift.baseline_stats).map(([key, baselineValue]) => {
                          const currentValue = drift.current_stats[key]
                          const diff =
                            typeof baselineValue === 'number' && typeof currentValue === 'number'
                              ? ((currentValue - baselineValue) / Math.max(Math.abs(baselineValue), 1)) * 100
                              : 0

                          const diffColor =
                            Math.abs(diff) > 20
                              ? '#DC2626'
                              : Math.abs(diff) > 10
                                ? '#D97706'
                                : '#059669'

                          return (
                            <div
                              key={key}
                              style={{
                                display: 'grid',
                                gridTemplateColumns: '100px 1fr 1fr auto',
                                gap: 8,
                                padding: 6,
                                background: 'rgba(255,255,255,0.3)',
                                borderRadius: 4,
                              }}
                            >
                              <div style={{ fontWeight: 600, color: color.text }}>{key}</div>
                              <div style={{ color: color.text }}>
                                Baseline: <strong>{JSON.stringify(baselineValue)}</strong>
                              </div>
                              <div style={{ color: color.text }}>
                                Current: <strong>{JSON.stringify(currentValue)}</strong>
                              </div>
                              <div style={{ color: diffColor, fontWeight: 600 }}>
                                {diff > 0 ? '+' : ''}{diff.toFixed(1)}%
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* Impact */}
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 600, color: color.text, marginBottom: 4 }}>
                      Impact
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: color.text,
                        padding: 8,
                        background: 'rgba(255,255,255,0.5)',
                        borderRadius: 4,
                        lineHeight: 1.5,
                      }}
                    >
                      {drift.impact}
                    </div>
                  </div>

                  {/* Recommendation */}
                  <div
                    style={{
                      padding: 8,
                      background: 'rgba(255,255,255,0.3)',
                      borderRadius: 4,
                      borderLeft: `3px solid ${color.badge}`,
                    }}
                  >
                    <div style={{ fontSize: 10, fontWeight: 600, color: color.text, marginBottom: 4 }}>
                      Recommendation
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: color.text,
                        lineHeight: 1.5,
                      }}
                    >
                      {drift.recommendation}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <button
                      type="button"
                      style={{
                        flex: 1,
                        padding: '6px 12px',
                        borderRadius: 4,
                        border: `1px solid ${color.badge}`,
                        background: 'transparent',
                        color: color.text,
                        fontSize: 10,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                      onClick={(e) => {
                        e.stopPropagation()
                        // Handle investigate
                      }}
                    >
                      Investigate
                    </button>
                    <button
                      type="button"
                      style={{
                        flex: 1,
                        padding: '6px 12px',
                        borderRadius: 4,
                        border: `1px solid ${color.badge}`,
                        background: 'transparent',
                        color: color.text,
                        fontSize: 10,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                      onClick={(e) => {
                        e.stopPropagation()
                        // Handle accept
                      }}
                    >
                      Accept Change
                    </button>
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
