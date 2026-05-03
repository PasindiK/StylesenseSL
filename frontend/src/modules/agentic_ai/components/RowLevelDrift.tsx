import React, { useState } from 'react'

interface RowDrift {
  row_id: number
  row_index: number
  status: 'SAFE' | 'CONDITIONAL' | 'QUARANTINED'
  confidence: number
  affected_columns: string[]
  reasons: string[]
  internal_similarity: number
  external_similarity: number
}

interface RowLevelDriftProps {
  rowDrifts: RowDrift[]
  totalRows: number
  isLoading?: boolean
}

const getStatusColor = (status: string) => {
  switch (status) {
    case 'SAFE':
      return { bg: '#F0FDF4', border: '#10B981', text: '#065F46', badge: '#059669' }
    case 'CONDITIONAL':
      return { bg: '#FFFBEB', border: '#F59E0B', text: '#92400E', badge: '#D97706' }
    case 'QUARANTINED':
      return { bg: '#FEF2F2', border: '#EF4444', text: '#7F1D1D', badge: '#DC2626' }
    default:
      return { bg: '#F3F4F6', border: '#D1D5DB', text: '#374151', badge: '#6B7280' }
  }
}

export const RowLevelDrift: React.FC<RowLevelDriftProps> = ({
  rowDrifts = [],
  totalRows,
  isLoading = false,
}) => {
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null)
  const [filterStatus, setFilterStatus] = useState<'ALL' | 'SAFE' | 'CONDITIONAL' | 'QUARANTINED'>('ALL')

  if (isLoading) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#6B7280' }}>
        Analyzing rows...
      </div>
    )
  }

  if (!rowDrifts || rowDrifts.length === 0) {
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
        No row-level data available
      </div>
    )
  }

  // Filter rows
  const filteredRows =
    filterStatus === 'ALL' ? rowDrifts : rowDrifts.filter((r) => r.status === filterStatus)

  // Count by status
  const statusCounts = {
    SAFE: rowDrifts.filter((r) => r.status === 'SAFE').length,
    CONDITIONAL: rowDrifts.filter((r) => r.status === 'CONDITIONAL').length,
    QUARANTINED: rowDrifts.filter((r) => r.status === 'QUARANTINED').length,
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
            Row-Level Drift Analysis
          </div>
          <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>
            {rowDrifts.length} of {totalRows} rows analyzed
          </div>
        </div>

        {/* Filter Buttons */}
        <div style={{ display: 'flex', gap: 8 }}>
          {['ALL', 'SAFE', 'CONDITIONAL', 'QUARANTINED'].map((status) => (
            <button
              key={status}
              type="button"
              onClick={() =>
                setFilterStatus(status as 'ALL' | 'SAFE' | 'CONDITIONAL' | 'QUARANTINED')
              }
              style={{
                padding: '6px 12px',
                borderRadius: 4,
                border: filterStatus === status ? 'none' : '1px solid #D1D5DB',
                background:
                  filterStatus === status
                    ? status === 'SAFE'
                      ? '#10B981'
                      : status === 'CONDITIONAL'
                        ? '#F59E0B'
                        : status === 'QUARANTINED'
                          ? '#EF4444'
                          : '#6B7280'
                    : '#FFFFFF',
                color:
                  filterStatus === status
                    ? '#FFFFFF'
                    : status === 'SAFE'
                      ? '#059669'
                      : status === 'CONDITIONAL'
                        ? '#92400E'
                        : status === 'QUARANTINED'
                          ? '#7F1D1D'
                          : '#6B7280',
                fontSize: 10,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {status} ({status === 'ALL' ? rowDrifts.length : statusCounts[status as keyof typeof statusCounts]})
            </button>
          ))}
        </div>
      </div>

      {/* Status Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        <div
          style={{
            padding: 12,
            borderRadius: 8,
            background: '#F0FDF4',
            border: '1px solid #BBFBEE',
          }}
        >
          <div style={{ fontSize: 10, color: '#065F46', fontWeight: 600 }}>Safe Rows</div>
          <div style={{ fontSize: 18, fontWeight: 900, color: '#10B981', marginTop: 4 }}>
            {statusCounts.SAFE}
          </div>
          <div style={{ fontSize: 9, color: '#059669', marginTop: 2 }}>
            {((statusCounts.SAFE / rowDrifts.length) * 100).toFixed(0)}%
          </div>
        </div>

        <div
          style={{
            padding: 12,
            borderRadius: 8,
            background: '#FFFBEB',
            border: '1px solid #FEF08A',
          }}
        >
          <div style={{ fontSize: 10, color: '#92400E', fontWeight: 600 }}>Conditional Rows</div>
          <div style={{ fontSize: 18, fontWeight: 900, color: '#F59E0B', marginTop: 4 }}>
            {statusCounts.CONDITIONAL}
          </div>
          <div style={{ fontSize: 9, color: '#D97706', marginTop: 2 }}>
            {((statusCounts.CONDITIONAL / rowDrifts.length) * 100).toFixed(0)}%
          </div>
        </div>

        <div
          style={{
            padding: 12,
            borderRadius: 8,
            background: '#FEF2F2',
            border: '1px solid #FECACA',
          }}
        >
          <div style={{ fontSize: 10, color: '#7F1D1D', fontWeight: 600 }}>Quarantined Rows</div>
          <div style={{ fontSize: 18, fontWeight: 900, color: '#EF4444', marginTop: 4 }}>
            {statusCounts.QUARANTINED}
          </div>
          <div style={{ fontSize: 9, color: '#DC2626', marginTop: 2 }}>
            {((statusCounts.QUARANTINED / rowDrifts.length) * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      {/* Rows List */}
      <div style={{ display: 'grid', gap: 6, maxHeight: 500, overflowY: 'auto' }}>
        {filteredRows.map((row) => {
          const isExpanded = expandedRowId === row.row_id
          const color = getStatusColor(row.status)

          return (
            <div
              key={row.row_id}
              onClick={() => setExpandedRowId(isExpanded ? null : row.row_id)}
              style={{
                padding: 10,
                borderRadius: 6,
                border: `1px solid ${color.border}`,
                background: color.bg,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as any).style.boxShadow = '0 1px 4px rgba(0,0,0,0.1)'
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as any).style.boxShadow = 'none'
              }}
            >
              {/* Row Header */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'auto auto 1fr auto auto',
                  gap: 10,
                  alignItems: 'center',
                }}
              >
                <div style={{ fontSize: 10, fontWeight: 600, color: color.text }}>Row {row.row_index}</div>

                <div
                  style={{
                    fontSize: 9,
                    fontWeight: 700,
                    color: '#FFFFFF',
                    background: color.badge,
                    padding: '2px 6px',
                    borderRadius: 3,
                    textTransform: 'uppercase',
                  }}
                >
                  {row.status}
                </div>

                <div style={{ fontSize: 9, color: color.text }}>
                  {row.affected_columns.join(', ')}
                </div>

                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: color.badge,
                  }}
                >
                  {(row.confidence * 100).toFixed(0)}%
                </div>

                <div
                  style={{
                    fontSize: 14,
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
                    gap: 8,
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: `1px solid ${color.border}`,
                  }}
                >
                  {/* Similarity Scores */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 9 }}>
                    <div
                      style={{
                        padding: 6,
                        background: 'rgba(255,255,255,0.3)',
                        borderRadius: 4,
                      }}
                    >
                      <div style={{ color: color.text, fontWeight: 600, marginBottom: 2 }}>
                        Internal Similarity
                      </div>
                      <div style={{ color: color.text, fontWeight: 700, fontSize: 12 }}>
                        {(row.internal_similarity * 100).toFixed(1)}%
                      </div>
                      <div
                        style={{
                          marginTop: 4,
                          height: 4,
                          background: 'rgba(0,0,0,0.1)',
                          borderRadius: 2,
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            height: '100%',
                            background: color.badge,
                            width: `${row.internal_similarity * 100}%`,
                          }}
                        />
                      </div>
                    </div>

                    <div
                      style={{
                        padding: 6,
                        background: 'rgba(255,255,255,0.3)',
                        borderRadius: 4,
                      }}
                    >
                      <div style={{ color: color.text, fontWeight: 600, marginBottom: 2 }}>
                        External Similarity
                      </div>
                      <div style={{ color: color.text, fontWeight: 700, fontSize: 12 }}>
                        {(row.external_similarity * 100).toFixed(1)}%
                      </div>
                      <div
                        style={{
                          marginTop: 4,
                          height: 4,
                          background: 'rgba(0,0,0,0.1)',
                          borderRadius: 2,
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            height: '100%',
                            background: color.badge,
                            width: `${row.external_similarity * 100}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Affected Columns */}
                  <div>
                    <div style={{ fontSize: 9, fontWeight: 600, color: color.text, marginBottom: 4 }}>
                      Affected Columns ({row.affected_columns.length})
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: 4 }}>
                      {row.affected_columns.map((col) => (
                        <div
                          key={col}
                          style={{
                            padding: '3px 6px',
                            background: 'rgba(255,255,255,0.5)',
                            borderRadius: 3,
                            fontSize: 8,
                            color: color.text,
                            fontWeight: 600,
                            textAlign: 'center',
                          }}
                        >
                          {col}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Reasons */}
                  {row.reasons.length > 0 && (
                    <div>
                      <div style={{ fontSize: 9, fontWeight: 600, color: color.text, marginBottom: 4 }}>
                        Reasons
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 16, display: 'grid', gap: 3 }}>
                        {row.reasons.map((reason, idx) => (
                          <li key={idx} style={{ fontSize: 8, color: color.text }}>
                            {reason}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Action Button */}
                  <button
                    type="button"
                    style={{
                      padding: '6px 12px',
                      borderRadius: 4,
                      border: `1px solid ${color.badge}`,
                      background: 'transparent',
                      color: color.text,
                      fontSize: 9,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                    onClick={(e) => {
                      e.stopPropagation()
                      // Handle view details
                    }}
                  >
                    View Full Row Data
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 8,
          marginTop: 12,
          padding: '8px 0',
          borderTop: '1px solid #E5E7EB',
          fontSize: 9,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#6B7280' }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#10B981' }} />
          Matches baselines
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#6B7280' }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#F59E0B' }} />
          Market shift detected
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#6B7280' }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#EF4444' }} />
          Genuine drift
        </div>
      </div>
    </div>
  )
}
