type Props = {
  loading: boolean
  lineage: any
  graphLayout: any
}

export default function LineageGraphPage({ loading, lineage, graphLayout }: Props) {
  if (!lineage) {
    return (
      <section className="df-tab-content">
        <article className="glass-card df-state-card">
          <h3>{loading ? 'Loading Lineage Graph...' : 'No Lineage Data Loaded Yet'}</h3>
          <p className="muted-text">
            {loading
              ? 'Fetching node and edge topology from backend...'
              : 'Use "Refresh Live Data" to load the latest lineage graph.'}
          </p>
        </article>
      </section>
    )
  }

  return (
    <section className="df-tab-content">
      <article className="glass-card">
        <h3>Lineage Graph</h3>
        <div className="lineage-canvas">
          <svg viewBox={`0 0 ${graphLayout.width} ${graphLayout.height}`} role="img" aria-label="Lineage Graph">
            <defs>
              <marker id="df-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
                <path d="M0,0 L10,4 L0,8 z" className="arrow-marker" />
              </marker>
            </defs>

            {graphLayout.edges.map((edge: any, index: number) => (
              <line
                key={`edge-${index}`}
                x1={edge.source.x}
                y1={edge.source.y}
                x2={edge.target.x}
                y2={edge.target.y}
                className="lineage-edge"
                markerEnd="url(#df-arrow)"
              />
            ))}

            {graphLayout.nodes.map((node: any) => (
              <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
                <circle r="36" className="lineage-node" />
                <text textAnchor="middle" dy="4" className="lineage-label">
                  {node.label.slice(0, 14)}
                </text>
              </g>
            ))}
          </svg>
        </div>
      </article>
    </section>
  )
}
