import React from 'react'

function slugify(s: string) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

/** When `family_id` was not persisted (legacy uploads), infer a display family from dataset name vs registry. */
function linkedFamilyDisplay(run: any, families: any[]): { text: string; title?: string } {
  if (run.family_id) {
    const fam = families.find((f: any) => f.family_id === run.family_id)
    return { text: fam?.family_name || String(run.family_id) }
  }
  const ds = String(run.dataset_name || '').trim()
  if (!ds) return { text: 'Not linked', title: 'No dataset name on this run.' }
  const dsSlug = slugify(ds)
  for (const fam of families) {
    if (fam.is_architecture_template) continue
    const nameSlug = slugify(String(fam.family_name || ''))
    const idStr = String(fam.family_id || '')
    if (nameSlug && (dsSlug === nameSlug || dsSlug.includes(nameSlug) || nameSlug.includes(dsSlug))) {
      return {
        text: `${fam.family_name} (inferred)`,
        title: 'No family_id stored for this upload; matched from dataset name. New uploads from DE Workflow with a selected family persist linkage.',
      }
    }
    if (idStr && ds.toLowerCase().includes(idStr.toLowerCase())) {
      return {
        text: `${fam.family_name} (inferred)`,
        title: 'No family_id stored; matched from dataset name containing family id.',
      }
    }
  }
  return {
    text: 'Not linked',
    title: 'Select a baseline family in DE Workflow before the upload finishes so the drift run stores family_id.',
  }
}

function summarizeReleaseResults(results: Array<{ release_status: string }>) {
  const counts = { READY: 0, CONDITIONAL: 0, QUARANTINED: 0 }
  for (const row of results) {
    const k = row.release_status as keyof typeof counts
    if (k in counts) counts[k] += 1
  }
  return `${counts.READY} READY / ${counts.CONDITIONAL} CONDITIONAL / ${counts.QUARANTINED} QUARANTINED`
}

export type FeatureOpsDatasetHistoryTablesProps = {
  familiesDisplayRows: any[]
  families: any[]
  driftRuns: any[]
  viewFamilyId: string
  viewFamilyVersions: any[]
  selectedCompareVersions: number[]
  toggleCompareVersion: (versionNumber: number) => void
  versionPairComparison: any | null
  historyModalViewMode: 'comparison' | 'left' | 'right'
  setHistoryModalViewMode: (mode: 'comparison' | 'left' | 'right') => void
  setViewFamilyId: (id: string) => void
  setSelectedCompareVersions: React.Dispatch<React.SetStateAction<number[]>>
  openFilePickerForVersion: (familyId: string) => void
  loadVersion: (familyId: string, versionNumber: number) => Promise<void>
  loadDriftRun: (run: any) => Promise<void>
  deleteFamily: (familyId: string) => Promise<void>
  deleteDriftRun: (runId: string) => Promise<void>
  approveVersion: (familyId: string, versionNumber: number) => Promise<void>
  deleteVersion: (familyId: string, versionNumber: number) => Promise<void>
  /** Called after Load / Load This Upload so the modal can close or the dashboard can switch tab. */
  afterNavigate?: () => void
}

