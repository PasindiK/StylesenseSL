import React from 'react'

export type KGComponentItem = {
  name: string
  role: string
  input: string
  output: string
}

const DEFAULT_COMPONENTS: KGComponentItem[] = [
  {
    name: 'Ingestion Layer',
    role: 'Loads users, products, preferences, and interactions into graph entities.',
    input: 'CSV/raw events',
    output: 'User/Product/Shop/Tag nodes + links',
  },
  {
    name: 'Graph Store (Neo4j)',
    role: 'Stores relationships for explainable recommendation traversal.',
    input: 'Nodes + relationships',
    output: 'Connected knowledge graph',
  },
  {
    name: 'Event Writer',
    role: 'Writes live search, recommendation impression, and preference events.',
    input: 'User actions from chat/UI',
    output: 'Updated graph edge weights',
  },
  {
    name: 'Graph Scoring',
    role: 'Computes graph relevance signal per candidate product.',
    input: 'user_id + candidate products',
    output: 'graph_score + graph_reasons',
  },
  {
    name: 'Personalization Reranker',
    role: 'Blends intent/profile/price/popularity with graph score.',
    input: 'Catalog candidates + KG score',
    output: 'Final ranked recommendations',
  },
]

export default function KGPipelinePanel({
  title = 'Knowledge Graph Pipeline',
  components = DEFAULT_COMPONENTS,
}: {
  title?: string
  components?: KGComponentItem[]
}) {
  return (
    <section
      style={{
        borderRadius: 16,
        padding: 20,
        background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 55%, #0b3b57 100%)',
        color: '#e2e8f0',
        border: '1px solid rgba(148,163,184,0.25)',
        boxShadow: '0 10px 30px rgba(2, 6, 23, 0.35)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{title}</h3>
          <p style={{ margin: '4px 0 0 0', fontSize: 12, color: '#cbd5e1' }}>
            End-to-end flow from ingestion to explainable recommendations.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <span
            style={{
              fontSize: 12,
              padding: '4px 10px',
              borderRadius: 999,
              background: 'rgba(16, 185, 129, 0.15)',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              color: '#bbf7d0',
            }}
          >
            KG Ready
          </span>
          <span
            style={{
              fontSize: 12,
              padding: '4px 10px',
              borderRadius: 999,
              background: 'rgba(59, 130, 246, 0.15)',
              border: '1px solid rgba(59, 130, 246, 0.35)',
              color: '#bfdbfe',
            }}
          >
            Production-Oriented
          </span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
        {components.map((item, idx) => (
          <article
            key={item.name}
            style={{
              borderRadius: 12,
              padding: 12,
              background: 'rgba(15, 23, 42, 0.55)',
              border: '1px solid rgba(148,163,184,0.25)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontWeight: 700, marginBottom: 6, color: '#f8fafc' }}>{item.name}</div>
              <span style={{ fontSize: 11, color: '#93c5fd', border: '1px solid rgba(147,197,253,.35)', borderRadius: 999, padding: '2px 8px' }}>
                Stage {idx + 1}
              </span>
            </div>
            <div style={{ fontSize: 13, marginBottom: 8, color: '#cbd5e1' }}>{item.role}</div>
            <div style={{ fontSize: 12, color: '#93c5fd' }}><strong>In:</strong> {item.input}</div>
            <div style={{ fontSize: 12, color: '#86efac' }}><strong>Out:</strong> {item.output}</div>
          </article>
        ))}
      </div>
    </section>
  )
}
