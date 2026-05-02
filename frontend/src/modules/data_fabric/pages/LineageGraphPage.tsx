import { useEffect, useMemo, useState } from 'react'

type LineageNode = { id: string; label: string; domain: string; quality_score: number }
type LineageEdge = { source: string; target: string }
type MergeConfidenceCandidate = {
  left_dataset: string
  right_dataset: string
  best_confidence: number
  best_decision: string
  relationship_key: string
}
type PositionedNode = LineageNode & { x: number; y: number }
type MergeCandidate = {
  leftId: string
  rightId: string
  distance: number
  proximity: number
  confidence: number
  decision: string
  key: string
}

type Props = {
  loading: boolean
  lineage: {
    nodes: LineageNode[]
    edges: LineageEdge[]
    merge_candidates?: MergeConfidenceCandidate[]
  } | null
  graphLayout?: any
}

const BASE_WIDTH = 1100
const BASE_HEIGHT = 620
const NODE_RADIUS = 34
const DOMAIN_COLORS = ['#2D9CDB', '#27AE60', '#F2994A', '#EB5757', '#56CCF2', '#6FCF97', '#F2C94C', '#BB6BD9']

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function hashText(text: string): number {
  let hash = 0
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0
  }
  return hash
}

function domainColor(domain: string): string {
  const idx = hashText((domain || 'unknown').toLowerCase()) % DOMAIN_COLORS.length
  return DOMAIN_COLORS[idx]
}

function buildNodeLabelLines(label: string): string[] {
  const clean = String(label || '').trim()
  if (!clean) return ['dataset']

  const maxCharsPerLine = 18
  const maxLines = 2
  const words = clean.split(/[_\s-]+/).filter(Boolean)
  const lines: string[] = []
  let current = ''

  words.forEach((word) => {
    const candidate = current ? `${current} ${word}` : word
    if (candidate.length <= maxCharsPerLine) {
      current = candidate
      return
    }

    if (current) {
      lines.push(current)
      current = word
    } else {
      lines.push(word.slice(0, maxCharsPerLine))
      current = word.slice(maxCharsPerLine)
    }
  })

  if (current) lines.push(current)

  const normalized = lines.slice(0, maxLines)
  if (lines.length > maxLines) {
    normalized[maxLines - 1] = `${normalized[maxLines - 1].slice(0, Math.max(1, maxCharsPerLine - 1))}…`
  }
  return normalized
}

function joinedNodeSortKey(nodeId: string): number {
  const text = String(nodeId || '').trim()
  if (!text) return -1
  const ts = text.match(/(\d{14})$/)
  if (ts) {
    return Number(ts[1])
  }
  // Fallback: keep joined nodes ordered deterministically even without timestamp suffix.
  return hashText(text)
}

