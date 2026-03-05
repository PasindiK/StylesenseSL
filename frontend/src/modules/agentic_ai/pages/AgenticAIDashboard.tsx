import React, { useEffect, useMemo, useState } from 'react'
import type { KGPreferenceSignal } from '../services/kgSignals'

type DashboardSection =
  | 'chat'
  | 'system_overview'
  | 'knowledge_graph'
  | 'agent_engine'

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function formatNumber(value: number) {
  return value.toLocaleString('en-US')
}

function MiniLineChart({
  values,
  stroke = '#38bdf8',
  fill = 'rgba(56,189,248,0.18)',
  height = 100,
}: {
  values: number[]
  stroke?: string
  fill?: string
  height?: number
}) {
  const width = 420
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const span = Math.max(1, max - min)
  const points = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * width
      const y = height - ((v - min) / span) * (height - 12) - 6
      return `${x},${y}`
    })
    .join(' ')
  const areaPoints = `0,${height} ${points} ${width},${height}`

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      <polygon points={areaPoints} fill={fill} />
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function DualAreaChart({
  first,
  second,
  height = 120,
}: {
  first: number[]
  second: number[]
  height?: number
}) {
  const width = 420
  const merged = [...first, ...second]
  const max = Math.max(...merged, 1)
  const min = Math.min(...merged, 0)
  const span = Math.max(1, max - min)

  const toPoints = (values: number[]) =>
    values
      .map((v, i) => {
        const x = (i / Math.max(values.length - 1, 1)) * width
        const y = height - ((v - min) / span) * (height - 14) - 7
        return `${x},${y}`
      })
      .join(' ')

  const firstPoints = toPoints(first)
  const secondPoints = toPoints(second)

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      <polygon points={`0,${height} ${secondPoints} ${width},${height}`} fill="rgba(45,212,191,0.16)" />
      <polygon points={`0,${height} ${firstPoints} ${width},${height}`} fill="rgba(59,130,246,0.2)" />
      <polyline points={firstPoints} fill="none" stroke="#60a5fa" strokeWidth="2.4" strokeLinecap="round" />
      <polyline points={secondPoints} fill="none" stroke="#34d399" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}

