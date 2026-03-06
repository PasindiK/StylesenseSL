import React from 'react'

const steps = [
  "Generate dataset CSV: python -m src.services.agentic_ai.scripts.generate_intent_dataset_csv --rows 8400",
  "Review CSV at src/services/agentic_ai/data/intent/intent_dataset_8400.csv (columns: text,label)",
  "Train DistilBERT: python -m src.services.agentic_ai.scripts.train_intent_distilbert --data <csv_path>",
  "Trainer learns temperature calibration and confidence threshold from validation set",
  "Model + config saved in src/services/agentic_ai/agents/models/intent_distilbert",
  "Restart backend to activate model-first intent with LLM fallback",
]

const colabNotebooks = [
  {
    title: 'Colab 1 - Training Visualization',
    path: 'src/services/agentic_ai/colab/intent_training_visualization_colab.ipynb',
    purpose: 'Shows training/eval loss and accuracy curves with saved model metadata.',
  },
  {
    title: 'Colab 2 - Evaluation Metrics',
    path: 'src/services/agentic_ai/colab/intent_evaluation_metrics_colab.ipynb',
    purpose: 'Generates summary metrics, per-intent F1 chart, and confusion matrix heatmap.',
  },
]

const labels = [
  'greeting',
  'farewell',
  'small_talk',
  'product_search',
  'styling_advice',
  'feedback_positive',
  'feedback_negative',
  'clarification',
  'add_to_cart',
  'view_cart',
  'clear_cart',
  'order_request',
]

export default function IntentModelTrainingPanel() {
  return (
    <article
      style={{
        borderRadius: 12,
        padding: 12,
        background: 'rgba(15,23,42,0.55)',
        border: '1px solid rgba(148,163,184,0.25)',
        color: '#e2e8f0',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Intent Model Training</div>
      <div style={{ fontSize: 12, color: '#cbd5e1', marginBottom: 10 }}>
        Your system can run with rules/LLM, but you can now train a local intent model for faster and cheaper routing.
      </div>

      <div style={{ display: 'grid', gap: 6, marginBottom: 10 }}>
        {steps.map((step, idx) => (
          <div key={step} style={{ fontSize: 12, background: 'rgba(2,6,23,0.33)', borderRadius: 8, padding: '7px 8px' }}>
            {idx + 1}. {step}
          </div>
        ))}
      </div>

      <div style={{ fontSize: 12, color: '#93c5fd', marginBottom: 6 }}>Colab Proof Notebooks</div>
      <div style={{ display: 'grid', gap: 6, marginBottom: 10 }}>
        {colabNotebooks.map((notebook) => (
          <div key={notebook.path} style={{ fontSize: 12, background: 'rgba(2,6,23,0.33)', borderRadius: 8, padding: '7px 8px' }}>
            <div style={{ fontWeight: 600 }}>{notebook.title}</div>
            <div style={{ color: '#cbd5e1' }}>{notebook.purpose}</div>
            <div style={{ color: '#93c5fd', marginTop: 2 }}>{notebook.path}</div>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 12, color: '#93c5fd', marginBottom: 6 }}>Recommended labels</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {labels.map((label) => (
          <span
            key={label}
            style={{
              padding: '3px 8px',
              borderRadius: 999,
              border: '1px solid rgba(96,165,250,0.4)',
              background: 'rgba(59,130,246,0.18)',
              fontSize: 11,
            }}
          >
            {label}
          </span>
        ))}
      </div>
    </article>
  )
}