function computeForceLayout(
  nodes: LineageNode[],
  edges: LineageEdge[],
  mergeCandidates: MergeConfidenceCandidate[]
): Record<string, { x: number; y: number }> {
  const count = Math.max(1, nodes.length)
  const radius = Math.min(BASE_WIDTH, BASE_HEIGHT) * 0.34
  const cx = BASE_WIDTH / 2
  const cy = BASE_HEIGHT / 2

  const positions: Record<string, { x: number; y: number }> = {}
  const velocities: Record<string, { x: number; y: number }> = {}

  nodes.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / count
    positions[node.id] = {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    }
    velocities[node.id] = { x: 0, y: 0 }
  })

  const strongMergeSprings = mergeCandidates
    .filter((candidate) => Number(candidate.best_confidence || 0) >= 0.5)
    .map((candidate) => ({
      source: candidate.left_dataset,
      target: candidate.right_dataset,
      confidence: clamp(Number(candidate.best_confidence || 0), 0, 1),
    }))
    .filter((edge) => positions[edge.source] && positions[edge.target])

  const lineageSprings = edges
    .map((edge) => ({ source: edge.source, target: edge.target }))
    .filter((edge) => positions[edge.source] && positions[edge.target])

  const idealDistance = 210
  const repelStrength = 76000
  const springStrength = 0.0075
  const centerStrength = 0.003
  const damping = 0.86

  for (let step = 0; step < 170; step += 1) {
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i]
      const pa = positions[a.id]
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j]
        const pb = positions[b.id]
        const dx = pa.x - pb.x
        const dy = pa.y - pb.y
        const distSq = Math.max(dx * dx + dy * dy, 1)
        const dist = Math.sqrt(distSq)
        const force = repelStrength / distSq
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        velocities[a.id].x += fx
        velocities[a.id].y += fy
        velocities[b.id].x -= fx
        velocities[b.id].y -= fy
      }
    }

    lineageSprings.forEach((edge) => {
      const ps = positions[edge.source]
      const pt = positions[edge.target]
      const dx = pt.x - ps.x
      const dy = pt.y - ps.y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const delta = dist - idealDistance
      const force = springStrength * delta
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      velocities[edge.source].x += fx
      velocities[edge.source].y += fy
      velocities[edge.target].x -= fx
      velocities[edge.target].y -= fy
    })

    strongMergeSprings.forEach((edge) => {
      const ps = positions[edge.source]
      const pt = positions[edge.target]
      const dx = pt.x - ps.x
      const dy = pt.y - ps.y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      // Higher confidence should appear visually closer.
      const desired = 130 + (1 - edge.confidence) * 150
      const delta = dist - desired
      const force = springStrength * 1.15 * delta
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      velocities[edge.source].x += fx
      velocities[edge.source].y += fy
      velocities[edge.target].x -= fx
      velocities[edge.target].y -= fy
    })

    nodes.forEach((node) => {
      const pos = positions[node.id]
      const vel = velocities[node.id]
      vel.x += (cx - pos.x) * centerStrength
      vel.y += (cy - pos.y) * centerStrength
      vel.x *= damping
      vel.y *= damping
      pos.x = clamp(pos.x + vel.x, NODE_RADIUS + 20, BASE_WIDTH - NODE_RADIUS - 20)
      pos.y = clamp(pos.y + vel.y, NODE_RADIUS + 20, BASE_HEIGHT - NODE_RADIUS - 20)
    })
  }

  return positions
}

