import type { DragEvent, RefObject } from 'react'

type Props = {
  loading: boolean
  overview: any
  joinOptions: any
  joinResult: any
  joinBusy: boolean
  leftDataset: string
  rightDataset: string
  setLeftDataset: (value: string) => void
  setRightDataset: (value: string) => void
  selectedRelationshipKey: string
  setSelectedRelationshipKey: (value: string) => void
  runJoin: () => Promise<void>
  intakeFilePath: string
  setIntakeFilePath: (value: string) => void
  intakeDatasetName: string
  setIntakeDatasetName: (value: string) => void
  intakeFiles: File[]
  intakeBusy: boolean
  intakeResult: any
  hasIntakeRun: boolean
  intakeSteps: Array<{ label: string; status: 'pending' | 'running' | 'completed' }>
  intakeReportReady: boolean
  downloadIntakeReport: () => void
  dragActive: boolean
  setDragActive: (value: boolean) => void
  intakeFileInputRef: RefObject<HTMLInputElement | null>
  handlePickedFiles: (files: File[] | null) => void
  handleDrop: (e: DragEvent<HTMLDivElement>) => void
  runIntake: () => Promise<void>
  formatNumber: (value: number) => string
  decisionClass: (decision: string) => string
}

export default function JoinStudioPage({
  loading,
  overview,
  joinOptions,
  joinResult,
  joinBusy,
  leftDataset,
  rightDataset,
  setLeftDataset,
  setRightDataset,
  selectedRelationshipKey,
  setSelectedRelationshipKey,
  runJoin,
  intakeFilePath,
  setIntakeFilePath,
  intakeDatasetName,
  setIntakeDatasetName,
  intakeFiles,
  intakeBusy,
  intakeResult,
  hasIntakeRun,
  intakeSteps,
  intakeReportReady,
  downloadIntakeReport,
  dragActive,
  setDragActive,
  intakeFileInputRef,
  handlePickedFiles,
  handleDrop,
  runIntake,
  formatNumber,
  decisionClass,
}: Props) {
  function confidenceBand(confidence: number): 'strong' | 'probable' | 'weak' {
    if (confidence > 0.9) return 'strong'
    if (confidence >= 0.6) return 'probable'
    return 'weak'
  }

  if (!overview) {
    return (
      <section className="df-tab-content">
        <article className="glass-card df-state-card">
          <h3>{loading ? 'Loading Join Studio...' : 'Join Studio Not Ready Yet'}</h3>
          <p className="muted-text">
            {loading
              ? 'Waiting for overview metadata to populate dataset selectors...'
              : 'Overview metadata is required before join operations can run. Use "Refresh Live Data".'}
          </p>
        </article>
      </section>
    )
  }

  const intakeSuggestions = (intakeResult?.suggestions as Array<any> | undefined) || []
  const joinSuggestions = (joinOptions?.suggestions as Array<any> | undefined) || []
  const discoveryRows = !hasIntakeRun ? [] : intakeSuggestions.length > 0 ? intakeSuggestions : joinSuggestions

  const joinDecisionMessage =
    !hasIntakeRun
      ? 'Run new dataset intake to evaluate join decisions for the latest uploaded data.'
      : joinOptions?.mode === 'auto_ready'
      ? 'One strong relationship detected. System can execute auto join safely.'
      : joinOptions?.mode === 'manual_required_multiple'
        ? 'Multiple strong/probable matches detected. Manual confirmation required.'
        : joinOptions?.mode === 'manual_required_weak'
          ? 'Only weak matches available. Manual confirmation required.'
          : 'No relationship candidates found yet for the selected pair.'

  function modelScores(row: any): { lr: string; secondaryLabel: string; secondary: string; combined: string } {
    const featureVector = row?.feature_vector || {}
    const modelsUsed = featureVector?.models_used || {}
    const lr = typeof modelsUsed.LR === 'number' ? modelsUsed.LR.toFixed(3) : '-'
    const secondaryEntry = Object.entries(modelsUsed).find(([key]) => key !== 'LR')
    const secondaryLabel = secondaryEntry ? secondaryEntry[0] : (overview?.model?.secondary_model_label || 'Secondary')
    const secondary = secondaryEntry && typeof secondaryEntry[1] === 'number' ? Number(secondaryEntry[1]).toFixed(3) : '-'
    const combined = Number(row?.confidence || 0).toFixed(3)
    return { lr, secondaryLabel, secondary, combined }
  }

  const derivedDatasetName =
    joinResult?.relationship
      ? `${joinResult.relationship.left_dataset}_${joinResult.relationship.right_dataset}_joined`
      : 'Not generated yet'

  return (
    <section className="df-tab-content">
      <div className="panel-story-grid">
        <article className="glass-card panel-section">
          <div className="section-kicker">Section 1</div>
          <h3>New Dataset Intake</h3>
          <p className="muted-text">
            Upload a new dataset and process it into the Data Fabric metadata and relationship pipeline.
          </p>

          <div
            className={`intake-dropzone ${dragActive ? 'active' : ''}`}
            onDragEnter={(e) => {
              e.preventDefault()
              setDragActive(true)
            }}
            onDragOver={(e) => {
              e.preventDefault()
              setDragActive(true)
            }}
            onDragLeave={(e) => {
              e.preventDefault()
              setDragActive(false)
            }}
            onDrop={handleDrop}
          >
            <p>Drag and drop datasets</p>
            <p className="muted-text">OR</p>
            <button type="button" className="df-btn" onClick={() => intakeFileInputRef.current?.click()}>
              Choose Files
            </button>
            <input
              ref={intakeFileInputRef}
              type="file"
              multiple
              className="hidden-file-input"
              onChange={(e) => handlePickedFiles(Array.from(e.target.files || []))}
            />
            {intakeFiles.length > 0 ? (
              <p className="muted-text">
                Selected files ({intakeFiles.length}): {intakeFiles.slice(0, 3).map((f) => f.name).join(', ')}
                {intakeFiles.length > 3 ? ` +${intakeFiles.length - 3} more` : ''}
              </p>
            ) : null}
          </div>

          <div className="join-form-row">
            <label>
              File Path (optional)
              <input
                type="text"
                value={intakeFilePath}
                onChange={(e) => setIntakeFilePath(e.target.value)}
                placeholder="C:\\path\\to\\new_dataset.csv"
              />
            </label>

            <label>
              Dataset Name
              <input
                type="text"
                value={intakeDatasetName}
                onChange={(e) => setIntakeDatasetName(e.target.value)}
                placeholder="new_dataset_name"
              />
            </label>
          </div>

          <button type="button" className="df-btn" onClick={() => void runIntake()} disabled={intakeBusy}>
            {intakeBusy ? 'Processing Intake...' : 'Process New File'}
          </button>

          <div className="intake-progress-box">
            <h4>Processing Progress</h4>
            {intakeSteps.length ? (
              <ul className="intake-step-list">
                {intakeSteps.map((step) => (
                  <li key={step.label} className={`step-${step.status}`}>
                    <span>{step.label}</span>
                    <strong>{step.status}</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-text">Progress steps appear when intake starts.</p>
            )}

            <button
              type="button"
              className="df-btn"
              onClick={downloadIntakeReport}
              disabled={!intakeReportReady}
            >
              Download Intake Report
            </button>
          </div>
        </article>

        <article className="glass-card panel-section">
          <div className="section-kicker">Section 2</div>
          <h3>Relationship Discovery Results</h3>

          <div className="confidence-legend">
            <span><i className="dot-strong" /> Strong {'>'} 0.90</span>
            <span><i className="dot-probable" /> Probable 0.60 - 0.90</span>
            <span><i className="dot-weak" /> Weak {'<'} 0.60</span>
          </div>

          {discoveryRows.length ? (
            <div className="df-table-wrap">
              <table className="df-table">
                <thead>
                  <tr>
                    <th>Left Column</th>
                    <th>Right Column</th>
                    <th>LR</th>
                    <th>{overview?.model?.secondary_model_label || 'Secondary'}</th>
                    <th>Combined</th>
                    <th>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {discoveryRows.map((row: any, index: number) => {
                    const band = confidenceBand(Number(row.confidence || 0))
                    const scores = modelScores(row)
                    return (
                      <tr key={`${row.relationship_key || 'row'}-${index}`}>
                        <td>{row.left_column || '-'}</td>
                        <td>{row.right_column || '-'}</td>
                        <td>{scores.lr}</td>
                        <td>{scores.secondary}</td>
                        <td>
                          <span className={`confidence-chip ${band}`}>{scores.combined}</span>
                        </td>
                        <td>
                          <span className={`df-decision ${decisionClass(String(row.decision || 'weak'))}`}>
                            {String(row.decision || 'weak')}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted-text">
              {!hasIntakeRun
                ? 'Process a new dataset first. Relationship candidates are hidden until intake runs.'
                : intakeResult
                ? 'No relationship candidates were found for the newly ingested dataset.'
                : 'Process a dataset to display discovered relationship candidates.'}
            </p>
          )}

          {intakeResult ? (
            <div className="intake-result-box">
              <ul className="meta-list compact">
                <li>
                  <span>Dataset</span>
                  <strong>{intakeResult.dataset_name || 'N/A'}</strong>
                </li>
                <li>
                  <span>Good Matches</span>
                  <strong>{formatNumber(intakeResult.good_match_count || 0)}</strong>
                </li>
                <li>
                  <span>Bad Matches</span>
                  <strong>{formatNumber(intakeResult.bad_match_count || 0)}</strong>
                </li>
              </ul>
            </div>
          ) : null}
        </article>
      </div>

      <article className="glass-card panel-section">
        <div className="section-kicker">Section 3</div>
        <h3>Autonomous Join Decision</h3>

        <div className="join-form-row">
          <label>
            Left Dataset
            <select value={leftDataset} onChange={(e) => setLeftDataset(e.target.value)}>
              <option value="">Select dataset</option>
              {overview.datasets.map((d: any) => (
                <option key={d.dataset_name} value={d.dataset_name}>
                  {d.dataset_name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Right Dataset
            <select value={rightDataset} onChange={(e) => setRightDataset(e.target.value)}>
              <option value="">Select dataset</option>
              {overview.datasets.map((d: any) => (
                <option key={d.dataset_name} value={d.dataset_name}>
                  {d.dataset_name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="join-mode-box">
          <span>Join Mode</span>
          <strong>{joinOptions?.mode || 'N/A'}</strong>
        </div>

        <p className="muted-text">{joinDecisionMessage}</p>

        <div className="decision-logic-grid">
          <div className="logic-card">
            <strong>IF one strong relationship</strong>
            <span>{'=>'} Auto Join</span>
          </div>
          <div className="logic-card">
            <strong>IF multiple strong relationships</strong>
            <span>{'=>'} Manual confirmation</span>
          </div>
          <div className="logic-card">
            <strong>IF weak relationships only</strong>
            <span>{'=>'} No auto join</span>
          </div>
        </div>

        <div className="suggestion-list">
          <h4>Suggested Relationships</h4>
          {!hasIntakeRun ? (
            <p className="muted-text">Suggestions will appear after running new dataset intake.</p>
          ) : joinOptions?.suggestions?.length ? (
            joinOptions.suggestions.map((s: any) => (
              <label key={s.relationship_key} className="suggestion-item">
                <input
                  type="radio"
                  name="relationship_suggestion"
                  checked={selectedRelationshipKey === s.relationship_key}
                  onChange={() => setSelectedRelationshipKey(s.relationship_key)}
                />
                <span>
                  {s.left_column} {'->'} {s.right_column} | {s.confidence.toFixed(3)} | {s.decision}
                </span>
              </label>
            ))
          ) : (
            <p className="muted-text">No relationship suggestions available for this pair.</p>
          )}
        </div>
      </article>

      <article className="glass-card panel-section">
        <div className="section-kicker">Section 4</div>
        <h3>Join Execution + Result</h3>

        <button type="button" className="df-btn" onClick={() => void runJoin()} disabled={joinBusy}>
          {joinBusy ? 'Executing Join...' : 'Execute Join'}
        </button>

        {joinResult?.manual_intervention_required ? (
          <p className="warning-text">{joinResult.reason || 'Manual intervention required for this join.'}</p>
        ) : null}

        {joinResult?.success ? (
          <div className="join-result-grid">
            <div>
              <h4>Join Completed</h4>
              <ul className="meta-list compact">
                <li>
                  <span>Derived Dataset</span>
                  <strong>{derivedDatasetName}</strong>
                </li>
                <li>
                  <span>Rows</span>
                  <strong>{formatNumber(joinResult.row_count || 0)}</strong>
                </li>
                <li>
                  <span>Columns</span>
                  <strong>{formatNumber((joinResult.columns || []).length)}</strong>
                </li>
                <li>
                  <span>Join Key</span>
                  <strong>
                    {joinResult.relationship?.left_column} {'->'} {joinResult.relationship?.right_column}
                  </strong>
                </li>
                <li>
                  <span>Confidence</span>
                  <strong>{Number(joinResult.relationship?.confidence || 0).toFixed(3)}</strong>
                </li>
              </ul>
            </div>

            <div className="mini-lineage-card">
              <h4>Lineage Updated</h4>
              <pre className="lineage-mini">
{`${joinResult.relationship?.left_dataset || leftDataset}
    |
    |-- join(${joinResult.relationship?.left_column || 'key'})
    |
${joinResult.relationship?.right_dataset || rightDataset}
    |
    v
${derivedDatasetName}`}
              </pre>
            </div>
          </div>
        ) : (
          <p className="muted-text">Run join execution to show derived dataset, confidence, and lineage update.</p>
        )}

        {joinResult?.success && joinResult.preview?.length ? (
          <div className="df-table-wrap">
            <table className="df-table">
              <thead>
                <tr>
                  {(joinResult.columns || []).map((col: string) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(joinResult.preview || []).map((row: any, idx: number) => (
                  <tr key={`preview-${idx}`}>
                    {(joinResult.columns || []).map((col: string) => (
                      <td key={`${idx}-${col}`}>{String(row[col] ?? '')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </article>
    </section>
  )
}