function HorizontalBars({
  items,
  color = '#38bdf8',
}: {
  items: Array<{ label: string; value: number }>
  color?: string
}) {
  const max = Math.max(...items.map((i) => i.value), 1)
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {items.map((item) => (
        <div key={item.label}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#cbd5e1', marginBottom: 3 }}>
            <span>{item.label}</span>
            <span>{Math.round(item.value)}</span>
          </div>
          <div style={{ height: 8, borderRadius: 999, background: 'rgba(148,163,184,0.2)', overflow: 'hidden' }}>
            <div
              style={{
                width: `${(item.value / max) * 100}%`,
                height: '100%',
                borderRadius: 999,
                background: color,
                transition: 'width 450ms ease',
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function AgenticAIDashboard({
  userId,
  users,
  onUserChange,
  onPreferenceSignal,
  chatContent,
}: {
  userId: string
  users?: Array<{ id: string; name?: string }>
  onUserChange?: (nextUserId: string) => void
  onPreferenceSignal?: (signal: KGPreferenceSignal) => void
  chatContent?: React.ReactNode
}) {
  const [activeSection, setActiveSection] = useState<DashboardSection>('chat')
  const [dashboardData, setDashboardData] = useState<any>(null)
  const [metricsError, setMetricsError] = useState<string | null>(null)
  const [lastRefreshTime, setLastRefreshTime] = useState<string>('')

  const apiBase = useMemo(() => {
    if (typeof window !== 'undefined' && (window as any).VITE_API_URL) {
      return (window as any).VITE_API_URL
    }
    return (typeof import.meta !== 'undefined' && (import.meta.env.VITE_API_URL as string)) || '/api'
  }, [])

  useEffect(() => {
    let isMounted = true

    const fetchMetrics = async () => {
      try {
        const res = await fetch(`${apiBase}/dashboard/metrics`)
        if (!res.ok) {
          setMetricsError(`Metrics endpoint returned ${res.status}`)
          return
        }
        const data = await res.json()
        if (isMounted) {
          setDashboardData(data)
          setMetricsError(null)
          setLastRefreshTime(new Date().toLocaleTimeString())
        }
      } catch {
        if (isMounted) {
          setMetricsError('Unable to reach dashboard metrics API')
        }
      }
    }

    fetchMetrics()
    const timer = window.setInterval(fetchMetrics, 10000)
    return () => {
      isMounted = false
      window.clearInterval(timer)
    }
  }, [apiBase])

  const navItems = useMemo(
    () => [
      { key: 'chat' as DashboardSection, label: 'AI Stylist' },
      { key: 'system_overview' as DashboardSection, label: 'System Overview' },
      { key: 'knowledge_graph' as DashboardSection, label: 'Knowledge Graph' },
      { key: 'agent_engine' as DashboardSection, label: 'AI Engine' },
    ],
    [],
  )

  const selectableUsers = useMemo(() => {
    if (Array.isArray(users) && users.length > 0) return users
    if (userId) return [{ id: userId, name: userId }]
    return []
  }, [users, userId])

  const metrics = useMemo(() => {
    const defaults = {
      active_users: 0,
      recommendations_served: 0,
      kg_nodes: 0,
      kg_relationships: 0,
      agent_success_rate: 0,
      pipeline_status: 'Unknown',
      requests_per_hour: Array.from({ length: 24 }, () => 0),
      kg_nodes_over_time: Array.from({ length: 12 }, () => 0),
      kg_edges_over_time: Array.from({ length: 12 }, () => 0),
      system_load_heatmap: Array.from({ length: 7 }, () => Array.from({ length: 12 }, () => 0)),
      real_time_feed: [] as Array<{ user_id: string; product: string; score: number }>,
      agent_latency_ms: { intent: 0, retriever: 0, ranking: 0, styling: 0 },
      node_distribution: { products: 0, users: 0, brands: 0, styles: 0 },
      intent_distribution: {} as Record<string, number>,
      edge_distribution: {} as Record<string, number>,
      kg_health: { enabled: false, vector_search_enabled: false },
      most_connected_products: [] as Array<{ product_id: string; name: string; connections: number }>,
      similarity_clusters: [] as Array<{ name: string; size: number }>,
      strategy_usage: { 'Knowledge Graph': 0, 'Hybrid ML': 0, 'Content Based': 0 },
      top_recommendation_paths: [] as string[],
    }
    const source = dashboardData || defaults
    return {
      activeUsers: Number(source.active_users || 0),
      recommendationsServed: Number(source.recommendations_served || 0),
      kgNodes: Number(source.kg_nodes || 0),
      kgRelationships: Number(source.kg_relationships || 0),
      agentSuccess: Number(source.agent_success_rate || 0),
      pipelineHealth: String(source.pipeline_status || 'Unknown'),
      overviewRequests: Array.isArray(source.requests_per_hour) ? source.requests_per_hour : defaults.requests_per_hour,
      nodesTrend: Array.isArray(source.kg_nodes_over_time) ? source.kg_nodes_over_time : defaults.kg_nodes_over_time,
      edgesTrend: Array.isArray(source.kg_edges_over_time) ? source.kg_edges_over_time : defaults.kg_edges_over_time,
      loadHeatmap: Array.isArray(source.system_load_heatmap) ? source.system_load_heatmap : defaults.system_load_heatmap,
      feed: Array.isArray(source.real_time_feed)
        ? source.real_time_feed.map((item: any) => `${item.user_id} -> ${item.product} -> ${Number(item.score || 0).toFixed(2)}`)
        : [],
      agentLatency: source.agent_latency_ms || defaults.agent_latency_ms,
      nodeDistribution: source.node_distribution || defaults.node_distribution,
      intentDistribution: source.intent_distribution || defaults.intent_distribution,
      edgeDistribution: source.edge_distribution || defaults.edge_distribution,
      kgHealth: source.kg_health || defaults.kg_health,
      connectedProducts: source.most_connected_products || defaults.most_connected_products,
      similarityClusters: source.similarity_clusters || defaults.similarity_clusters,
      strategyUsage: source.strategy_usage || defaults.strategy_usage,
      topPaths: source.top_recommendation_paths || defaults.top_recommendation_paths,
    }
  }, [dashboardData])

  const graphDistribution = useMemo(() => {
    const products = Number(metrics.nodeDistribution.products || 0)
    const usersCount = Number(metrics.nodeDistribution.users || 0)
    const brands = Number(metrics.nodeDistribution.brands || 0)
    const styles = Number(metrics.nodeDistribution.styles || 0)
    const total = Math.max(products + usersCount + brands + styles, 1)
    return [
      { label: 'Products', value: Math.round((products / total) * 100), color: '#60a5fa' },
      { label: 'Users', value: Math.round((usersCount / total) * 100), color: '#34d399' },
      { label: 'Brands', value: Math.round((brands / total) * 100), color: '#f59e0b' },
      { label: 'Styles', value: Math.round((styles / total) * 100), color: '#f472b6' },
    ]
  }, [metrics.nodeDistribution])

  const pieGradient = useMemo(() => {
    const total = graphDistribution.reduce((sum, item) => sum + item.value, 0)
    let start = 0
    const stops = graphDistribution.map((item) => {
      const pct = (item.value / total) * 100
      const segment = `${item.color} ${start.toFixed(2)}% ${(start + pct).toFixed(2)}%`
      start += pct
      return segment
    })
    return `conic-gradient(${stops.join(', ')})`
  }, [graphDistribution])

  const mostConnectedProducts = useMemo(
    () => {
      if (Array.isArray(metrics.connectedProducts) && metrics.connectedProducts.length > 0) {
        return metrics.connectedProducts.map((item: { name: string; connections: number }) => ({
          label: item.name,
          value: Number(item.connections),
        }))
      }
      const intents = Object.entries(metrics.intentDistribution)
        .map(([label, value]) => ({ label, value: Number(value) }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 4)
      if (intents.length > 0) return intents
      return [
        { label: 'No interaction data yet', value: 0 },
        { label: 'Start chatting to populate', value: 0 },
      ]
    },
    [metrics.intentDistribution],
  )

  const agentLatency = useMemo(
    () => [
      { label: 'Intent Agent', value: Number(metrics.agentLatency.intent || 0) },
      { label: 'KG Retriever', value: Number(metrics.agentLatency.retriever || 0) },
      { label: 'Ranking Agent', value: Number(metrics.agentLatency.ranking || 0) },
      { label: 'Styling Agent', value: Number(metrics.agentLatency.styling || 0) },
    ],
    [metrics.agentLatency],
  )

  const scoreDistribution = useMemo(
    () => {
      const requests = metrics.overviewRequests
      const bucket = Math.max(Math.floor(requests.length / 10), 1)
      return Array.from({ length: 10 }, (_, i) => {
        const chunk = requests.slice(i * bucket, (i + 1) * bucket)
        const sum = chunk.reduce((acc: number, cur: number) => acc + Number(cur || 0), 0)
        return Math.max(0, Math.round(sum / Math.max(chunk.length, 1)))
      })
    },
    [metrics.overviewRequests],
  )

  const strategyGradient = useMemo(() => {
    const entries = Object.entries(metrics.strategyUsage || {})
    const total = Math.max(
      entries.reduce((sum: number, [, value]) => sum + Number(value || 0), 0),
      1,
    )
    const palette = ['#60a5fa', '#34d399', '#f59e0b']
    let start = 0
    const segments = entries.map(([_, value], idx) => {
      const pct = (Number(value || 0) / total) * 100
      const current = `${palette[idx % palette.length]} ${start.toFixed(2)}% ${(start + pct).toFixed(2)}%`
      start += pct
      return current
    })
    return `conic-gradient(${segments.join(', ')})`
  }, [metrics.strategyUsage])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%', minHeight: 0 }}>
      <section style={{ padding: '2px 2px 0 2px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', gap: 16, overflowX: 'auto', paddingBottom: 2 }}>
            {navItems.map((item) => {
              const active = activeSection === item.key
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveSection(item.key)}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    color: active ? '#93c5fd' : '#94a3b8',
                    padding: '6px 0',
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: active ? 700 : 500,
                    whiteSpace: 'nowrap',
                    textDecoration: active ? 'underline' : 'none',
                    textUnderlineOffset: 6,
                  }}
                >
                  {item.label}
                </button>
              )
            })}
          </div>
          {activeSection === 'chat' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <label htmlFor="ai-stylist-user" style={{ color: '#94a3b8', fontSize: 12 }}>User</label>
              <select
                id="ai-stylist-user"
                value={userId}
                onChange={(e) => onUserChange?.(e.target.value)}
                disabled={!onUserChange || selectableUsers.length === 0}
                style={{
                  borderRadius: 8,
                  border: '1px solid rgba(148,163,184,0.35)',
                  background: 'rgba(2,6,23,0.45)',
                  color: '#e2e8f0',
                  fontSize: 12,
                  padding: '5px 10px',
                  cursor: 'pointer',
                  minWidth: 130,
                }}
              >
                {selectableUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name || u.id}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </section>

      <section style={{ padding: '0 2px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: 12,
            color: '#94a3b8',
          }}
        >
          <span>
            {metricsError
              ? `Data status: ${metricsError}`
              : dashboardData
                ? 'Data status: Live metrics connected'
                : 'Data status: Waiting for first metrics payload'}
          </span>
          <span>{lastRefreshTime ? `Last refresh: ${lastRefreshTime}` : ''}</span>
        </div>
      </section>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
          flex: 1,
          minHeight: 0,
          overflowX: 'hidden',
          overflowY: activeSection === 'chat' ? 'hidden' : 'auto',
        }}
      >
        {activeSection === 'chat' && (
          <section style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {chatContent}
          </section>
        )}

        {activeSection === 'system_overview' && (
          <>
            <section
              style={{
                padding: '2px 0',
                color: '#e2e8f0',
              }}
            >
              <div style={{ fontSize: 18, fontWeight: 700 }}>System Overview</div>
              <div style={{ marginTop: 2, fontSize: 11, color: '#94a3b8' }}>
                Executive dashboard with live recommendation, graph, agent, and pipeline telemetry.
              </div>
            </section>

            <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
              {[
                { label: 'Active Users', value: formatNumber(metrics.activeUsers) },
                { label: 'Recommendations Served', value: formatNumber(metrics.recommendationsServed) },
                { label: 'KG Nodes', value: formatNumber(metrics.kgNodes) },
                { label: 'KG Relationships', value: formatNumber(metrics.kgRelationships) },
                { label: 'Agent Success Rate', value: `${metrics.agentSuccess.toFixed(1)}%` },
                { label: 'Pipeline Status', value: metrics.pipelineHealth },
              ].map((kpi) => (
                <article key={kpi.label} style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}>
                  <div style={{ fontSize: 12, color: '#93c5fd' }}>{kpi.label}</div>
                  <div style={{ marginTop: 5, fontSize: 18, fontWeight: 700 }}>{kpi.value}</div>
                </article>
              ))}
            </section>

            <section style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1.2fr', gap: 10 }}>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 6 }}>Recommendation Requests (per hour)</div>
                <MiniLineChart values={metrics.overviewRequests} />
              </article>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 6 }}>KG Growth</div>
                <DualAreaChart first={metrics.nodesTrend} second={metrics.edgesTrend} />
                <div style={{ display: 'flex', gap: 10, fontSize: 12, color: '#cbd5e1', marginTop: 5 }}>
                  <span>Nodes</span>
                  <span>Edges</span>
                </div>
              </article>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 8 }}>Real-Time Recommendation Feed</div>
                <div style={{ maxHeight: 130, overflowY: 'auto', display: 'grid', gap: 6 }}>
                  {metrics.feed.map((item: string) => (
                    <div key={item} style={{ fontSize: 12, color: '#cbd5e1', padding: '4px 6px', borderRadius: 8, background: 'rgba(2,6,23,0.35)' }}>{item}</div>
                  ))}
                </div>
              </article>
            </section>

            <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
              <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 8 }}>System Load Heatmap (Time vs API Requests)</div>
              <div style={{ display: 'grid', gap: 4 }}>
                {metrics.loadHeatmap.map((row: number[], rowIdx: number) => (
                  <div key={`row-${rowIdx}`} style={{ display: 'grid', gridTemplateColumns: 'repeat(12, minmax(0, 1fr))', gap: 4 }}>
                    {row.map((cell: number, cellIdx: number) => (
                      <div
                        key={`${rowIdx}-${cellIdx}`}
                        style={{
                          height: 16,
                          borderRadius: 4,
                          background: `rgba(56,189,248, ${cell.toFixed(2)})`,
                          border: '1px solid rgba(148,163,184,0.2)',
                        }}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </article>
          </>
        )}

        {activeSection === 'knowledge_graph' && (
          <>
            <section style={{ padding: '2px 0', color: '#e2e8f0' }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>Knowledge Graph</div>
              <div style={{ marginTop: 2, fontSize: 11, color: '#94a3b8' }}>Interactive structure for user, product, style, and recommendation relationships.</div>
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {['User', 'Product', 'Brand', 'Category', 'Style', 'Season', 'Material'].map((node) => (
                  <span key={node} style={{ padding: '4px 10px', borderRadius: 999, fontSize: 12, background: 'rgba(59,130,246,0.18)', border: '1px solid rgba(96,165,250,0.4)' }}>{node}</span>
                ))}
              </div>
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {Object.entries(metrics.edgeDistribution || {}).map(([edge, count]) => (
                  <span key={edge} style={{ padding: '4px 10px', borderRadius: 999, fontSize: 12, background: 'rgba(16,185,129,0.15)', border: '1px solid rgba(52,211,153,0.38)' }}>
                    {edge} ({Number(count || 0)})
                  </span>
                ))}
              </div>
            </section>

            <section style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr', gap: 10 }}>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 8 }}>Interactive Graph Explorer</div>
                <svg viewBox="0 0 520 220" width="100%" style={{ display: 'block', borderRadius: 8, background: 'rgba(2,6,23,0.28)' }}>
                  <line x1="70" y1="105" x2="210" y2="62" stroke="#7dd3fc" strokeWidth="2" />
                  <line x1="210" y1="62" x2="350" y2="110" stroke="#7dd3fc" strokeWidth="2" />
                  <line x1="210" y1="62" x2="460" y2="70" stroke="#34d399" strokeWidth="2" />
                  <line x1="350" y1="110" x2="460" y2="160" stroke="#60a5fa" strokeWidth="2" />
                  <circle cx="70" cy="105" r="24" fill="#0ea5e9" />
                  <circle cx="210" cy="62" r="26" fill="#6366f1" />
                  <circle cx="350" cy="110" r="22" fill="#10b981" />
                  <circle cx="460" cy="70" r="20" fill="#f59e0b" />
                  <circle cx="460" cy="160" r="20" fill="#ec4899" />
                  <text x="70" y="111" textAnchor="middle" fill="#e2e8f0" fontSize="11">User</text>
                  <text x="210" y="67" textAnchor="middle" fill="#e2e8f0" fontSize="11">Product</text>
                  <text x="350" y="115" textAnchor="middle" fill="#e2e8f0" fontSize="11">Product</text>
                  <text x="460" y="74" textAnchor="middle" fill="#e2e8f0" fontSize="10">Category</text>
                  <text x="460" y="164" textAnchor="middle" fill="#e2e8f0" fontSize="10">Style</text>
                </svg>
              </article>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 8 }}>Node Distribution</div>
                <div style={{ width: 146, height: 146, margin: '0 auto', borderRadius: '50%', background: pieGradient, border: '1px solid rgba(148,163,184,0.35)' }} />
                <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                  {graphDistribution.map((item) => (
                    <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#cbd5e1' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: item.color }} />
                        {item.label}
                      </span>
                      <span>{item.value}%</span>
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Graph Density</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div style={{ padding: 10, borderRadius: 10, background: 'rgba(2,6,23,0.34)' }}>
                    <div style={{ fontSize: 12, color: '#93c5fd' }}>Avg Node Degree</div>
                    <div style={{ marginTop: 4, fontSize: 18, fontWeight: 700 }}>{(metrics.kgRelationships / Math.max(metrics.kgNodes, 1)).toFixed(2)}</div>
                  </div>
                  <div style={{ padding: 10, borderRadius: 10, background: 'rgba(2,6,23,0.34)' }}>
                    <div style={{ fontSize: 12, color: '#93c5fd' }}>Connectivity</div>
                    <div style={{ marginTop: 4, fontSize: 18, fontWeight: 700 }}>{clamp((metrics.kgRelationships / Math.max(metrics.kgNodes * 3, 1)) * 100, 0, 100).toFixed(1)}%</div>
                  </div>
                </div>
              </article>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 8 }}>Most Connected Products</div>
                <HorizontalBars items={mostConnectedProducts} color="#22d3ee" />
              </article>
            </section>

            <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Similarity Network Clusters</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                {(metrics.similarityClusters.length > 0
                  ? metrics.similarityClusters
                  : [{ name: 'No cluster data yet', size: 0 }]
                ).map((cluster: { name: string; size: number }) => (
                  <div key={cluster.name} style={{ padding: 10, borderRadius: 10, background: 'rgba(2,6,23,0.33)', border: '1px solid rgba(148,163,184,0.25)' }}>
                    <div style={{ fontWeight: 600 }}>{cluster.name}</div>
                    <div style={{ marginTop: 4, fontSize: 12, color: '#cbd5e1' }}>Products in cluster: {cluster.size}</div>
                  </div>
                ))}
              </div>
            </article>
          </>
        )}

        {activeSection === 'agent_engine' && (
          <>
            <section style={{ padding: '2px 0', color: '#e2e8f0' }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>AI Engine</div>
              <div style={{ marginTop: 2, fontSize: 11, color: '#94a3b8' }}>Intent detection, KG retrieval, ranking, and styling generation flow.</div>
            </section>

            <section style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 10 }}>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Agent Pipeline Visualization</div>
                <div style={{ display: 'grid', gap: 6, maxWidth: 340 }}>
                  {['User Query', 'Intent Agent', 'KG Retrieval Agent', 'Ranking Agent', 'Styling Agent', 'Recommendation'].map((step, idx, arr) => (
                    <React.Fragment key={step}>
                      <div style={{ borderRadius: 8, padding: '8px 10px', background: 'rgba(2,6,23,0.36)', border: '1px solid rgba(148,163,184,0.25)', fontSize: 13 }}>{step}</div>
                      {idx < arr.length - 1 && <div style={{ color: '#93c5fd', marginLeft: 12 }}>↓</div>}
                    </React.Fragment>
                  ))}
                </div>
              </article>

              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 8 }}>Agent Latency (ms)</div>
                <HorizontalBars items={agentLatency} color="#60a5fa" />
              </article>
            </section>

            <section style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr', gap: 10 }}>
              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Recommendation Strategy Usage</div>
                <div style={{ width: 150, height: 150, borderRadius: '50%', background: strategyGradient, margin: '0 auto', border: '1px solid rgba(148,163,184,0.3)' }} />
                <div style={{ marginTop: 10, display: 'grid', gap: 5, fontSize: 12, color: '#cbd5e1' }}>
                  {Object.entries(metrics.strategyUsage).map(([name, pct]) => (
                    <div key={name}>{name} {Number(pct || 0)}%</div>
                  ))}
                </div>
              </article>

              <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Top Recommendation Paths</div>
                <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
                  {(metrics.topPaths.length > 0
                    ? metrics.topPaths
                    : ['No path data yet. Start querying the AI stylist to populate recommendation paths.']
                  ).map((path: string) => (
                    <div key={path} style={{ borderRadius: 8, padding: 8, background: 'rgba(2,6,23,0.33)' }}>{path}</div>
                  ))}
                </div>
              </article>
            </section>

            <article style={{ borderRadius: 12, padding: 12, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)' }}>
              <div style={{ color: '#f8fafc', fontWeight: 700, marginBottom: 8 }}>Recommendation Score Distribution</div>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${scoreDistribution.length}, minmax(0, 1fr))`, gap: 6, alignItems: 'end', minHeight: 140 }}>
                {scoreDistribution.map((value, idx) => (
                  <div key={`hist-${idx}`} style={{ height: `${value * 4}px`, borderRadius: 6, background: 'linear-gradient(180deg, #60a5fa 0%, #2563eb 100%)' }} />
                ))}
              </div>
            </article>
          </>
        )}


      </div>
    </div>
  )
}