export default function LineageGraphPage({ loading, lineage }: Props) {
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null)
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({})
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [hoveredCandidateKey, setHoveredCandidateKey] = useState<string | null>(null)
  const [showAllLabels, setShowAllLabels] = useState(true)
  const [showMergeLines, setShowMergeLines] = useState(false)
  const [panning, setPanning] = useState(false)
  const [lastPointer, setLastPointer] = useState<{ x: number; y: number } | null>(null)

  const nodes = lineage?.nodes || []
  const rawEdges = lineage?.edges || []
  const edges = useMemo(() => {
    const seen = new Set<string>()
    return rawEdges.filter((edge) => {
      if (!edge.source || !edge.target || edge.source === edge.target) return false
      const key = `${edge.source}->${edge.target}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [rawEdges])
  const mergeConfidenceCandidates = lineage?.merge_candidates || []

  const latestJoinedNodeId = useMemo(() => {
    const candidates = nodes.filter((node) => {
      const id = String(node.id || '').toLowerCase()
      return id.startsWith('virtual_') || id.includes('_joined')
    })
    if (!candidates.length) return null
    return candidates
      .slice()
      .sort((a, b) => joinedNodeSortKey(b.id) - joinedNodeSortKey(a.id))[0].id
  }, [nodes])

  useEffect(() => {
    setPositions(computeForceLayout(nodes, edges, mergeConfidenceCandidates))
    setZoom(1)
    setPan({ x: 0, y: 0 })
    setDraggingNodeId(null)
    setHoveredNodeId(null)
    setHoveredCandidateKey(null)
    // Dense graphs become unreadable with all labels and candidate links visible.
    setShowAllLabels(nodes.length <= 12)
    setShowMergeLines(nodes.length <= 10)
  }, [lineage])

  const positionedNodes: PositionedNode[] = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        x: positions[node.id]?.x ?? BASE_WIDTH / 2,
        y: positions[node.id]?.y ?? BASE_HEIGHT / 2,
      })),
    [nodes, positions]
  )

  const nodeMap = useMemo(
    () => new Map(positionedNodes.map((node) => [node.id, node])),
    [positionedNodes]
  )

  const positionedEdges = useMemo(
    () =>
      edges.flatMap((edge) => {
        const source = nodeMap.get(edge.source)
        const target = nodeMap.get(edge.target)
        if (!source || !target) return []
        return [{ source, target }]
      }),
    [edges, nodeMap]
  )

  const maxY = useMemo(() => {
    if (!positionedNodes.length) return 1
    return Math.max(...positionedNodes.map((n) => n.y), 1)
  }, [positionedNodes])

  const mergeCandidates: MergeCandidate[] = useMemo(() => {
    const results: MergeCandidate[] = []
    const byId = new Map(positionedNodes.map((n) => [n.id, n]))
    mergeConfidenceCandidates.forEach((candidate) => {
      const leftId = candidate.left_dataset
      const rightId = candidate.right_dataset
      const a = byId.get(leftId)
      const b = byId.get(rightId)
      if (!a || !b) return

      const confidence = clamp(Number(candidate.best_confidence || 0), 0, 1)
      const proximity = confidence
      const distance = 1 - confidence
      const key = `${leftId}::${rightId}`
      results.push({
        leftId,
        rightId,
        key,
        distance,
        proximity,
        confidence,
        decision: candidate.best_decision,
      })
    })

    return results.sort((a, b) => b.confidence - a.confidence).slice(0, 8)
  }, [positionedNodes, mergeConfidenceCandidates])

  function nodeDepth(node: PositionedNode): number {
    return clamp(0.55 + 0.45 * (node.y / maxY), 0.55, 1)
  }

  function wheelZoom(deltaY: number) {
    const next = clamp(zoom - deltaY * 0.0012, 0.55, 2.3)
    setZoom(next)
  }

  function onBackgroundPointerDown(clientX: number, clientY: number) {
    setPanning(true)
    setLastPointer({ x: clientX, y: clientY })
  }

  function onPointerMove(clientX: number, clientY: number) {
    if (draggingNodeId) {
      const viewX = (clientX - pan.x) / zoom
      const viewY = (clientY - pan.y) / zoom
      setPositions((prev) => ({
        ...prev,
        [draggingNodeId]: {
          x: clamp(viewX, 60, BASE_WIDTH - 60),
          y: clamp(viewY, 60, BASE_HEIGHT - 60),
        },
      }))
      return
    }

    if (panning && lastPointer) {
      const dx = clientX - lastPointer.x
      const dy = clientY - lastPointer.y
      setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }))
      setLastPointer({ x: clientX, y: clientY })
    }
  }

  function onPointerUp() {
    setDraggingNodeId(null)
    setPanning(false)
    setLastPointer(null)
  }

  const connectedToHovered = new Set<string>()
  if (hoveredNodeId) {
    positionedEdges.forEach((edge) => {
      if (edge.source.id === hoveredNodeId || edge.target.id === hoveredNodeId) {
        connectedToHovered.add(edge.source.id)
        connectedToHovered.add(edge.target.id)
      }
    })
  }

  const candidateNodesHighlighted = new Set<string>()
  if (hoveredCandidateKey) {
    const hit = mergeCandidates.find((candidate) => candidate.key === hoveredCandidateKey)
    if (hit) {
      candidateNodesHighlighted.add(hit.leftId)
      candidateNodesHighlighted.add(hit.rightId)
    }
  }

  const connectedToLatestJoined = new Set<string>()
  if (latestJoinedNodeId) {
    connectedToLatestJoined.add(latestJoinedNodeId)
    positionedEdges.forEach((edge) => {
      if (edge.source.id === latestJoinedNodeId || edge.target.id === latestJoinedNodeId) {
        connectedToLatestJoined.add(edge.source.id)
        connectedToLatestJoined.add(edge.target.id)
      }
    })
  }

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
        <div className="lineage-toolbar">
          <h3>Lineage Graph</h3>
          <div className="lineage-controls">
            <button type="button" className="df-btn" onClick={() => setZoom((z) => clamp(z + 0.12, 0.55, 2.3))}>Zoom +</button>
            <button type="button" className="df-btn" onClick={() => setZoom((z) => clamp(z - 0.12, 0.55, 2.3))}>Zoom -</button>
            <button type="button" className="df-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}>Reset View</button>
            <button
              type="button"
              className={`df-btn secondary ${showAllLabels ? 'active' : ''}`}
              onClick={() => setShowAllLabels((v) => !v)}
            >
              {showAllLabels ? 'Labels: On' : 'Labels: Smart'}
            </button>
            <button
              type="button"
              className={`df-btn secondary ${showMergeLines ? 'active' : ''}`}
              onClick={() => setShowMergeLines((v) => !v)}
            >
              {showMergeLines ? 'Merge Links: On' : 'Merge Links: Off'}
            </button>
          </div>
        </div>
        <p className="muted-text lineage-help">Drag nodes to re-layout, drag empty canvas to pan, use mouse wheel to zoom.</p>

        <div
          className="lineage-canvas lineage-canvas-3d"
          onWheel={(e) => {
            e.preventDefault()
            wheelZoom(e.deltaY)
          }}
          onMouseMove={(e) => onPointerMove(e.nativeEvent.offsetX, e.nativeEvent.offsetY)}
          onMouseUp={onPointerUp}
          onMouseLeave={onPointerUp}
        >
          <svg
            viewBox={`0 0 ${BASE_WIDTH} ${BASE_HEIGHT}`}
            role="img"
            aria-label="Lineage Graph"
            onMouseDown={(e) => onBackgroundPointerDown(e.nativeEvent.offsetX, e.nativeEvent.offsetY)}
          >
            <defs>
              <marker id="df-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
                <path d="M0,0 L10,4 L0,8 z" className="arrow-marker" />
              </marker>
              <radialGradient id="lineageNodeGrad" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stopColor="rgba(210, 247, 255, 0.95)" />
                <stop offset="45%" stopColor="rgba(103, 179, 232, 0.9)" />
                <stop offset="100%" stopColor="rgba(28, 67, 118, 0.95)" />
              </radialGradient>
              <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feDropShadow dx="0" dy="5" stdDeviation="7" floodColor="rgba(60, 176, 255, 0.42)" />
              </filter>
            </defs>

            <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
              {showMergeLines
                ? mergeCandidates.map((candidate) => {
                const left = nodeMap.get(candidate.leftId)
                const right = nodeMap.get(candidate.rightId)
                if (!left || !right) return null
                const isActive = hoveredCandidateKey === candidate.key
                const midX = (left.x + right.x) / 2
                const midY = (left.y + right.y) / 2
                return (
                  <g
                    key={candidate.key}
                    onMouseEnter={() => setHoveredCandidateKey(candidate.key)}
                    onMouseLeave={() => setHoveredCandidateKey(null)}
                  >
                    <line
                      x1={left.x}
                      y1={left.y}
                      x2={right.x}
                      y2={right.y}
                      className={`merge-candidate-line ${isActive ? 'active' : ''}`}
                    />
                    <text x={midX} y={midY - 6} textAnchor="middle" className="merge-distance-label">
                      {candidate.distance.toFixed(0)}
                    </text>
                  </g>
                )
                })
                : null}

              {positionedEdges.map((edge, index) => {
                const emphasized = hoveredNodeId
                  ? edge.source.id === hoveredNodeId || edge.target.id === hoveredNodeId
                  : false
                const highlightedJoinEdge = Boolean(
                  latestJoinedNodeId &&
                    (edge.source.id === latestJoinedNodeId || edge.target.id === latestJoinedNodeId)
                )
                const depth = (nodeDepth(edge.source) + nodeDepth(edge.target)) / 2
                return (
                  <line
                    key={`edge-${index}`}
                    x1={edge.source.x}
                    y1={edge.source.y}
                    x2={edge.target.x}
                    y2={edge.target.y}
                    className={`lineage-edge ${emphasized ? 'active' : ''} ${highlightedJoinEdge ? 'recent' : ''}`}
                    style={{ opacity: emphasized || highlightedJoinEdge ? 0.96 : 0.35 + depth * 0.38 }}
                    markerEnd="url(#df-arrow)"
                  />
                )
              })}

              {[...positionedNodes]
                .sort((a, b) => a.y - b.y)
                .map((node) => {
                  const depth = nodeDepth(node)
                  const isHovered = node.id === hoveredNodeId
                  const isLatestJoined = Boolean(latestJoinedNodeId && node.id === latestJoinedNodeId)
                  const fadeHoverLayer = hoveredNodeId && !connectedToHovered.has(node.id)
                  const fadeCandidateLayer = hoveredCandidateKey && !candidateNodesHighlighted.has(node.id)
                  const fadeOther = Boolean(fadeHoverLayer || fadeCandidateLayer)
                  const r = 28 + Math.round(depth * 8)
                  const fillColor = domainColor(node.domain)
                  const labelLines = buildNodeLabelLines(node.label)
                  const labelWidth = Math.min(170, Math.max(96, Math.round(node.label.length * 6.1)))
                  const labelHeight = labelLines.length > 1 ? 34 : 22
                  const labelY = r + 11
                  const shouldShowLabel =
                    showAllLabels || isHovered || connectedToHovered.has(node.id) || candidateNodesHighlighted.has(node.id)

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      className="lineage-node-group"
                      style={{ opacity: fadeOther ? 0.33 : 1 }}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                      onMouseDown={(e) => {
                        e.stopPropagation()
                        setDraggingNodeId(node.id)
                      }}
                    >
                      <ellipse
                        cx={0}
                        cy={r + 15}
                        rx={Math.round(r * 0.95)}
                        ry={Math.round(r * 0.28)}
                        className="lineage-shadow"
                      />
                      <circle
                        r={r}
                        className={`lineage-node ${isHovered ? 'active' : ''} ${isLatestJoined ? 'latest-joined' : ''}`}
                        fill={fillColor}
                        filter="url(#nodeGlow)"
                      />
                      {isLatestJoined ? (
                        <circle r={r + 5} className="lineage-node-new-ring" />
                      ) : null}
                      <circle r={Math.round(r * 0.66)} className="lineage-node-inner" />
                      <title>{node.label}</title>
                      {isLatestJoined ? (
                        <text textAnchor="middle" y={-r - 10} className="lineage-new-badge">NEW JOIN</text>
                      ) : null}
                      {shouldShowLabel ? (
                        <>
                          <rect
                            x={-labelWidth / 2}
                            y={labelY}
                            width={labelWidth}
                            height={labelHeight}
                            rx={10}
                            className="lineage-label-bg"
                          />
                          {labelLines.map((line, lineIndex) => (
                            <text
                              key={`${node.id}-line-${lineIndex}`}
                              textAnchor="middle"
                              y={labelY + 14 + lineIndex * 13}
                              className={`lineage-label ${lineIndex > 0 ? 'lineage-label-sub' : ''}`}
                            >
                              {line}
                            </text>
                          ))}
                        </>
                      ) : null}
                    </g>
                  )
                })}
            </g>
          </svg>
        </div>

        <div className="lineage-legend">
          <span className="muted-text">Nodes: {nodes.length}</span>
          <span className="muted-text">Edges: {edges.length}{rawEdges.length > edges.length ? ` (${rawEdges.length - edges.length} duplicates hidden)` : ''}</span>
          <span className="muted-text">Active zoom: {zoom.toFixed(2)}x</span>
          {latestJoinedNodeId ? <span className="muted-text">Highlighted latest join: {latestJoinedNodeId}</span> : null}
        </div>

        <div className="closest-merge-panel">
          <h4>Closest Merge Candidates (Confidence-Based Distance)</h4>
          {mergeCandidates.length === 0 ? (
            <p className="muted-text">No unlinked dataset pairs available.</p>
          ) : (
            <ul className="closest-merge-list">
              {mergeCandidates.map((candidate, index) => (
                <li
                  key={candidate.key}
                  className={hoveredCandidateKey === candidate.key ? 'active' : ''}
                  onMouseEnter={() => setHoveredCandidateKey(candidate.key)}
                  onMouseLeave={() => setHoveredCandidateKey(null)}
                >
                  <span>{index + 1}. {candidate.leftId} ↔ {candidate.rightId}</span>
                  <strong>confidence {candidate.confidence.toFixed(3)} | distance {(1 - candidate.confidence).toFixed(3)} | {candidate.decision}</strong>
                </li>
              ))}
            </ul>
          )}
        </div>
      </article>
    </section>
  )
}
