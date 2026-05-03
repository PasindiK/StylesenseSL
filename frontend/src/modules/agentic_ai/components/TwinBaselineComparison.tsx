import React from 'react'

type ColumnProfile = {
  column_name: string
  inferred_type: 'numeric' | 'datetime' | 'boolean' | 'text' | 'mixed' | 'unknown'
  missing_percent: number
  unique_percent: number
  min: number | null
  max: number | null
  mean: number | null
  std: number | null
  sample_values: string[]
  row_count: number
  column_count: number
  scale_pattern: string
}

type SemanticProfile = {
  column_name: string
  approved_or_detected_meaning: string
  generic_role: string
}

type BaselineProfile = {
  dataset_name: string
  created_at: string
  row_count: number
  column_count: number
  column_profiles?: ColumnProfile[]
  semantic_profiles?: SemanticProfile[]
}

interface TwinBaselineComparisonProps {
  internalBaseline?: BaselineProfile | null
  currentUpload?: BaselineProfile | null
  externalBaseline?: BaselineProfile | null
  isLoading?: boolean
}

const ProfileSummary: React.FC<{ profile: BaselineProfile | undefined | null; label: string; color: string }> = ({
  profile,
  label,
  color,
}) => {
  if (!profile) {
    return (
      <div style={{ display: 'grid', gap: 8, padding: 12, borderRadius: 8, background: '#F3F4F6', border: '1px dashed #D1D5DB' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#6B7280' }}>{label}</div>
        <div style={{ fontSize: 11, color: '#9CA3AF', fontStyle: 'italic' }}>No baseline available</div>
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gap: 8, padding: 12, borderRadius: 8, border: `1px solid ${color}`, background: 'rgba(255, 255, 255, 0.3)' }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          color,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: color }} />
        {label}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 11 }}>
        <div>
          <div style={{ color: '#6B7280', fontSize: 10, marginBottom: 2 }}>Name</div>
          <div style={{ color: '#111827', fontWeight: 600, wordBreak: 'break-word' }}>{profile.dataset_name}</div>
        </div>
        <div>
          <div style={{ color: '#6B7280', fontSize: 10, marginBottom: 2 }}>Rows</div>
          <div style={{ color: '#111827', fontWeight: 600 }}>{profile.row_count}</div>
        </div>
        <div>
          <div style={{ color: '#6B7280', fontSize: 10, marginBottom: 2 }}>Columns</div>
          <div style={{ color: '#111827', fontWeight: 600 }}>{profile.column_count}</div>
        </div>
        <div>
          <div style={{ color: '#6B7280', fontSize: 10, marginBottom: 2 }}>Created</div>
          <div style={{ color: '#111827', fontWeight: 600, fontSize: 10 }}>
            {profile.created_at ? new Date(profile.created_at).toLocaleDateString() : 'N/A'}
          </div>
        </div>
      </div>

      {profile.column_profiles && profile.column_profiles.length > 0 && (
        <div>
          <div style={{ color: '#6B7280', fontSize: 10, marginBottom: 4 }}>Sample Columns ({profile.column_profiles.length})</div>
          <div style={{ display: 'grid', gap: 3 }}>
            {profile.column_profiles.slice(0, 4).map((col, idx) => (
              <div key={idx} style={{ fontSize: 10, color: '#374151' }}>
                <span style={{ fontWeight: 600 }}>{col.column_name}</span>
                <span style={{ color: '#9CA3AF', marginLeft: 4 }}>({col.inferred_type})</span>
              </div>
            ))}
            {profile.column_profiles.length > 4 && (
              <div style={{ fontSize: 10, color: '#6B7280', fontStyle: 'italic' }}>
                +{profile.column_profiles.length - 4} more columns
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const ColumnComparison: React.FC<{ columns: { internal?: ColumnProfile; current?: ColumnProfile; external?: ColumnProfile } }> = ({
  columns,
}) => {
  const names = new Set([
    ...(columns.internal ? [columns.internal.column_name] : []),
    ...(columns.current ? [columns.current.column_name] : []),
    ...(columns.external ? [columns.external.column_name] : []),
  ])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {Array.from(names).map((colName) => {
        const internal = columns.internal?.column_name === colName ? columns.internal : undefined
        const current = columns.current?.column_name === colName ? columns.current : undefined
        const external = columns.external?.column_name === colName ? columns.external : undefined

        const internalType = internal?.inferred_type ?? 'missing'
        const currentType = current?.inferred_type ?? 'missing'
        const externalType = external?.inferred_type ?? 'missing'

        const typesMatch = internalType === currentType && currentType === externalType && internalType !== 'missing'

        return (
          <div
            key={colName}
            style={{
              display: 'grid',
              gap: 8,
              padding: 10,
              borderRadius: 6,
              border: `1px solid ${typesMatch ? '#D1D5DB' : '#FCA5A5'}`,
              background: typesMatch ? '#FAFAFA' : '#FEF2F2',
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, color: '#111827' }}>
              {colName}
              {!typesMatch && (
                <span
                  style={{
                    marginLeft: 8,
                    fontSize: 9,
                    color: '#DC2626',
                    fontWeight: 600,
                    background: '#FEE2E2',
                    padding: '2px 6px',
                    borderRadius: 3,
                  }}
                >
                  TYPE MISMATCH
                </span>
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, fontSize: 10 }}>
              <div>
                <div style={{ color: '#6B7280', marginBottom: 2 }}>Internal</div>
                <div style={{ color: '#111827', fontWeight: 500 }}>
                  {internal ? internal.inferred_type : '—'}
                </div>
                {internal && (
                  <div style={{ color: '#9CA3AF', fontSize: 9, marginTop: 2 }}>
                    {internal.column_count ? `${internal.row_count} rows` : ''}
                  </div>
                )}
              </div>
              <div>
                <div style={{ color: '#6B7280', marginBottom: 2 }}>Current</div>
                <div style={{ color: '#111827', fontWeight: 500 }}>
                  {current ? current.inferred_type : '—'}
                </div>
                {current && (
                  <div style={{ color: '#9CA3AF', fontSize: 9, marginTop: 2 }}>
                    {current.column_count ? `${current.row_count} rows` : ''}
                  </div>
                )}
              </div>
              <div>
                <div style={{ color: '#6B7280', marginBottom: 2 }}>External</div>
                <div style={{ color: '#111827', fontWeight: 500 }}>
                  {external ? external.inferred_type : '—'}
                </div>
                {external && (
                  <div style={{ color: '#9CA3AF', fontSize: 9, marginTop: 2 }}>
                    {external.column_count ? `${external.row_count} rows` : ''}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export const TwinBaselineComparison: React.FC<TwinBaselineComparisonProps> = ({
  internalBaseline,
  currentUpload,
  externalBaseline,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#6B7280' }}>
        Loading baseline comparison...
      </div>
    )
  }

  const hasAnyBaseline = internalBaseline || currentUpload || externalBaseline

  if (!hasAnyBaseline) {
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
        No baselines available for comparison. Upload a dataset first.
      </div>
    )
  }

  // Build columns map for comparison
  const allColumns = new Map<string, { internal?: ColumnProfile; current?: ColumnProfile; external?: ColumnProfile }>()

  internalBaseline?.column_profiles?.forEach((col) => {
    if (!allColumns.has(col.column_name)) allColumns.set(col.column_name, {})
    allColumns.get(col.column_name)!.internal = col
  })

  currentUpload?.column_profiles?.forEach((col) => {
    if (!allColumns.has(col.column_name)) allColumns.set(col.column_name, {})
    allColumns.get(col.column_name)!.current = col
  })

  externalBaseline?.column_profiles?.forEach((col) => {
    if (!allColumns.has(col.column_name)) allColumns.set(col.column_name, {})
    allColumns.get(col.column_name)!.external = col
  })

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <ProfileSummary profile={internalBaseline} label="Internal Baseline" color="#0EA5E9" />
        <ProfileSummary profile={currentUpload} label="Current Upload" color="#8B5CF6" />
        <ProfileSummary profile={externalBaseline} label="External Market" color="#EC4899" />
      </div>

      {allColumns.size > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#111827', marginBottom: 12 }}>
            Column-by-Column Alignment ({allColumns.size} columns)
          </div>
          <ColumnComparison columns={Object.fromEntries(allColumns)} />
        </div>
      )}
    </div>
  )
}
