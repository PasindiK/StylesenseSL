import React from 'react'
import type { BaselineDetectionResult } from '../types'
import '../styles/BaselineDetectionCard.css'

interface BaselineDetectionCardProps {
  detection: BaselineDetectionResult
  onConfirm: (baseline: string) => void
  onSelectAlternative?: (baseline: string) => void
}

export const BaselineDetectionCard: React.FC<BaselineDetectionCardProps> = ({
  detection,
  onConfirm,
  onSelectAlternative,
}) => {
  const { confidence, recommendation, detected_baseline, alternatives, matched_columns, analysis } = detection

  // HIGH confidence - auto-select card
  if (confidence >= 0.9) {
    return (
      <div className="detection-card detection-card--high-confidence">
        <div className="detection-header">
          <span className="confidence-badge confidence-badge--high">✅ HIGH</span>
          <h3>Baseline Auto-Detected</h3>
        </div>

        <div className="baseline-result">
          <div className="baseline-icon">📦</div>
          <div className="baseline-info">
            <h4>{detected_baseline.toUpperCase()}</h4>
            <p className="confidence">Confidence: {Math.round(confidence * 100)}%</p>
          </div>
        </div>

        {matched_columns.length > 0 && (
          <div className="matched-columns">
            <h5>Matched Columns ({matched_columns.length}):</h5>
            <div className="column-list">
              {matched_columns.slice(0, 5).map((col) => (
                <span key={col} className="column-badge">
                  {col}
                </span>
              ))}
              {matched_columns.length > 5 && (
                <span className="column-badge column-badge--more">+{matched_columns.length - 5} more</span>
              )}
            </div>
          </div>
        )}

        <p className="reasoning">{detection.reasoning}</p>

        <div className="action-buttons">
          <button className="btn btn--primary" onClick={() => onConfirm(detected_baseline)}>
            Continue with Auto-Selected Baseline
          </button>
          {alternatives.length > 0 && onSelectAlternative && (
            <button
              className="btn btn--secondary"
              onClick={() => {
                /* Show alternatives panel */
              }}
            >
              Choose Different
            </button>
          )}
        </div>
      </div>
    )
  }

  // MEDIUM confidence - confirm card
  if (confidence >= 0.7) {
    return (
      <div className="detection-card detection-card--medium-confidence">
        <div className="detection-header">
          <span className="confidence-badge confidence-badge--medium">⚠️ CONFIRM</span>
          <h3>Baseline Detected - Please Confirm</h3>
        </div>

        <div className="baseline-result">
          <div className="baseline-icon">📦</div>
          <h4>{detected_baseline.toUpperCase()}</h4>
          <p className="confidence">Confidence: {Math.round(confidence * 100)}%</p>
        </div>

        {(analysis.primary_key_found || matched_columns.length > 0 || analysis.row_count_plausible) && (
          <div className="analysis">
            <h5>Detection Analysis:</h5>
            <ul>
              {analysis.primary_key_found && <li>✓ Primary key detected</li>}
              {analysis.characteristic_columns_matched > 0 && (
                <li>✓ {analysis.characteristic_columns_matched} characteristic columns matched</li>
              )}
              {analysis.row_count_plausible && <li>✓ Row count plausible</li>}
            </ul>
          </div>
        )}

        {alternatives.length > 0 && (
          <div className="alternatives">
            <h5>Other Possible Matches:</h5>
            <div className="alternatives-list">
              {alternatives.map((alt) => (
                <button
                  key={alt.baseline}
                  className="alt-button"
                  onClick={() => onSelectAlternative?.(alt.baseline)}
                >
                  {alt.baseline} ({Math.round(alt.confidence * 100)}%)
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="action-buttons">
          <button className="btn btn--primary" onClick={() => onConfirm(detected_baseline)}>
            Confirm Selection
          </button>
          {alternatives.length > 0 && (
            <button
              className="btn btn--secondary"
              onClick={() => {
                /* Show alternatives panel */
              }}
            >
              Select Different
            </button>
          )}
        </div>
      </div>
    )
  }

  // LOW confidence - manual selection card
  return (
    <div className="detection-card detection-card--low-confidence">
      <div className="detection-header">
        <span className="confidence-badge confidence-badge--low">❓ INCONCLUSIVE</span>
        <h3>Unable to Auto-Detect - Please Select Baseline</h3>
      </div>

      <p className="explanation">
        The uploaded file doesn't match known baseline patterns clearly. Please manually select which baseline this
        data belongs to.
      </p>

      {alternatives.length > 0 && (
        <div className="alternatives">
          <h5>Detection Results (sorted by confidence):</h5>
          <div className="baseline-options">
            <div className="option" onClick={() => onConfirm(detected_baseline)}>
              <input type="radio" name="baseline" value={detected_baseline} defaultChecked />
              <label>{detected_baseline} - {Math.round(confidence * 100)}%</label>
            </div>
            {alternatives.map((alt) => (
              <div key={alt.baseline} className="option" onClick={() => onSelectAlternative?.(alt.baseline)}>
                <input type="radio" name="baseline" value={alt.baseline} />
                <label>{alt.baseline} - {Math.round(alt.confidence * 100)}%</label>
              </div>
            ))}
          </div>
        </div>
      )}

      <details className="details">
        <summary>View Detection Analysis</summary>
        <pre>{JSON.stringify(detection.analysis, null, 2)}</pre>
      </details>

      <div className="action-buttons">
        <button className="btn btn--primary" onClick={() => onConfirm(detected_baseline)}>
          Use Primary Detection
        </button>
      </div>
    </div>
  )
}