export function FeatureOpsDatasetHistoryTables(props: FeatureOpsDatasetHistoryTablesProps) {
  const {
    familiesDisplayRows,
    families,
    driftRuns,
    viewFamilyId,
    viewFamilyVersions,
    selectedCompareVersions,
    toggleCompareVersion,
    versionPairComparison,
    historyModalViewMode,
    setHistoryModalViewMode,
    setViewFamilyId,
    setSelectedCompareVersions,
    openFilePickerForVersion,
    loadVersion,
    loadDriftRun,
    deleteFamily,
    deleteDriftRun,
    approveVersion,
    deleteVersion,
    afterNavigate,
  } = props

  return (
    <>
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
            {familiesDisplayRows.map((family: any) => (
              <tr key={family.family_id}>
                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>
                  {family.family_name}
                  {family.is_architecture_template ? (
                    <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, color: '#1d4ed8', border: '1px solid #bfdbfe', borderRadius: 6, padding: '1px 6px', verticalAlign: 'middle' }}>template</span>
                  ) : null}
                </td>
                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', textAlign: 'right', color: '#0f172a' }}>{family.is_architecture_template ? '—' : (family.version_count ?? family.versions.length)}</td>
                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{family.is_architecture_template ? '—' : `v${family.latest_version}`}</td>
                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{family.is_architecture_template ? '—' : new Date(family.updated_at).toLocaleDateString('en-GB', { month: 'short', day: '2-digit' })}</td>
                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {!family.is_architecture_template ? (
                      <button
                        type="button"
                        onClick={() => {
                          setViewFamilyId(family.family_id)
                          setSelectedCompareVersions([])
                          setHistoryModalViewMode('comparison')
                        }}
                        style={{ borderRadius: 999, border: '1px solid #94a3b8', background: '#ffffff', color: '#0f172a', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer', fontWeight: 700 }}
                      >
                        View Versions
                      </button>
                    ) : null}
                    <button type="button" onClick={() => openFilePickerForVersion(family.family_id)} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>{family.is_architecture_template ? 'Create family' : '+ Add Dataset'}</button>
                    {!family.is_architecture_template ? (
                      <button
                        type="button"
                        onClick={() => {
                          void loadVersion(family.family_id, family.approved_baseline_version || family.latest_version)
                          afterNavigate?.()
                        }}
                        style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}
                      >
                        Load
                      </button>
                    ) : null}
                    {!family.is_architecture_template ? (
                      <button type="button" onClick={() => void deleteFamily(family.family_id)} style={{ borderRadius: 999, border: '1px solid #fecaca', background: '#fff1f2', color: '#b91c1c', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer', fontWeight: 700 }}>Delete Family</button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: 'grid', gap: 10 }}>
        <div className="featureops-history-section-title" style={{ fontSize: 13 }}>Uploaded Dataset History</div>
        <div className="featureops-history-subtle" style={{ fontSize: 11.5 }}>
          These rows are upload events only. They are not directly comparable versions. To compare drift, open a family below and select two saved registry versions from that family.
        </div>
        {!driftRuns.length ? (
          <div style={{ borderRadius: 8, border: '1px dashed #cbd5e1', background: '#f1f5f9', color: '#334155', fontWeight: 600, padding: '12px', fontSize: 11.5 }}>
            No upload events recorded yet.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#0f172a' }}>
              <thead>
                <tr style={{ background: '#e2e8f0' }}>
                  {['Dataset Name', 'Uploaded At', 'Linked Family', 'Release Summary'].map((header) => (
                    <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #cbd5e1', color: '#1e293b', fontWeight: 800 }}>{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {driftRuns.slice().reverse().map((run: any) => {
                  const linked = linkedFamilyDisplay(run, families)
                  return (
                  <tr key={run.run_id}>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', fontWeight: 700, color: '#0f172a' }}>{run.dataset_name}</td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', color: '#1e293b', fontWeight: 600 }}>{new Date(run.created_at).toLocaleString('en-GB')}</td>
                    <td
                      style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', color: '#1e293b', fontWeight: 600 }}
                      title={linked.title}
                    >
                      {linked.text}
                    </td>
                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{ color: '#334155', fontWeight: 600 }}>{summarizeReleaseResults(run.release_results || [])}</span>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          <button
                            type="button"
                            onClick={() => {
                              void loadDriftRun(run)
                              afterNavigate?.()
                            }}
                            style={{ borderRadius: 999, border: '1px solid #64748b', background: '#ffffff', color: '#0f172a', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer', fontWeight: 700 }}
                          >
                            Load This Upload
                          </button>
                          <button type="button" onClick={() => void deleteDriftRun(run.run_id)} style={{ borderRadius: 999, border: '1px solid #fecaca', background: '#fff1f2', color: '#b91c1c', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer', fontWeight: 700 }}>
                            Delete
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {viewFamilyId && (
          <div style={{ display: 'grid', gap: 8, paddingTop: 12, borderTop: '2px solid #94a3b8' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <div className="featureops-history-section-title" style={{ fontSize: 12 }}>Registry versions - {families.find((family: any) => family.family_id === viewFamilyId)?.family_name || viewFamilyId}</div>
              <div className="featureops-history-subtle" style={{ fontSize: 11.5 }}>
                Only saved registry versions in this same family can be compared. Uploaded Dataset History rows above are upload events, not comparable family versions.
              </div>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#0f172a' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    {['Compare', 'Version', 'File Name', 'Created Date', 'Rows', 'Columns', 'Release Summary', 'Actions'].map((header) => (
                      <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {viewFamilyVersions.map((version: any) => (
                    <tr key={version.version_id}>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                        <input type="checkbox" checked={selectedCompareVersions.includes(version.version_number)} onChange={() => toggleCompareVersion(version.version_number)} />
                      </td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9', fontWeight: 700 }}>v{version.version_number}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{version.file_name || version.dataset_name}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{new Date(version.created_at).toLocaleString('en-GB')}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{version.row_count}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{version.column_count}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{summarizeReleaseResults(version.release_results)}</td>
                      <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          <button
                            type="button"
                            onClick={() => {
                              void loadVersion(viewFamilyId, version.version_number)
                              afterNavigate?.()
                            }}
                            style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}
                          >
                            Load
                          </button>
                          <button type="button" onClick={() => void approveVersion(viewFamilyId, version.version_number)} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer' }}>Set As Baseline</button>
                          <button type="button" onClick={() => void deleteVersion(viewFamilyId, version.version_number)} style={{ borderRadius: 999, border: '1px solid #fecaca', background: '#fff1f2', color: '#b91c1c', padding: '4px 8px', fontSize: 10.5, cursor: 'pointer', fontWeight: 700 }}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {viewFamilyVersions.length < 2 && (
              <div style={{ borderRadius: 8, border: '1px solid #dbeafe', background: '#eff6ff', color: '#1e3a8a', padding: '10px 12px', fontSize: 11.5 }}>
                This family currently has only {viewFamilyVersions.length} saved registry version{viewFamilyVersions.length === 1 ? '' : 's'}. Add another dataset as a new version in this same family to enable comparison.
              </div>
            )}
            {versionPairComparison && (
              <div className="featureops-history-compare-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>Compared versions: v{versionPairComparison.left.version_number} vs v{versionPairComparison.right.version_number}</div>
                    <div style={{ fontSize: 11, color: '#475569' }}>Columns compared: {versionPairComparison.comparedColumns} | No drift: {versionPairComparison.severityCounts.NONE} | Low drift: {versionPairComparison.severityCounts.LOW} | Moderate drift: {versionPairComparison.severityCounts.MODERATE} | High drift: {versionPairComparison.severityCounts.HIGH}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <button type="button" className={`featureops-filter-pill${historyModalViewMode === 'left' ? ' active' : ''}`} onClick={() => setHistoryModalViewMode('left')}>View v{versionPairComparison.left.version_number} Summary</button>
                    <button type="button" className={`featureops-filter-pill${historyModalViewMode === 'right' ? ' active' : ''}`} onClick={() => setHistoryModalViewMode('right')}>View v{versionPairComparison.right.version_number} Summary</button>
                    <button type="button" className={`featureops-filter-pill${historyModalViewMode === 'comparison' ? ' active' : ''}`} onClick={() => setHistoryModalViewMode('comparison')}>View Comparison</button>
                  </div>
                </div>
                <div style={{ overflowX: 'auto', marginTop: 10 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#0f172a' }}>
                    <thead>
                      <tr style={{ background: '#eef4fb' }}>
                        {(historyModalViewMode === 'comparison'
                          ? ['Column', `v${versionPairComparison.left.version_number} Meaning`, `v${versionPairComparison.right.version_number} Meaning`, `v${versionPairComparison.left.version_number} Scale`, `v${versionPairComparison.right.version_number} Scale`, 'Drift', 'Release', 'Reason']
                          : ['Column', 'Role', 'Scale', 'Release', 'Summary', 'Created']).map((header) => (
                          <th key={header} style={{ textAlign: 'left', padding: '7px 6px', borderBottom: '1px solid #dbe5f0', color: '#334155' }}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(historyModalViewMode === 'comparison'
                        ? versionPairComparison.external.map((row: any) => {
                            const release = versionPairComparison.releaseByColumn[row.column_name]
                            const leftScale = versionPairComparison.left.semantic_profiles.find((item: any) => item.column_name === row.column_name)?.detected_scale || '-'
                            const rightScale = versionPairComparison.right.semantic_profiles.find((item: any) => item.column_name === row.column_name)?.detected_scale || '-'
                            return (
                              <tr key={`compare-${row.column_name}`}>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', fontWeight: 700 }}>{row.column_name}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{row.baseline_meaning}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{row.current_detected_meaning}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{leftScale}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{rightScale}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{row.drift_severity}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{release?.release_status || '-'}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>{row.evidence.join(' ') || release?.explanation || 'stable'}</td>
                              </tr>
                            )
                          })
                        : (historyModalViewMode === 'left' ? versionPairComparison.left : versionPairComparison.right).semantic_profiles.map((profile: any) => {
                            const source = historyModalViewMode === 'left' ? versionPairComparison.left : versionPairComparison.right
                            const release = source.release_results.find((item: any) => item.column_name === profile.column_name)
                            return (
                              <tr key={`${historyModalViewMode}-${profile.column_name}`}>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', fontWeight: 700 }}>{profile.column_name}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{profile.generic_role}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{profile.detected_scale}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{release?.release_status || '-'}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>{profile.approved_or_detected_meaning}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>{new Date(source.created_at).toLocaleString('en-GB')}</td>
                              </tr>
                            )
                          }))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
