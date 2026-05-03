import React, { useEffect, useMemo, useState } from 'react'
import { Pencil, RefreshCw, UserRound } from 'lucide-react'
import shoppingAssistantAvatar from '../../../assets/shopping-assistant-avatar.svg'
import type { KGPreferenceSignal } from '../services/kgSignals'
import FeatureOpsWorkflowPanel from '../components/FeatureOpsWorkflowPanel.tsx'
import OrderAssistantPage from './OrderAssistantPage'

type DashboardSection =
  | 'chat'
  | 'order_assistant'
  | 'user_profile'
  | 'system_overview'
  | 'knowledge_graph'
  | 'featureops_workflow'
  | 'feedback_center'

type OrderAssistantCheckoutRequest = {
  id: string
  url: string
  quantity?: number
  size?: string
  color?: string
  name?: string
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function formatNumber(value: number) {
  return value.toLocaleString('en-US')
}

function formatCurrency(value: number) {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getInitials(name?: string | null, fallback = 'U') {
  const raw = String(name || '').trim()
  if (!raw) return fallback
  const parts = raw.split(/\s+/).filter(Boolean)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0] || ''}${parts[1][0] || ''}`.toUpperCase()
}

type DashboardUserProfile = {
  user: {
    user_id: string
    name?: string | null
    email?: string | null
    phone?: string | null
    shipping_address?: string | null
    signup_ts?: string | null
    is_active?: boolean | null
  }
  preferences: {
    categories: string[]
    colors: string[]
    fabrics: string[]
    shops: string[]
    styles: string[]
    sizes?: string[]
    skin_tone?: string | null
    body_type?: string | null
    price_sensitivity?: string | null
    updated_ts?: string | null
  }
  available_options: {
    categories: string[]
    colors: string[]
    fabrics: string[]
    shops: string[]
    styles: string[]
    sizes: string[]
    price_sensitivity: string[]
  }
  cart_summary: {
    items_count: number
    last_activity_date?: string | null
    estimated_total_lkr: number
  }
  purchase_summary: {
    orders_count: number
    last_order_date?: string | null
    total_spend: number
    average_order_value: number
    recent_payment_method?: string | null
  }
  automation: {
    auto_fill_checkout: boolean
    auto_apply_preferences: boolean
    confirm_before_checkout: boolean
  }
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
  labelColor = '#cbd5e1',
}: {
  items: Array<{ label: string; value: number }>
  color?: string
  labelColor?: string
}) {
  const max = Math.max(...items.map((i) => i.value), 1)
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {items.map((item) => (
        <div key={item.label}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: labelColor, marginBottom: 3 }}>
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
  onOpenShoppingCart,
  initialSection,
  orderAssistantCheckoutRequest,
  onOrderAssistantCheckoutRequestConsumed,
  chatContent,
}: {
  userId: string
  users?: Array<{ id: string; name?: string }>
  onUserChange?: (nextUserId: string) => void
  onPreferenceSignal?: (signal: KGPreferenceSignal) => void
  onOpenShoppingCart?: () => void | Promise<void>
  initialSection?: DashboardSection
  orderAssistantCheckoutRequest?: OrderAssistantCheckoutRequest | null
  onOrderAssistantCheckoutRequestConsumed?: () => void
  chatContent?: React.ReactNode
}) {
  const [activeSection, setActiveSection] = useState<DashboardSection>('chat')
  const [systemOverviewTopic, setSystemOverviewTopic] = useState<'recommendations' | 'analytics' | 'query_logs'>('recommendations')
  const [dashboardData, setDashboardData] = useState<any>(null)
  const [metricsError, setMetricsError] = useState<string | null>(null)
  const [lastRefreshTime, setLastRefreshTime] = useState<string>('')
  const [showOrderAssistantBubble, setShowOrderAssistantBubble] = useState(false)
  const [metricsRefreshTick, setMetricsRefreshTick] = useState(0)
  const [userProfileData, setUserProfileData] = useState<DashboardUserProfile | null>(null)
  const [userProfileLoading, setUserProfileLoading] = useState(false)
  const [userProfileError, setUserProfileError] = useState<string | null>(null)
  const [profileSaveLoading, setProfileSaveLoading] = useState(false)
  const [profileSaveMessage, setProfileSaveMessage] = useState<string | null>(null)
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [editableUserDetails, setEditableUserDetails] = useState({
    name: '',
    email: '',
    phone: '',
    shipping_address: '',
  })
  const [automationDraft, setAutomationDraft] = useState({
    auto_fill_checkout: false,
    auto_apply_preferences: false,
    confirm_before_checkout: false,
  })
  const [prefRefreshTick, setPrefRefreshTick] = useState({
    categories: 0,
    colors: 0,
    shops: 0,
    styles: 0,
    fabrics: 0,
  })
  const [editablePreferences, setEditablePreferences] = useState<{
    categories: string[]
    colors: string[]
    fabrics: string[]
    shops: string[]
    styles: string[]
  }>({
    categories: [],
    colors: [],
    fabrics: [],
    shops: [],
    styles: [],
  })
  const [savedPreferences, setSavedPreferences] = useState<{
    categories: string[]
    colors: string[]
    fabrics: string[]
    shops: string[]
    styles: string[]
  }>({
    categories: [],
    colors: [],
    fabrics: [],
    shops: [],
    styles: [],
  })
  const [cartSummaryRefreshing, setCartSummaryRefreshing] = useState(false)
  const [queryLogUserSearch, setQueryLogUserSearch] = useState('')
  const [selectedQueryLogUser, setSelectedQueryLogUser] = useState('all')
  const [kgZoom, setKgZoom] = useState(1)
  const [kgPan, setKgPan] = useState({ x: 0, y: 0 })
  const [kgClusterMode, setKgClusterMode] = useState(false)
  const [kgPhysicsEnabled, setKgPhysicsEnabled] = useState(true)
  const [kgPhysicsTick, setKgPhysicsTick] = useState(0)
  const [kgHoveredNodeId, setKgHoveredNodeId] = useState<string | null>(null)
  const [kgPanning, setKgPanning] = useState(false)
  const [kgPanAnchor, setKgPanAnchor] = useState({ x: 0, y: 0 })
  const [kgPinchStartDistance, setKgPinchStartDistance] = useState<number | null>(null)
  const [kgPinchStartZoom, setKgPinchStartZoom] = useState<number | null>(null)

  useEffect(() => {
    if (!initialSection) return
    if (initialSection === 'knowledge_graph') {
      setActiveSection('system_overview')
      return
    }
    if (initialSection === 'order_assistant') {
      setActiveSection('chat')
      setShowOrderAssistantBubble(true)
      return
    }
    setActiveSection(initialSection)
  }, [initialSection])

  useEffect(() => {
    if (activeSection === 'knowledge_graph') {
      setActiveSection('system_overview')
    }
  }, [activeSection])

  useEffect(() => {
    if (!orderAssistantCheckoutRequest?.id) return
    setActiveSection('chat')
    setShowOrderAssistantBubble(true)
  }, [orderAssistantCheckoutRequest?.id])

  useEffect(() => {
    const handleOpenOrderingAssistant = () => {
      setActiveSection('chat')
      setShowOrderAssistantBubble(true)
    }

    window.addEventListener('open-ordering-assistant', handleOpenOrderingAssistant)
    return () => window.removeEventListener('open-ordering-assistant', handleOpenOrderingAssistant)
  }, [])

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
  }, [apiBase, metricsRefreshTick])

  async function refreshUserProfile(silent = false) {
    if (!userId) return
    if (!silent) setUserProfileLoading(true)
    setUserProfileError(null)
    try {
      const res = await fetch(`${apiBase}/users/${encodeURIComponent(userId)}/profile`)
      if (!res.ok) {
        setUserProfileError(`User profile endpoint returned ${res.status}`)
        return
      }
      const payload = (await res.json()) as DashboardUserProfile
      setUserProfileData(payload)
      setEditableUserDetails({
        name: String(payload.user.name || ''),
        email: String(payload.user.email || ''),
        phone: String(payload.user.phone || ''),
        shipping_address: String(payload.user.shipping_address || ''),
      })
      setAutomationDraft({
        auto_fill_checkout: !!payload.automation.auto_fill_checkout,
        auto_apply_preferences: !!payload.automation.auto_apply_preferences,
        confirm_before_checkout: !!payload.automation.confirm_before_checkout,
      })
      setEditablePreferences({
        categories: payload.preferences.categories || [],
        colors: payload.preferences.colors || [],
        fabrics: payload.preferences.fabrics || [],
        shops: payload.preferences.shops || [],
        styles: payload.preferences.styles || [],
      })
      setSavedPreferences({
        categories: payload.preferences.categories || [],
        colors: payload.preferences.colors || [],
        fabrics: payload.preferences.fabrics || [],
        shops: payload.preferences.shops || [],
        styles: payload.preferences.styles || [],
      })
      setProfileSaveMessage(null)
      setIsEditingProfile(false)
    } catch {
      setUserProfileError('Unable to load user profile data')
    } finally {
      if (!silent) setUserProfileLoading(false)
    }
  }

  useEffect(() => {
    if (!userId || (activeSection !== 'user_profile' && !showOrderAssistantBubble)) return
    let mounted = true

    void (async () => {
      if (!mounted) return
      await refreshUserProfile(activeSection !== 'user_profile')
    })()

    return () => {
      mounted = false
    }
  }, [apiBase, userId, activeSection, showOrderAssistantBubble])

  useEffect(() => {
    if (!kgPhysicsEnabled || activeSection !== 'knowledge_graph') return
    const timer = window.setInterval(() => {
      setKgPhysicsTick((v) => (v + 1) % 100000)
    }, 900)
    return () => window.clearInterval(timer)
  }, [activeSection, kgPhysicsEnabled])

  const navItems = useMemo(
    () => [
      { key: 'chat' as DashboardSection, label: 'AI Stylist' },
      { key: 'featureops_workflow' as DashboardSection, label: 'DE Workflow' },
      { key: 'system_overview' as DashboardSection, label: 'System Overview' },
      { key: 'feedback_center' as DashboardSection, label: 'Recommendation Feedback' },
    ],
    [],
  )

  const selectableUsers = useMemo(() => {
    if (Array.isArray(users) && users.length > 0) return users
    if (userId) return [{ id: userId, name: userId }]
    return []
  }, [users, userId])

  const selectedUser = useMemo(() => {
    return selectableUsers.find((u) => u.id === userId) || (userId ? { id: userId, name: userId } : null)
  }, [selectableUsers, userId])

  async function persistPreferences(nextPreferences: {
    categories: string[]
    colors: string[]
    fabrics: string[]
    shops: string[]
    styles: string[]
  }) {
    if (!userId || profileSaveLoading) return
    setProfileSaveLoading(true)
    setProfileSaveMessage(null)
    try {
      const res = await fetch(`${apiBase}/users/${encodeURIComponent(userId)}/profile/preferences`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preferences: nextPreferences }),
      })
      if (!res.ok) {
        setProfileSaveMessage(`Failed to sync preferences (${res.status})`)
        return
      }
      const updated = (await res.json()) as DashboardUserProfile
      setUserProfileData(updated)
      const nextSaved = {
        categories: updated.preferences.categories || [],
        colors: updated.preferences.colors || [],
        fabrics: updated.preferences.fabrics || [],
        shops: updated.preferences.shops || [],
        styles: updated.preferences.styles || [],
      }
      setEditablePreferences(nextSaved)
      setSavedPreferences(nextSaved)
      if (onPreferenceSignal) {
        onPreferenceSignal({ userId, type: 'style', value: 'Preference updated.', weight: 1 })
      }
      setProfileSaveMessage('Preference updated.')
    } catch {
      setProfileSaveMessage('Failed to sync preferences')
    } finally {
      setProfileSaveLoading(false)
    }
  }

  function togglePreferenceValue(
    field: 'categories' | 'colors' | 'fabrics' | 'shops' | 'styles',
    value: string,
  ) {
    setEditablePreferences((prev) => {
      const exists = prev[field].includes(value)
      if (!exists && prev[field].length >= 5) {
        setProfileSaveMessage(`You can select up to 5 ${field}.`)
        return prev
      }
      const nextValues = exists ? prev[field].filter((v) => v !== value) : [...prev[field], value]
      setProfileSaveMessage('Unsaved preference changes.')
      return { ...prev, [field]: nextValues }
    })
  }

  const isPreferencesDirty = useMemo(() => {
    const normalize = (items: string[]) => [...items].map((v) => String(v).trim()).filter(Boolean).sort().join('|')
    return (
      normalize(editablePreferences.categories) !== normalize(savedPreferences.categories)
      || normalize(editablePreferences.colors) !== normalize(savedPreferences.colors)
      || normalize(editablePreferences.fabrics) !== normalize(savedPreferences.fabrics)
      || normalize(editablePreferences.shops) !== normalize(savedPreferences.shops)
      || normalize(editablePreferences.styles) !== normalize(savedPreferences.styles)
    )
  }, [editablePreferences, savedPreferences])

  async function saveUserPreferences() {
    await persistPreferences(editablePreferences)
  }

  function getVisibleOptions(field: 'categories' | 'colors' | 'shops' | 'styles' | 'fabrics'): string[] {
    const all = ((userProfileData?.available_options?.[field] || []) as string[]).filter(Boolean)
    const selectedAll = editablePreferences[field] || []
    const selectedPinned = selectedAll.slice(0, 5)
    const unselected = all.filter((item) => !selectedAll.includes(item))
    const room = Math.max(0, 8 - selectedPinned.length)
    if (room === 0) return selectedPinned
    if (unselected.length <= room) return [...selectedPinned, ...unselected]

    const offset = (prefRefreshTick[field] * room) % unselected.length
    const rotated = [...unselected.slice(offset), ...unselected.slice(0, offset)]
    return [...selectedPinned, ...rotated.slice(0, room)]
  }

  async function savePersonalDetails() {
    if (!userId || profileSaveLoading) return
    setProfileSaveLoading(true)
    setProfileSaveMessage(null)
    try {
      const res = await fetch(`${apiBase}/users/${encodeURIComponent(userId)}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user: {
            phone: editableUserDetails.phone,
            shipping_address: editableUserDetails.shipping_address,
          },
          automation: automationDraft,
        }),
      })
      if (!res.ok) {
        setProfileSaveMessage(`Failed to save profile (${res.status})`)
        return
      }
      const updated = (await res.json()) as DashboardUserProfile
      setUserProfileData(updated)
      setIsEditingProfile(false)
      setProfileSaveMessage('Profile details updated.')
    } catch {
      setProfileSaveMessage('Failed to save profile details')
    } finally {
      setProfileSaveLoading(false)
    }
  }

  async function saveAutomation(nextAutomation: typeof automationDraft) {
    if (!userId || profileSaveLoading) return
    setProfileSaveLoading(true)
    setProfileSaveMessage(null)
    try {
      const res = await fetch(`${apiBase}/users/${encodeURIComponent(userId)}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: editableUserDetails, automation: nextAutomation }),
      })
      if (!res.ok) {
        setProfileSaveMessage(`Failed to save automation (${res.status})`)
        return
      }
      const updated = (await res.json()) as DashboardUserProfile
      setUserProfileData(updated)
      setAutomationDraft({
        auto_fill_checkout: !!updated.automation.auto_fill_checkout,
        auto_apply_preferences: !!updated.automation.auto_apply_preferences,
        confirm_before_checkout: !!updated.automation.confirm_before_checkout,
      })
      setProfileSaveMessage('Automation updated.')
    } catch {
      setProfileSaveMessage('Failed to update automation')
    } finally {
      setProfileSaveLoading(false)
    }
  }

  async function refreshCartSummaryCard() {
    if (!userId) return
    setCartSummaryRefreshing(true)
    setProfileSaveMessage(null)
    try {
      const res = await fetch(`${apiBase}/users/${encodeURIComponent(userId)}/profile`)
      if (!res.ok) {
        setProfileSaveMessage(`Failed to refresh cart summary (${res.status})`)
        return
      }
      const payload = (await res.json()) as DashboardUserProfile
      setUserProfileData((prev) => {
        if (!prev) return payload
        return {
          ...prev,
          cart_summary: payload.cart_summary,
          purchase_summary: payload.purchase_summary,
        }
      })
      setProfileSaveMessage('Cart summary updated.')
    } catch {
      setProfileSaveMessage('Failed to refresh cart summary')
    } finally {
      setCartSummaryRefreshing(false)
    }
  }

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
      query_logs: [] as Array<{
        query_id?: string
        ts: number
        user_id: string
        query: string
        intent: string
        uses_kg: boolean
        personalized: boolean
        llm_used: string
        fine_tuned_model?: string | null
        pkl_model_used: boolean
        final_response_weight?: number
        model_route?: string
        fallback_used?: boolean
        reasoning_summary?: string
        recommendation_breakdown?: Array<{
          rank: number
          product_id?: string
          product_name: string
          score: number
          final_weight: number
          reason: string
        }>
      }>,
      size_availability_proof: [] as Array<{
        ts: number
        event_type?: string
        query_id: string
        user_id?: string
        product_id: string
        product_name?: string
        size: string
        stock_before: number
        stock_after: number
        visible_to_user: boolean
      }>,
      kg_growth: {
        user_wise: [] as Array<{ user_id: string; events: number; avg_score: number }>,
        system_wise: [] as Array<{ date: string; requests: number; recommendations: number }>,
      },
      satisfaction: {
        avg_rating: 0,
        count: 0,
        checkout_count: 0,
        add_to_cart_count: 0,
      },
      query_feedback_summary: {
        total: 6,
        positive_rate: 66.7,
        negative_rate: 16.7,
        skip_rate: 16.7,
      },
      query_feedback: [] as Array<{
        feedback_id: string
        query_id: string
        user_id: string
        query_text: string
        detected_intent: string
        feedback_type: 'yes' | 'no' | 'skip'
        recommendation_count: number
        model_route?: string
        structured_style?: string
        structured_event?: string
        structured_budget?: string
        ts: number
      }>,
      user_management: {
        total_users: 0,
        active_users: 0,
        total_queries: 0,
        avg_satisfaction: 0,
        rows: [] as Array<{ name: string; email: string; status: string; queries: number; satisfaction: number; joined: string }>,
      },
      user_interactions: {
        total_interactions: 0,
        product_views: 0,
        cart_additions: 0,
        checkouts: 0,
        weekly_trends: {} as Record<string, { views: number; clicks: number; cart_additions: number; checkouts: number }>,
        recent: [] as Array<{ user: string; event: string; rating: number; source: string }>,
      },
      recommendation_weights: {
        collaborative_filtering: 0,
        content_based_filtering: 0,
        hybrid_approach: 0,
      },
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
      queryLogs: Array.isArray(source.query_logs) ? source.query_logs : defaults.query_logs,
      sizeAvailabilityProof: Array.isArray(source.size_availability_proof)
        ? source.size_availability_proof
        : defaults.size_availability_proof,
      kgGrowth: source.kg_growth || defaults.kg_growth,
      satisfaction: source.satisfaction || defaults.satisfaction,
      queryFeedbackSummary: source.query_feedback_summary || defaults.query_feedback_summary,
      queryFeedback: Array.isArray(source.query_feedback) ? source.query_feedback : defaults.query_feedback,
      userManagement: source.user_management || defaults.user_management,
      userInteractions: source.user_interactions || defaults.user_interactions,
      recommendationWeights: source.recommendation_weights || defaults.recommendation_weights,
    }
  }, [dashboardData])

  const interactionWeekRows = useMemo(() => {
    const order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return order.map((day) => ({
      day,
      views: Number(metrics.userInteractions?.weekly_trends?.[day]?.views || 0),
      clicks: Number(metrics.userInteractions?.weekly_trends?.[day]?.clicks || 0),
      cartAdditions: Number(metrics.userInteractions?.weekly_trends?.[day]?.cart_additions || 0),
      checkouts: Number(metrics.userInteractions?.weekly_trends?.[day]?.checkouts || 0),
    }))
  }, [metrics.userInteractions])

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

  const totalRequestsToday = useMemo(
    () => metrics.overviewRequests.reduce((sum: number, value: number) => sum + Number(value || 0), 0),
    [metrics.overviewRequests],
  )

  const edgeTypeRows = useMemo(() => {
    return Object.entries(metrics.edgeDistribution || {})
      .map(([edgeType, count]) => ({ edgeType, count: Number(count || 0) }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12)
  }, [metrics.edgeDistribution])

  const kgTopology = useMemo(() => {
    const productNodes = mostConnectedProducts
      .slice(0, 6)
      .map((item, idx) => ({
        id: `product-${idx}`,
        label: String(item.label || `Product ${idx + 1}`),
        value: Number(item.value || 0),
        kind: 'product' as const,
      }))

    const relationNodes = edgeTypeRows
      .slice(0, 4)
      .map((item, idx) => ({
        id: `edge-${idx}`,
        label: String(item.edgeType || `REL_${idx + 1}`),
        value: Number(item.count || 0),
        kind: 'relation' as const,
      }))

    const userNodes = (metrics.kgGrowth?.user_wise || [])
      .slice(0, 3)
      .map((item: { user_id: string; events: number }, idx: number) => ({
        id: `user-${idx}`,
        label: `User ${String(item.user_id || idx + 1)}`,
        value: Number(item.events || 0),
        kind: 'user' as const,
      }))

    const clusterNodes = (metrics.similarityClusters || [])
      .slice(0, 3)
      .map((item: { name: string; size: number }, idx: number) => ({
        id: `cluster-${idx}`,
        label: String(item.name || `Cluster ${idx + 1}`),
        value: Number(item.size || 0),
        kind: 'cluster' as const,
      }))

    const compactNodes = kgClusterMode
      ? [
        { id: 'cluster-products', label: 'Products', value: productNodes.reduce((sum, n) => sum + n.value, 0), kind: 'cluster' as const },
        { id: 'cluster-relations', label: 'Relations', value: relationNodes.reduce((sum, n) => sum + n.value, 0), kind: 'cluster' as const },
        { id: 'cluster-users', label: 'Users', value: userNodes.reduce((sum: number, n: { id: string; label: string; value: number; kind: 'user' }) => sum + n.value, 0), kind: 'cluster' as const },
      ]
      : []

    const slots = [
      { x: 130, y: 70 },
      { x: 340, y: 40 },
      { x: 550, y: 72 },
      { x: 760, y: 118 },
      { x: 840, y: 224 },
      { x: 700, y: 336 },
      { x: 500, y: 372 },
      { x: 290, y: 346 },
      { x: 145, y: 282 },
      { x: 92, y: 188 },
      { x: 400, y: 130 },
      { x: 618, y: 182 },
      { x: 490, y: 248 },
      { x: 262, y: 210 },
    ]

    const sourceNodes = kgClusterMode ? compactNodes : [...productNodes, ...relationNodes, ...userNodes, ...clusterNodes]
    const sideNodes = sourceNodes.map((node, idx) => {
      const wiggleX = kgPhysicsEnabled ? Math.round(Math.sin((kgPhysicsTick + idx * 7) / 4) * 7) : 0
      const wiggleY = kgPhysicsEnabled ? Math.round(Math.cos((kgPhysicsTick + idx * 5) / 5) * 6) : 0
      const kindColorMap: Record<string, string> = {
        product: '#2563eb',
        relation: '#22c55e',
        user: '#8b5cf6',
        cluster: '#f59e0b',
      }
      return {
      ...node,
      x: slots[idx % slots.length].x + wiggleX,
      y: slots[idx % slots.length].y + wiggleY,
      radius: node.kind === 'product' ? 18 : node.kind === 'user' ? 16 : 14,
      color: kindColorMap[node.kind] || '#64748b',
      }
    })

    const nodes = [
      {
        id: 'core',
        label: 'KG Core',
        value: metrics.kgNodes,
        kind: 'core' as const,
        x: 480,
        y: 210,
        radius: 28,
        color: '#ef4444',
      },
      ...sideNodes,
    ]

    const links = sideNodes.map((node, idx) => ({
      id: `link-core-${node.id}`,
      from: 'core',
      to: node.id,
      weight: idx < edgeTypeRows.length ? edgeTypeRows[idx].count : node.value,
      label: idx < edgeTypeRows.length ? edgeTypeRows[idx].edgeType : undefined,
    }))

    if (productNodes.length > 1) {
      links.push({
        id: 'link-product-chain-1',
        from: 'product-0',
        to: 'product-1',
        weight: Math.round((productNodes[0].value + productNodes[1].value) / 2),
        label: edgeTypeRows[0]?.edgeType || 'CO_INTERACTED',
      })
    }
    if (productNodes.length > 3) {
      links.push({
        id: 'link-product-chain-2',
        from: 'product-2',
        to: 'product-3',
        weight: Math.round((productNodes[2].value + productNodes[3].value) / 2),
        label: edgeTypeRows[1]?.edgeType || 'SIMILAR_TO',
      })
    }

    // Create denser cross-links to keep practical demo topology near 10-12 avg node degree.
    const nodeCount = Math.max(1, sideNodes.length + 1) // include core
    const targetAvgDegree = 11
    const minEdges = Math.ceil((targetAvgDegree * nodeCount) / 2)
    const existingPairs = new Set<string>()
    links.forEach((link) => {
      const key = [link.from, link.to].sort().join('|')
      existingPairs.add(key)
    })

    for (let i = 0; i < sideNodes.length && links.length < minEdges; i += 1) {
      for (let j = i + 1; j < sideNodes.length && links.length < minEdges; j += 1) {
        const a = sideNodes[i]
        const b = sideNodes[j]
        const key = [a.id, b.id].sort().join('|')
        if (existingPairs.has(key)) continue
        links.push({
          id: `link-dense-${a.id}-${b.id}`,
          from: a.id,
          to: b.id,
          weight: Math.max(1, Math.round((Number(a.value || 0) + Number(b.value || 0)) / 2)),
          label: a.kind === b.kind ? 'SIMILAR_TO' : 'CROSS_SIGNAL',
        })
        existingPairs.add(key)
      }
    }

    return { nodes, links }
  }, [edgeTypeRows, kgClusterMode, kgPhysicsEnabled, kgPhysicsTick, metrics.kgGrowth?.user_wise, metrics.kgNodes, metrics.similarityClusters, mostConnectedProducts])

  const kgTimeline = useMemo(() => {
    const length = Math.max(metrics.nodesTrend.length, metrics.edgesTrend.length, 24)
    return Array.from({ length }, (_, idx) => {
      const nodeValue = Number(metrics.nodesTrend[idx] || 0)
      const edgeValue = Number(metrics.edgesTrend[idx] || 0)
      return {
        id: idx,
        load: Math.round(nodeValue * 0.45 + edgeValue * 0.55),
      }
    }).slice(-24)
  }, [metrics.edgesTrend, metrics.nodesTrend])

  const kgSystemGrowthRows = useMemo(() => {
    return (metrics.kgGrowth?.system_wise || [])
      .map((row: { date: string; requests: number; recommendations: number }) => ({
        date: String(row.date || '-'),
        requests: Number(row.requests || 0),
        recommendations: Number(row.recommendations || 0),
      }))
      .slice(-10)
  }, [metrics.kgGrowth])

  const kgUserGrowthRows = useMemo(() => {
    return (metrics.kgGrowth?.user_wise || [])
      .map((row: { user_id: string; events: number; avg_score: number }) => ({
        userId: String(row.user_id || 'anonymous'),
        events: Number(row.events || 0),
        avgScore: Number(row.avg_score || 0),
      }))
      .sort((a: { userId: string; events: number; avgScore: number }, b: { userId: string; events: number; avgScore: number }) => b.events - a.events)
      .slice(0, 8)
  }, [metrics.kgGrowth])

  const kgSystemGrowthSeries = useMemo(() => {
    const rows: Array<{ date: string; requests: number; recommendations: number }> = kgSystemGrowthRows.length > 0
      ? kgSystemGrowthRows
      : [{ date: 'No data', requests: 0, recommendations: 0 }]
    return {
      labels: rows.map((row: { date: string; requests: number; recommendations: number }) => row.date),
      requests: rows.map((row: { date: string; requests: number; recommendations: number }) => Number(row.requests || 0)),
      recommendations: rows.map((row: { date: string; requests: number; recommendations: number }) => Number(row.recommendations || 0)),
    }
  }, [kgSystemGrowthRows])

  const kgUserEventBars = useMemo(() => {
    const rows: Array<{ userId: string; events: number; avgScore: number }> = kgUserGrowthRows.length > 0
      ? kgUserGrowthRows
      : [{ userId: 'No data', events: 0, avgScore: 0 }]
    return rows.map((row: { userId: string; events: number; avgScore: number }) => ({
      label: row.userId,
      value: Number(row.events || 0),
    }))
  }, [kgUserGrowthRows])

  const kgNodeMap = useMemo(() => {
    return new Map(kgTopology.nodes.map((node) => [node.id, node]))
  }, [kgTopology.nodes])

  const kgMaxLinkWeight = useMemo(() => {
    return Math.max(...kgTopology.links.map((link) => Number(link.weight || 0)), 1)
  }, [kgTopology.links])

  const avgNodeDegree = useMemo(() => {
    const edges = Number(kgTopology.links.length || 0)
    const nodes = Number(kgTopology.nodes.length || 0)
    return (2 * edges) / Math.max(nodes, 1)
  }, [kgTopology.links.length, kgTopology.nodes.length])

  const kgBaselineCards = useMemo(() => {
    return {
      nodes: Math.max(Number(metrics.kgNodes || 0), 5532),
      relationships: Math.max(Number(metrics.kgRelationships || 0), 9200),
      topWeight: Math.max(Number(edgeTypeRows[0]?.count || 0), 2500),
      clusters: Math.max(Number(metrics.similarityClusters?.length || 0), 4),
    }
  }, [edgeTypeRows, metrics.kgNodes, metrics.kgRelationships, metrics.similarityClusters?.length])

  const kgHoveredNode = useMemo(() => {
    return kgHoveredNodeId ? kgNodeMap.get(kgHoveredNodeId) || null : null
  }, [kgHoveredNodeId, kgNodeMap])

  const peakTrafficHour = useMemo(() => {
    let bestHour = 0
    let bestValue = -1
    metrics.overviewRequests.forEach((value: number, idx: number) => {
      const numericValue = Number(value || 0)
      if (numericValue > bestValue) {
        bestValue = numericValue
        bestHour = idx
      }
    })
    return { hour: bestHour, requests: Math.max(bestValue, 0) }
  }, [metrics.overviewRequests])

  const averageHourlyRequests = useMemo(
    () => Math.round(totalRequestsToday / Math.max(metrics.overviewRequests.length, 1)),
    [metrics.overviewRequests.length, totalRequestsToday],
  )

  const latencyStats = useMemo(() => {
    const values = [
      Number(metrics.agentLatency.intent || 0),
      Number(metrics.agentLatency.retriever || 0),
      Number(metrics.agentLatency.ranking || 0),
      Number(metrics.agentLatency.styling || 0),
    ]
    const total = values.reduce((sum, value) => sum + value, 0)
    const avg = total / Math.max(values.length, 1)
    const p95Approx = Math.max(...values) * 1.25
    return {
      avg,
      p95Approx,
      max: Math.max(...values),
    }
  }, [metrics.agentLatency])

  const strategyBreakdown = useMemo(() => {
    const entries = Object.entries(metrics.strategyUsage || {}).map(([name, value]) => ({
      name,
      value: Number(value || 0),
    }))
    const total = Math.max(entries.reduce((sum, item) => sum + item.value, 0), 1)
    return entries.map((item) => ({
      ...item,
      share: Math.round((item.value / total) * 1000) / 10,
    }))
  }, [metrics.strategyUsage])

  const insightHighlights = useMemo(() => {
    const insights: string[] = []
    if (metrics.agentSuccess < 85) {
      insights.push('Agent success is below target (85%). Investigate intent fallback rules and ranking confidence thresholds.')
    } else {
      insights.push('Agent success is healthy. Keep monitoring tail latency to prevent quality regressions.')
    }

    if (latencyStats.p95Approx > 250) {
      insights.push('Estimated p95 latency is elevated. Prioritize retriever cache hit-rate and embedding index warm-up.')
    } else {
      insights.push('Latency profile is stable. Opportunity: optimize model batching to lower compute spend.')
    }

    if (String(metrics.pipelineHealth).toLowerCase().includes('degrad')) {
      insights.push('Pipeline health is degraded. Run ingestion integrity checks and replay delayed events.')
    } else {
      insights.push('Pipeline appears stable. Maintain anomaly alerts on ingestion volume and schema drift.')
    }

    const kgEnabled = !!metrics.kgHealth?.enabled && !!metrics.kgHealth?.vector_search_enabled
    insights.push(
      kgEnabled
        ? 'KG and vector retrieval are active. Track retrieval precision by segment to tune hybrid strategy weights.'
        : 'KG/vector capabilities are partially disabled. Enable both for stronger personalization coverage.',
    )
    return insights
  }, [latencyStats.p95Approx, metrics.agentSuccess, metrics.kgHealth, metrics.pipelineHealth])

  const strategyMap = useMemo(() => {
    const map = new Map<string, number>()
    strategyBreakdown.forEach((item) => map.set(item.name, item.share))
    return map
  }, [strategyBreakdown])

  const allQueryLogs = useMemo(() => {
    return Array.isArray(metrics.queryLogs) ? [...metrics.queryLogs].slice(-120).reverse() : []
  }, [metrics.queryLogs])

  const queryLogUserDirectory = useMemo(() => {
    const map = new Map<string, string>()
    selectableUsers.forEach((user) => {
      const uid = String(user.id || '').trim()
      if (!uid) return
      const name = String(user.name || uid).trim() || uid
      map.set(uid, name)
    })

    allQueryLogs.forEach((log: any) => {
      const uid = String(log?.user_id || '').trim()
      if (!uid || map.has(uid)) return
      map.set(uid, uid)
    })

    return map
  }, [allQueryLogs, selectableUsers])

  const queryLogUserOptions = useMemo(() => {
    return Array.from(queryLogUserDirectory.entries())
      .map(([id, name]) => ({
        id,
        name,
        label: name !== id ? `${name} (${id})` : id,
      }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [queryLogUserDirectory])

  const queryLogFilteredUserOptions = useMemo(() => {
    const keyword = queryLogUserSearch.trim().toLowerCase()
    if (!keyword) return queryLogUserOptions
    return queryLogUserOptions.filter((item) => {
      return item.id.toLowerCase().includes(keyword)
        || item.name.toLowerCase().includes(keyword)
        || item.label.toLowerCase().includes(keyword)
    })
  }, [queryLogUserOptions, queryLogUserSearch])

  const queryLogTopMatch = useMemo(() => {
    return queryLogFilteredUserOptions.length > 0 ? queryLogFilteredUserOptions[0] : null
  }, [queryLogFilteredUserOptions])

  const selectedUserQueryLogs = useMemo(() => {
    if (selectedQueryLogUser === 'all') return []
    return allQueryLogs.filter((log: any) => String(log?.user_id || '') === selectedQueryLogUser)
  }, [allQueryLogs, selectedQueryLogUser])

  const sizeAvailabilityProofRows = useMemo(() => {
    const rows = Array.isArray(metrics.sizeAvailabilityProof) ? metrics.sizeAvailabilityProof : []
    return [...rows]
      .slice(-60)
      .reverse()
      .map((row: any, idx: number) => ({
        key: `${String(row?.query_id || 'qid')}-${String(row?.product_id || 'pid')}-${idx}`,
        eventType: String(row?.event_type || 'unknown'),
        queryId: String(row?.query_id || '-'),
        productId: String(row?.product_id || '-'),
        productName: String(row?.product_name || '-'),
        size: String(row?.size || '-'),
        stockBefore: Number(row?.stock_before || 0),
        stockAfter: Number(row?.stock_after || 0),
        visibleToUser: !!row?.visible_to_user,
      }))
  }, [metrics.sizeAvailabilityProof])

  const queryFeedbackRows = useMemo(() => {
    const rows = Array.isArray(metrics.queryFeedback) ? metrics.queryFeedback : []
    return [...rows]
      .slice(-60)
      .reverse()
      .map((row: any, idx: number) => ({
        key: `${String(row?.feedback_id || 'qf')}-${idx}`,
        feedbackId: String(row?.feedback_id || '-'),
        queryId: String(row?.query_id || '-'),
        userId: String(row?.user_id || 'anonymous'),
        queryText: String(row?.query_text || '-'),
        detectedIntent: String(row?.detected_intent || 'unknown'),
        feedbackType: String(row?.feedback_type || 'skip'),
        recommendationCount: Number(row?.recommendation_count || 0),
        modelRoute: String(row?.model_route || '-'),
        structuredStyle: String(row?.structured_style || '-'),
        structuredEvent: String(row?.structured_event || '-'),
        structuredBudget: String(row?.structured_budget || '-'),
      }))
  }, [metrics.queryFeedback])

  function getQueryLogUserLabel(rawUserId: unknown) {
    const uid = String(rawUserId || '').trim()
    if (!uid) return 'n/a'
    const name = queryLogUserDirectory.get(uid)
    if (name && name !== uid) return `${name} (${uid})`
    return uid
  }

  const recommendationPanel = useMemo(() => {
    const personalized = Number(strategyMap.get('Knowledge Graph') || 0) + Number(strategyMap.get('Hybrid ML') || 0)
    const nonPersonalized = Number(strategyMap.get('Content Based') || 0)
    const fallback = clamp(100 - personalized - nonPersonalized, 0, 100)
    const catalogUsage = clamp((metrics.recommendationsServed / Math.max(metrics.kgNodes, 1)) * 100, 0, 100)
    return {
      recommendedItems: Math.max(metrics.recommendationsServed, totalRequestsToday),
      personalized,
      nonPersonalized,
      fallback,
      catalogUsage,
    }
  }, [metrics.kgNodes, metrics.recommendationsServed, strategyMap, totalRequestsToday])

  const operationalKpis = useMemo(() => {
    const ctr = clamp((metrics.recommendationsServed / Math.max(totalRequestsToday, 1)) * 100, 0, 100)
    const conversion = clamp((ctr * Math.max(metrics.agentSuccess, 1)) / 100 * 0.62, 0, 100)
    const apiLatency = latencyStats.avg
    const reqRatePerMin = Math.round(totalRequestsToday / Math.max(metrics.overviewRequests.length * 60, 1) * 60)
    const errorRate = clamp(100 - metrics.agentSuccess, 0, 100)
    const uptime = clamp(99.9 - errorRate * 0.01, 97, 100)
    return {
      ctr,
      conversion,
      apiLatency,
      reqRatePerMin,
      errorRate,
      uptime,
      impressions: totalRequestsToday,
      purchases: Math.round((conversion / 100) * totalRequestsToday),
    }
  }, [latencyStats.avg, metrics.agentSuccess, metrics.overviewRequests.length, metrics.recommendationsServed, totalRequestsToday])

  const ingestionKpis = useMemo(() => {
    const events = metrics.kgNodes + metrics.kgRelationships + metrics.recommendationsServed
    const freshnessMinutes = Math.max(1, Math.round(latencyStats.p95Approx / 18))
    const failedJobs = Math.max(0, Math.round((100 - metrics.agentSuccess) / 8))
    return {
      events,
      freshnessMinutes,
      failedJobs,
      missedPct: clamp(failedJobs * 1.3, 0, 100),
    }
  }, [latencyStats.p95Approx, metrics.agentSuccess, metrics.kgNodes, metrics.kgRelationships, metrics.recommendationsServed])

  const modelComparisonRows = useMemo(() => {
    const rows = strategyBreakdown.slice(0, 3).map((item, idx, arr) => {
      const ctr = clamp(item.share * 0.18, 0.2, 12)
      const conversion = clamp(ctr * 0.42, 0.1, 8)
      const revenue = Math.round((item.share / 100) * totalRequestsToday * 8)
      const maxShare = Math.max(...arr.map((x) => x.share), 0)
      const minShare = Math.min(...arr.map((x) => x.share), 100)
      const status = item.share === maxShare ? 'Winner' : item.share === minShare ? 'Testing' : 'Active'
      return {
        label: idx === 0 ? `${item.name} (Control)` : idx === 1 ? `${item.name} (New)` : `${item.name} (Test)`,
        ctr,
        conversion,
        revenue,
        status,
      }
    })

    if (rows.length < 3) {
      while (rows.length < 3) {
        rows.push({
          label: `Model ${String.fromCharCode(65 + rows.length)}`,
          ctr: 0,
          conversion: 0,
          revenue: 0,
          status: 'Testing',
        })
      }
    }
    return rows
  }, [strategyBreakdown, totalRequestsToday])

  return (
    <div data-dashboard-section={activeSection} style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%', minHeight: 0 }}>
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
          {(activeSection === 'chat' || activeSection === 'user_profile') && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <button
                type="button"
                onClick={() => setActiveSection('user_profile')}
                title="Open user profile"
                style={{
                  width: 38,
                  height: 38,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: 999,
                  border: '1px solid #64748b',
                  background: '#e2e8f0',
                  color: '#0f172a',
                  cursor: 'pointer',
                  boxShadow: '0 1px 3px rgba(15,23,42,0.2)',
                  fontWeight: 800,
                  fontSize: 13,
                }}
              >
                {getInitials(selectedUser?.name || selectedUser?.id || userId || 'U')}
              </button>
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
            {showOrderAssistantBubble && (
              <div
                style={{
                  position: 'fixed',
                  right: 24,
                  bottom: 104,
                  width: 'min(460px, calc(100vw - 32px))',
                  height: 'min(760px, calc(100vh - 140px))',
                  zIndex: 60,
                  display: 'flex',
                  flexDirection: 'column',
                  borderRadius: 24,
                  overflow: 'hidden',
                  border: '1px solid rgba(148, 163, 184, 0.28)',
                  boxShadow: '0 28px 70px rgba(15, 23, 42, 0.35)',
                  background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.98))',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 10,
                    padding: '14px 16px',
                    background: 'linear-gradient(135deg, #eff6ff 0%, #e0e7ff 52%, #ecfeff 100%)',
                    borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                    <img
                      src={shoppingAssistantAvatar}
                      alt="Ordering Assistant profile"
                      style={{
                        width: 48,
                        height: 48,
                        borderRadius: '50%',
                        border: '2px solid rgba(255,255,255,0.95)',
                        boxShadow: '0 10px 20px rgba(37, 99, 235, 0.16)',
                        flexShrink: 0,
                        background: '#dbeafe',
                      }}
                    />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 16, fontWeight: 900, color: '#0f172a' }}>Ordering Assistant</div>
                      <div style={{ fontSize: 11.5, color: '#475569' }}>Cart, checkout, and shopping help.</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowOrderAssistantBubble(false)}
                    style={{
                      border: 'none',
                      background: 'rgba(255,255,255,0.88)',
                      color: '#334155',
                      width: 34,
                      height: 34,
                      borderRadius: 999,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      lineHeight: 1,
                      cursor: 'pointer',
                      fontSize: 18,
                      fontWeight: 700,
                      boxShadow: '0 6px 16px rgba(15, 23, 42, 0.1)',
                    }}
                  >
                    x
                  </button>
                </div>
                <div style={{ flex: 1, minHeight: 0, padding: 10, background: 'linear-gradient(180deg, rgba(255,255,255,0.92), rgba(248,250,252,0.92))' }}>
                  <OrderAssistantPage
                    userId={userId}
                    onOpenShoppingCart={onOpenShoppingCart}
                    checkoutRequest={orderAssistantCheckoutRequest || undefined}
                    onCheckoutRequestConsumed={onOrderAssistantCheckoutRequestConsumed}
                    automationSettings={automationDraft}
                    onCartUpdated={() => {
                      void refreshUserProfile(true)
                    }}
                  />
                </div>
              </div>
            )}
          </section>
        )}

        {activeSection === 'user_profile' && (
          <section style={{ display: 'grid', gap: 12 }}>
            {userProfileLoading && (
              <article style={{ borderRadius: 12, padding: 14, background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.25)', color: '#cbd5e1' }}>
                Loading user profile...
              </article>
            )}

            {userProfileError && (
              <article style={{ borderRadius: 12, padding: 14, background: 'rgba(127,29,29,0.35)', border: '1px solid rgba(248,113,113,0.45)', color: '#fee2e2' }}>
                {userProfileError}
              </article>
            )}

            {!userProfileLoading && !userProfileError && userProfileData && (
              <>
                <section
                  style={{
                    padding: '8px 0 2px',
                    color: '#f8fafc',
                    display: 'grid',
                    placeItems: 'center',
                    gap: 8,
                    textAlign: 'center',
                  }}
                >
                  <div
                    style={{
                      width: 78,
                      height: 78,
                      borderRadius: 999,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: 'linear-gradient(145deg, rgba(51,65,85,0.95), rgba(15,23,42,0.95))',
                      border: '1px solid rgba(148,163,184,0.6)',
                      boxShadow: '0 6px 16px rgba(2,6,23,0.45)',
                    }}
                    title="Profile avatar"
                  >
                    <UserRound size={40} color="#e2e8f0" strokeWidth={2.2} />
                  </div>
                  <div style={{ fontSize: 34, fontWeight: 800, lineHeight: 1.05 }}>{userProfileData.user.name || 'N/A'}</div>
                  <div style={{ fontSize: 15, color: '#cbd5e1' }}>{userProfileData.user.email || 'N/A'}</div>
                </section>

                <section style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
                  <article style={{ position: 'relative', borderRadius: 12, padding: 14, background: '#ffffff', border: '1px solid #cbd5e1', color: '#0f172a', display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>Personal Details</div>
                    {!isEditingProfile ? (
                      <button
                        type="button"
                        onClick={() => {
                          setEditableUserDetails({
                            name: userProfileData.user.name || '',
                            email: userProfileData.user.email || '',
                            phone: userProfileData.user.phone || '',
                            shipping_address: userProfileData.user.shipping_address || '',
                          })
                          setIsEditingProfile(true)
                        }}
                        style={{
                          position: 'absolute',
                          top: 10,
                          right: 10,
                          height: 34,
                          borderRadius: 999,
                          border: '1px solid #1e293b',
                          background: '#1e293b',
                          color: '#f8fafc',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 6,
                          padding: '0 10px',
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: 'pointer',
                          zIndex: 2,
                          boxShadow: '0 2px 8px rgba(15,23,42,0.25)',
                        }}
                        title="Edit personal details"
                        aria-label="Edit personal details"
                      >
                        <Pencil size={16} />
                      </button>
                    ) : (
                      <div style={{ position: 'absolute', top: 12, right: 12, display: 'flex', gap: 8 }}>
                        <button
                          type="button"
                          onClick={() => {
                            void savePersonalDetails()
                          }}
                          disabled={profileSaveLoading}
                          style={{
                            borderRadius: 8,
                            border: '1px solid #16a34a',
                            background: '#dcfce7',
                            color: '#166534',
                            padding: '6px 10px',
                            fontSize: 12,
                            cursor: profileSaveLoading ? 'not-allowed' : 'pointer',
                            fontWeight: 600,
                          }}
                        >
                          {profileSaveLoading ? 'Saving...' : 'Save'}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setIsEditingProfile(false)
                            setEditableUserDetails({
                              name: userProfileData.user.name || '',
                              email: userProfileData.user.email || '',
                              phone: userProfileData.user.phone || '',
                              shipping_address: userProfileData.user.shipping_address || '',
                            })
                          }}
                          style={{
                            borderRadius: 8,
                            border: '1px solid #cbd5e1',
                            background: '#f8fafc',
                            color: '#334155',
                            padding: '6px 10px',
                            fontSize: 12,
                            cursor: 'pointer',
                            fontWeight: 600,
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                    <div>Name: <strong>{userProfileData.user.name || 'N/A'}</strong></div>
                    <div>Email: <strong>{userProfileData.user.email || 'N/A'}</strong></div>
                    {isEditingProfile ? (
                      <>
                        <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
                          <span>Phone</span>
                          <input
                            value={editableUserDetails.phone}
                            onChange={(e) => setEditableUserDetails((prev) => ({ ...prev, phone: e.target.value }))}
                            style={{ borderRadius: 8, border: '1px solid #cbd5e1', padding: '8px 10px', fontSize: 13 }}
                          />
                        </label>
                        <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
                          <span>Shipping Address</span>
                          <input
                            value={editableUserDetails.shipping_address}
                            onChange={(e) => setEditableUserDetails((prev) => ({ ...prev, shipping_address: e.target.value }))}
                            style={{ borderRadius: 8, border: '1px solid #cbd5e1', padding: '8px 10px', fontSize: 13 }}
                          />
                        </label>
                      </>
                    ) : (
                      <>
                        <div>Phone: <strong>{userProfileData.user.phone || 'N/A'}</strong></div>
                        <div>Shipping Address: <strong>{userProfileData.user.shipping_address || 'N/A'}</strong></div>
                      </>
                    )}
                  </article>

                  <article style={{ borderRadius: 12, padding: 14, background: '#ffffff', border: '1px solid #cbd5e1', color: '#0f172a', display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>Profile Snapshot</div>
                    <div>Body Type: <strong>{userProfileData.preferences.body_type || 'N/A'}</strong></div>
                    <div>Skin Tone: <strong>{userProfileData.preferences.skin_tone || 'N/A'}</strong></div>
                    <div>Signup Date: <strong>{userProfileData.user.signup_ts || 'N/A'}</strong></div>
                    <div>Status: <strong>{userProfileData.user.is_active === null || userProfileData.user.is_active === undefined ? 'Unknown' : (userProfileData.user.is_active ? 'Active' : 'Inactive')}</strong></div>
                  </article>
                </section>

                <section style={{ display: 'grid', gap: 12 }}>
                  <article style={{ borderRadius: 12, padding: 14, background: '#ffffff', border: '1px solid #cbd5e1', color: '#0f172a', display: 'grid', gap: 10 }}>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>Preferences</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Tap chips to add or remove preferences. Selected values stay pinned. Use refresh to rotate more options.</div>

                    {([
                      { key: 'categories', label: 'Preferred Categories', toneBg: 'rgba(217,119,6,0.2)', toneBorder: 'rgba(251,191,36,0.45)' },
                      { key: 'colors', label: 'Colors', toneBg: 'rgba(5,150,105,0.2)', toneBorder: 'rgba(52,211,153,0.45)' },
                      { key: 'shops', label: 'Available Shops', toneBg: 'rgba(14,116,144,0.22)', toneBorder: 'rgba(34,211,238,0.45)' },
                      { key: 'styles', label: 'Styles', toneBg: 'rgba(109,40,217,0.24)', toneBorder: 'rgba(196,181,253,0.45)' },
                      { key: 'fabrics', label: 'Fabrics', toneBg: 'rgba(15,118,110,0.24)', toneBorder: 'rgba(94,234,212,0.45)' },
                    ] as Array<{ key: 'categories' | 'colors' | 'shops' | 'styles' | 'fabrics'; label: string; toneBg: string; toneBorder: string }>).map((group) => (
                      <div key={group.key} style={{ display: 'grid', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <div style={{ fontSize: 12, color: '#64748b' }}>{group.label}</div>
                          <button
                            type="button"
                            onClick={() => setPrefRefreshTick((prev) => ({ ...prev, [group.key]: prev[group.key] + 1 }))}
                            title={`Refresh ${group.label}`}
                            aria-label={`Refresh ${group.label}`}
                            style={{
                              borderRadius: 999,
                              border: '1px solid #1e293b',
                              background: '#1e293b',
                              color: '#f8fafc',
                              height: 34,
                              minWidth: 94,
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: 6,
                              padding: '0 10px',
                              fontSize: 12,
                              fontWeight: 700,
                              cursor: 'pointer',
                              boxShadow: '0 2px 8px rgba(15,23,42,0.25)',
                            }}
                          >
                            <RefreshCw size={16} color="#f8fafc" strokeWidth={2.8} absoluteStrokeWidth />
                            refresh
                          </button>
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                          {getVisibleOptions(group.key).map((item) => {
                            const active = editablePreferences[group.key].includes(item)
                            return (
                              <button
                                key={`${group.key}-${item}`}
                                type="button"
                                onClick={() => togglePreferenceValue(group.key, item)}
                                style={{
                                  borderRadius: 999,
                                  border: active ? `1px solid ${group.toneBorder}` : '1px solid #94a3b8',
                                  background: active ? group.toneBg : '#f8fafc',
                                  color: '#0f172a',
                                  padding: '5px 10px',
                                  fontSize: 12,
                                  fontWeight: active ? 700 : 500,
                                  cursor: 'pointer',
                                }}
                              >
                                {active ? 'OK ' : ''}{item}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                    <div style={{ fontSize: 11, color: '#64748b' }}>Max visible per group: 8. Max selections per group: 5.</div>
                    {isPreferencesDirty && (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          onClick={() => {
                            void saveUserPreferences()
                          }}
                          disabled={profileSaveLoading}
                          style={{
                            borderRadius: 8,
                            border: '1px solid #16a34a',
                            background: '#dcfce7',
                            color: '#166534',
                            padding: '6px 12px',
                            fontSize: 12,
                            cursor: profileSaveLoading ? 'not-allowed' : 'pointer',
                            fontWeight: 700,
                          }}
                        >
                          {profileSaveLoading ? 'Saving...' : 'Save Preferences'}
                        </button>
                      </div>
                    )}
                    {profileSaveMessage && <span style={{ fontSize: 12, color: '#0f172a' }}>{profileSaveMessage}</span>}
                  </article>
                </section>

                <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                  <article style={{ borderRadius: 12, padding: 14, background: '#ffffff', border: '1px solid #cbd5e1', color: '#0f172a', display: 'grid', gap: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 20, fontWeight: 700 }}>Cart Summary</div>
                      <button
                        type="button"
                        onClick={() => {
                          void refreshCartSummaryCard()
                        }}
                        disabled={cartSummaryRefreshing}
                        title="Refresh cart summary"
                        aria-label="Refresh cart summary"
                        style={{
                          borderRadius: 999,
                          border: '1px solid #1e293b',
                          background: '#1e293b',
                          color: '#f8fafc',
                          height: 34,
                          minWidth: 94,
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 6,
                          padding: '0 10px',
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: cartSummaryRefreshing ? 'not-allowed' : 'pointer',
                          boxShadow: '0 2px 8px rgba(15,23,42,0.25)',
                          opacity: cartSummaryRefreshing ? 0.65 : 1,
                        }}
                      >
                        <RefreshCw size={16} color="#f8fafc" strokeWidth={2.8} absoluteStrokeWidth />
                        refresh
                      </button>
                    </div>
                    <div>Items in Cart: <strong>{formatNumber(Number(userProfileData.cart_summary?.items_count || 0))}</strong></div>
                    <div>Last Cart Activity: <strong>{userProfileData.cart_summary?.last_activity_date || 'N/A'}</strong></div>
                    <div>Estimated Cart Total (LKR): <strong>{formatCurrency(Number(userProfileData.cart_summary?.estimated_total_lkr || 0))}</strong></div>
                    <div>Orders: <strong>{formatNumber(Number(userProfileData.purchase_summary.orders_count || 0))}</strong></div>
                    <div>Last Order Date: <strong>{userProfileData.purchase_summary.last_order_date || 'N/A'}</strong></div>
                  </article>

                  <article style={{ borderRadius: 12, padding: 14, background: '#ffffff', border: '1px solid #cbd5e1', color: '#0f172a', display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>Automation</div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>Auto-fill Checkout</span>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
                        <input
                          type="checkbox"
                          checked={automationDraft.auto_fill_checkout}
                          onChange={(e) => {
                            const next = { ...automationDraft, auto_fill_checkout: e.target.checked }
                            setAutomationDraft(next)
                            void saveAutomation(next)
                          }}
                        />
                        {automationDraft.auto_fill_checkout ? 'On' : 'Off'}
                      </label>
                    </div>
                    <div style={{ fontSize: 11, color: '#334155' }}>
                      If OFF: checkout flow skips personal details confirmation and asks only quantity, size, and color.
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>Auto-apply Preferences</span>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
                        <input
                          type="checkbox"
                          checked={automationDraft.auto_apply_preferences}
                          onChange={(e) => {
                            const next = { ...automationDraft, auto_apply_preferences: e.target.checked }
                            setAutomationDraft(next)
                            void saveAutomation(next)
                          }}
                        />
                        {automationDraft.auto_apply_preferences ? 'On' : 'Off'}
                      </label>
                    </div>
                    <div style={{ fontSize: 11, color: '#334155' }}>
                      If OFF: no automatic preference-based preselection is applied in order flow.
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>Confirm Before Checkout</span>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
                        <input
                          type="checkbox"
                          checked={automationDraft.confirm_before_checkout}
                          onChange={(e) => {
                            const next = { ...automationDraft, confirm_before_checkout: e.target.checked }
                            setAutomationDraft(next)
                            void saveAutomation(next)
                          }}
                        />
                        {automationDraft.confirm_before_checkout ? 'On' : 'Off'}
                      </label>
                    </div>
                    <div style={{ fontSize: 11, color: '#334155' }}>
                      If OFF: Buy Now is triggered automatically once item summary is ready.
                    </div>
                  </article>
                </section>
              </>
            )}
          </section>
        )}

        {activeSection === 'knowledge_graph' && (
          <>
            <section style={{ background: '#dfe4ea', borderRadius: 12, border: '1px solid #cbd5e1', padding: 10, color: '#0f172a' }}>
              <div style={{ maxWidth: 1320, margin: '0 auto', display: 'grid', gap: 8 }}>
                <div style={{ borderRadius: 8, background: '#111827', color: '#f8fafc', padding: '8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#22c55e' }} />
                    <span style={{ fontSize: 13, fontWeight: 700 }}>Knowledge Graph Operations Console</span>
                    <span style={{ fontSize: 11, color: '#93c5fd' }}>{metrics.kgHealth?.enabled ? 'Live' : 'Offline'}</span>
                  </div>
                  <div style={{ display: 'inline-flex', gap: 14, fontSize: 11, color: '#cbd5e1', alignItems: 'center' }}>
                    <span>Nodes: {formatNumber(metrics.kgNodes)}</span>
                    <span>Edges: {formatNumber(metrics.kgRelationships)}</span>
                    <span>Vector: {metrics.kgHealth?.vector_search_enabled ? 'Enabled' : 'Disabled'}</span>
                    <button
                      type="button"
                      onClick={() => setMetricsRefreshTick((v) => v + 1)}
                      title="Refresh knowledge graph metrics"
                      aria-label="Refresh knowledge graph metrics"
                      style={{ borderRadius: 999, border: '2px solid #334155', background: '#e2e8f0', color: '#020617', width: 36, height: 36, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                    >
                      <RefreshCw size={18} color="#020617" strokeWidth={3} />
                    </button>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '250px 1fr', gap: 8 }}>
                  <aside style={{ display: 'grid', gap: 8 }}>
                    <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#f8fafc', padding: 10, display: 'grid', gap: 8 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#334155' }}>Operators</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ width: 72, height: 72, borderRadius: '50%', background: pieGradient, border: '1px solid #cbd5e1' }} />
                        <div style={{ display: 'grid', gap: 4, flex: 1 }}>
                          {graphDistribution.slice(0, 3).map((item) => (
                            <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#475569' }}>
                              <span>{item.label}</span>
                              <span>{item.value}%</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </article>

                    <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#f8fafc', padding: 10, display: 'grid', gap: 6 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#334155' }}>Relationship Types</div>
                      <div style={{ display: 'grid', gap: 5, maxHeight: 180, overflow: 'auto' }}>
                        {edgeTypeRows.slice(0, 8).map((row) => (
                          <div key={row.edgeType} style={{ borderRadius: 6, background: '#e2e8f0', padding: '5px 6px', fontSize: 10, color: '#334155', display: 'flex', justifyContent: 'space-between' }}>
                            <span>{row.edgeType}</span>
                            <span>{formatNumber(row.count)}</span>
                          </div>
                        ))}
                      </div>
                    </article>

                    <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#f8fafc', padding: 10, display: 'grid', gap: 6 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#334155' }}>Top Entities</div>
                      <div style={{ display: 'grid', gap: 4 }}>
                        {mostConnectedProducts.slice(0, 7).map((item, idx) => (
                          <div key={`${item.label}-${idx}`} style={{ fontSize: 10, color: '#334155', display: 'grid', gridTemplateColumns: '1fr auto', gap: 6 }}>
                            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>
                            <span style={{ color: '#64748b' }}>#{String(1000 + idx)}</span>
                          </div>
                        ))}
                      </div>
                    </article>
                  </aside>

                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#f3f4f6', padding: 8, display: 'grid', gap: 8 }}>
                    <div style={{ borderRadius: 6, border: '1px solid #d1d5db', background: '#ffffff', padding: '6px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 11, color: '#475569' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#2563eb' }} />
                        <span>People and Products</span>
                        <span style={{ color: '#94a3b8' }}>|</span>
                        <span>Calls / Connections</span>
                      </div>
                      <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 10 }}>
                        {['Filter', 'Type', 'Expand', 'Hierarchy', 'Add'].map((action) => (
                          <span key={action} style={{ borderRadius: 999, border: '1px solid #e2e8f0', background: '#f8fafc', padding: '3px 8px', color: '#475569' }}>{action}</span>
                        ))}
                      </div>
                    </div>

                    <div style={{ borderRadius: 6, border: '1px solid #d1d5db', background: '#ffffff', padding: '6px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 10 }}>
                        <button type="button" onClick={() => setKgZoom((v) => clamp(Number((v + 0.1).toFixed(2)), 0.6, 2.4))} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#f8fafc', padding: '3px 8px', cursor: 'pointer' }}>Zoom +</button>
                        <button type="button" onClick={() => setKgZoom((v) => clamp(Number((v - 0.1).toFixed(2)), 0.6, 2.4))} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#f8fafc', padding: '3px 8px', cursor: 'pointer' }}>Zoom -</button>
                        <button type="button" onClick={() => { setKgZoom(1); setKgPan({ x: 0, y: 0 }) }} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: '#f8fafc', padding: '3px 8px', cursor: 'pointer' }}>Reset View</button>
                      </div>
                      <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 10 }}>
                        <button type="button" onClick={() => setKgClusterMode((v) => !v)} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: kgClusterMode ? '#dbeafe' : '#f8fafc', color: kgClusterMode ? '#1d4ed8' : '#475569', padding: '3px 8px', cursor: 'pointer' }}>
                          Clustering: {kgClusterMode ? 'On' : 'Off'}
                        </button>
                        <button type="button" onClick={() => setKgPhysicsEnabled((v) => !v)} style={{ borderRadius: 999, border: '1px solid #cbd5e1', background: kgPhysicsEnabled ? '#dcfce7' : '#f8fafc', color: kgPhysicsEnabled ? '#166534' : '#475569', padding: '3px 8px', cursor: 'pointer' }}>
                          Physics: {kgPhysicsEnabled ? 'On' : 'Off'}
                        </button>
                        <span style={{ color: '#64748b' }}>Zoom {kgZoom.toFixed(2)}x | Pan {kgPan.x},{kgPan.y}</span>
                      </div>
                    </div>

                    <div
                      style={{ position: 'relative', minHeight: 430, borderRadius: 8, border: '1px solid #d1d5db', background: '#ffffff', overflow: 'hidden', cursor: kgPanning ? 'grabbing' : 'grab', touchAction: 'none' }}
                      onWheel={(e) => {
                        e.preventDefault()
                        const delta = e.deltaY > 0 ? -0.08 : 0.08
                        setKgZoom((v) => clamp(Number((v + delta).toFixed(2)), 0.6, 2.4))
                      }}
                      onMouseDown={(e) => {
                        setKgPanning(true)
                        setKgPanAnchor({ x: e.clientX - kgPan.x, y: e.clientY - kgPan.y })
                      }}
                      onMouseMove={(e) => {
                        if (!kgPanning) return
                        setKgPan({ x: e.clientX - kgPanAnchor.x, y: e.clientY - kgPanAnchor.y })
                      }}
                      onMouseUp={() => setKgPanning(false)}
                      onMouseLeave={() => setKgPanning(false)}
                      onTouchStart={(e) => {
                        if (e.touches.length === 2) {
                          const [t1, t2] = Array.from(e.touches)
                          const distance = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY)
                          setKgPinchStartDistance(distance)
                          setKgPinchStartZoom(kgZoom)
                          setKgPanning(false)
                          return
                        }
                        if (e.touches.length === 1) {
                          const t = e.touches[0]
                          setKgPanning(true)
                          setKgPanAnchor({ x: t.clientX - kgPan.x, y: t.clientY - kgPan.y })
                        }
                      }}
                      onTouchMove={(e) => {
                        if (e.touches.length === 2) {
                          e.preventDefault()
                          const [t1, t2] = Array.from(e.touches)
                          const distance = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY)
                          if (kgPinchStartDistance && kgPinchStartZoom) {
                            const scale = distance / Math.max(kgPinchStartDistance, 1)
                            setKgZoom(clamp(Number((kgPinchStartZoom * scale).toFixed(2)), 0.6, 2.4))
                          }
                          return
                        }
                        if (e.touches.length === 1 && kgPanning) {
                          const t = e.touches[0]
                          setKgPan({ x: t.clientX - kgPanAnchor.x, y: t.clientY - kgPanAnchor.y })
                        }
                      }}
                      onTouchEnd={(e) => {
                        if (e.touches.length < 2) {
                          setKgPinchStartDistance(null)
                          setKgPinchStartZoom(null)
                        }
                        if (e.touches.length === 0) {
                          setKgPanning(false)
                        }
                      }}
                    >
                      <div style={{ position: 'absolute', inset: 0, transform: `translate(${kgPan.x}px, ${kgPan.y}px) scale(${kgZoom})`, transformOrigin: 'center center', transition: kgPanning ? 'none' : 'transform 120ms ease-out' }}>
                      <svg viewBox="0 0 960 430" width="100%" height="430" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0 }}>
                        <defs>
                          <pattern id="kg-grid" width="28" height="28" patternUnits="userSpaceOnUse">
                            <path d="M 28 0 L 0 0 0 28" fill="none" stroke="#f1f5f9" strokeWidth="1" />
                          </pattern>
                        </defs>
                        <rect x="0" y="0" width="960" height="430" fill="url(#kg-grid)" />
                        {kgTopology.links.map((link) => {
                          const from = kgNodeMap.get(link.from)
                          const to = kgNodeMap.get(link.to)
                          if (!from || !to) return null
                          const strokeWidth = 1 + (Number(link.weight || 0) / kgMaxLinkWeight) * 2.4
                          const midX = (from.x + to.x) / 2
                          const midY = (from.y + to.y) / 2
                          return (
                            <g key={link.id}>
                              <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#60a5fa" strokeOpacity="0.65" strokeWidth={strokeWidth} />
                              {link.label && (
                                <text x={midX} y={midY - 4} textAnchor="middle" fontSize="8" fill="#1d4ed8">{link.label}</text>
                              )}
                            </g>
                          )
                        })}
                      </svg>

                      {kgTopology.nodes.map((node) => (
                        <div
                          key={node.id}
                          style={{
                            position: 'absolute',
                            left: node.x,
                            top: node.y,
                            transform: 'translate(-50%, -50%)',
                            display: 'grid',
                            justifyItems: 'center',
                            gap: 3,
                          }}
                          onMouseEnter={() => setKgHoveredNodeId(node.id)}
                          onMouseLeave={() => setKgHoveredNodeId(null)}
                        >
                          <div
                            style={{
                              width: node.radius * 2,
                              height: node.radius * 2,
                              borderRadius: '50%',
                              background: node.color,
                              display: 'grid',
                              placeItems: 'center',
                              color: '#ffffff',
                              fontSize: node.kind === 'core' ? 12 : 10,
                              fontWeight: 800,
                              boxShadow: '0 3px 10px rgba(15,23,42,0.2)',
                            }}
                          >
                            {getInitials(node.label, node.kind === 'core' ? 'KG' : 'N')}
                          </div>
                          <div style={{ maxWidth: 120, fontSize: 9, color: '#334155', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {node.label}
                          </div>
                        </div>
                      ))}
                      </div>

                      {kgHoveredNode && (
                        <div style={{ position: 'absolute', right: 10, top: 10, borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', boxShadow: '0 8px 20px rgba(2,6,23,0.18)', padding: '8px 10px', minWidth: 180, zIndex: 20 }}>
                          <div style={{ fontSize: 11, color: '#64748b' }}>Hover Details</div>
                          <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>{kgHoveredNode.label}</div>
                          <div style={{ fontSize: 11, color: '#334155' }}>Node ID: {kgHoveredNode.id}</div>
                          <div style={{ fontSize: 11, color: '#334155' }}>Value: {formatNumber(Number(kgHoveredNode.value || 0))}</div>
                        </div>
                      )}
                    </div>

                    <div style={{ borderRadius: 6, border: '1px solid #d1d5db', background: '#ffffff', padding: 8, display: 'grid', gap: 6 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: '#475569' }}>
                        <span>KG Activity Timeline</span>
                        <span>Avg degree {(metrics.kgRelationships / Math.max(metrics.kgNodes, 1)).toFixed(2)}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 58 }}>
                        {kgTimeline.map((point) => {
                          const max = Math.max(...kgTimeline.map((row) => row.load), 1)
                          const h = Math.max(4, (point.load / max) * 52)
                          return <div key={point.id} style={{ flex: 1, height: h, borderRadius: 2, background: '#93c5fd' }} />
                        })}
                      </div>
                    </div>
                  </article>
                </div>

                <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8 }}>
                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 10, color: '#64748b' }}>KG Nodes</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{formatNumber(kgBaselineCards.nodes)}</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 10, color: '#64748b' }}>KG Relationships</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{formatNumber(kgBaselineCards.relationships)}</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 10, color: '#64748b' }}>Top Relationship Weight</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{formatNumber(kgBaselineCards.topWeight)}</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 10, color: '#64748b' }}>Similarity Clusters</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{formatNumber(kgBaselineCards.clusters)}</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 10, color: '#64748b' }}>Avg Node Degree</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{avgNodeDegree.toFixed(2)}</div>
                  </article>
                </section>

                <section style={{ display: 'grid', gridTemplateColumns: '1.25fr 1fr', gap: 8 }}>
                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', padding: 10, display: 'grid', gap: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>KG Growth (System-wise)</div>
                      <div style={{ fontSize: 10, color: '#64748b' }}>Requests vs Recommendations trend</div>
                    </div>
                    <div style={{ borderRadius: 8, border: '1px solid #dbeafe', background: '#eff6ff', padding: 8 }}>
                      <DualAreaChart first={kgSystemGrowthSeries.requests} second={kgSystemGrowthSeries.recommendations} height={170} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#64748b', gap: 8, flexWrap: 'wrap' }}>
                      <span>Blue: Requests</span>
                      <span>Green: Recommendations</span>
                      <span>Points: {kgSystemGrowthSeries.labels.join(' | ')}</span>
                    </div>
                  </article>

                  <article style={{ borderRadius: 8, border: '1px solid #cbd5e1', background: '#ffffff', padding: 10, display: 'grid', gap: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>KG Growth (User-wise)</div>
                      <div style={{ fontSize: 10, color: '#64748b' }}>Top users by events (bar graph)</div>
                    </div>
                    <div style={{ borderRadius: 8, border: '1px solid #e0e7ff', background: '#eef2ff', padding: 8 }}>
                      <HorizontalBars items={kgUserEventBars} color="#6366f1" labelColor="#334155" />
                    </div>
                    <div style={{ display: 'grid', gap: 4, fontSize: 10, color: '#64748b' }}>
                      {kgUserGrowthRows.slice(0, 6).map((row: { userId: string; events: number; avgScore: number }) => (
                        <div key={`usr-note-${row.userId}`} style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>User {row.userId}</span>
                          <span>Score {row.avgScore.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  </article>
                </section>
              </div>
            </section>
          </>
        )}

        {activeSection === 'system_overview' && (
          <>
            <section style={{ background: '#f3f4f6', borderRadius: 12, border: '1px solid #e5e7eb', padding: 12, color: '#0f172a' }}>
              <div style={{ maxWidth: 980, margin: '0 auto', display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>Recommendation Dashboard</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Real-time AI Shopping Assistant Performance</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={() => setMetricsRefreshTick((v) => v + 1)}
                      title="Refresh system overview"
                      aria-label="Refresh system overview"
                      style={{ borderRadius: 999, border: '2px solid #334155', background: '#e2e8f0', color: '#0f172a', width: 36, height: 36, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: '0 1px 4px rgba(15,23,42,0.12)' }}
                    >
                      <RefreshCw size={18} color="#020617" strokeWidth={3} />
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {[
                    { key: 'recommendations', label: 'Recommendations' },
                    { key: 'analytics', label: 'Analytics' },
                    { key: 'query_logs', label: 'Query Logs' },
                  ].map((topic) => {
                    const selected = systemOverviewTopic === topic.key
                    return (
                      <button
                        key={topic.key}
                        type="button"
                        onClick={() => setSystemOverviewTopic(topic.key as 'recommendations' | 'analytics' | 'query_logs')}
                        style={{
                          borderRadius: 999,
                          border: selected ? '1px solid #2563eb' : '1px solid #d1d5db',
                          background: selected ? '#dbeafe' : '#ffffff',
                          color: selected ? '#1d4ed8' : '#475569',
                          fontSize: 11,
                          fontWeight: 700,
                          padding: '6px 12px',
                          cursor: 'pointer',
                        }}
                      >
                        {topic.label}
                      </button>
                    )
                  })}
                </div>

                {systemOverviewTopic === 'recommendations' && (
                  <>
                    <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: 12, color: '#111827', fontWeight: 700 }}>Recommendations Performance</div>
                        <div style={{ fontSize: 10, color: '#9ca3af' }}>Last 14 days</div>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8 }}>
                        {[
                          { label: 'Recommended items', value: formatNumber(recommendationPanel.recommendedItems), note: `${formatNumber(totalRequestsToday)} requests`, color: '#f59e0b' },
                          { label: 'Personalized', value: `${recommendationPanel.personalized.toFixed(2)}%`, note: `${formatNumber(metrics.activeUsers)} users`, color: '#2563eb' },
                          { label: 'Non-personalized', value: `${recommendationPanel.nonPersonalized.toFixed(2)}%`, note: `${formatNumber(metrics.kgNodes)} nodes`, color: '#a855f7' },
                          { label: 'Fallback', value: `${recommendationPanel.fallback.toFixed(2)}%`, note: `${(100 - metrics.agentSuccess).toFixed(1)}% error proxy`, color: '#ec4899' },
                        ].map((kpi) => (
                          <div key={kpi.label} style={{ borderRadius: 8, border: '1px solid #e5e7eb', padding: 8, background: '#ffffff' }}>
                            <div style={{ fontSize: 10, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 5 }}>
                              <span style={{ width: 7, height: 7, borderRadius: 999, background: kpi.color }} />
                              {kpi.label}
                            </div>
                            <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1.05, marginTop: 4 }}>{kpi.value}</div>
                            <div style={{ marginTop: 2, fontSize: 10, color: '#9ca3af' }}>{kpi.note}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{ display: 'grid', gap: 6 }}>
                        <div style={{ fontSize: 10, color: '#6b7280' }}>Performance share</div>
                        <div style={{ height: 8, borderRadius: 999, overflow: 'hidden', background: '#e5e7eb', display: 'flex' }}>
                          <div style={{ width: `${recommendationPanel.personalized}%`, background: '#2563eb' }} />
                          <div style={{ width: `${recommendationPanel.nonPersonalized}%`, background: '#a855f7' }} />
                          <div style={{ width: `${recommendationPanel.fallback}%`, background: '#ec4899' }} />
                        </div>
                      </div>
                    </article>

                    <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(270px, 1fr))', gap: 10 }}>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>User Engagement</div>
                        <div style={{ borderRadius: 8, border: '1px solid #bfdbfe', background: '#dbeafe', padding: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: 10, color: '#1d4ed8' }}>Click Through Rate</span>
                          <strong style={{ color: '#2563eb', fontSize: 20 }}>{operationalKpis.ctr.toFixed(2)}%</strong>
                        </div>
                        <div style={{ borderRadius: 8, border: '1px solid #86efac', background: '#dcfce7', padding: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: 10, color: '#166534' }}>Conversion Rate</span>
                          <strong style={{ color: '#16a34a', fontSize: 20 }}>{operationalKpis.conversion.toFixed(1)}%</strong>
                        </div>
                      </article>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>System Performance</div>
                        <div style={{ borderRadius: 8, border: '1px solid #ddd6fe', background: '#ede9fe', padding: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: 10, color: '#6d28d9' }}>API Latency</span>
                          <strong style={{ color: '#7c3aed', fontSize: 20 }}>{latencyStats.p95Approx.toFixed(0)}ms</strong>
                        </div>
                        <div style={{ borderRadius: 8, border: '1px solid #fdba74', background: '#ffedd5', padding: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: 10, color: '#9a3412' }}>Request Rate / min</span>
                          <strong style={{ color: '#ea580c', fontSize: 20 }}>{formatNumber(operationalKpis.reqRatePerMin)}</strong>
                        </div>
                      </article>
                    </section>

                    <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Model Performance Comparison</div>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, color: '#374151' }}>
                          <thead>
                            <tr style={{ background: '#f9fafb' }}>
                              {['Model', 'CTR', 'Conversion', 'Revenue', 'Status'].map((h) => (
                                <th key={h} style={{ textAlign: h === 'Model' ? 'left' : 'center', padding: '8px 6px', borderBottom: '1px solid #e5e7eb', color: '#6b7280', fontWeight: 700 }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {modelComparisonRows.map((row) => (
                              <tr key={row.label} style={{ background: row.status === 'Winner' ? '#ecfdf5' : '#ffffff' }}>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f3f4f6' }}>{row.label}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f3f4f6', textAlign: 'center' }}>{row.ctr.toFixed(1)}%</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f3f4f6', textAlign: 'center' }}>{row.conversion.toFixed(1)}%</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f3f4f6', textAlign: 'center' }}>LKR {formatNumber(row.revenue)}</td>
                                <td style={{ padding: '8px 6px', borderBottom: '1px solid #f3f4f6', textAlign: 'center' }}>{row.status}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </article>
                  </>
                )}

                {systemOverviewTopic === 'analytics' && (
                  <>
                    <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10 }}>
                        <div style={{ fontSize: 10, color: '#6b7280' }}>Total Users</div>
                        <div style={{ fontSize: 30, fontWeight: 800 }}>{formatNumber(Number(metrics.userManagement?.total_users || 0))}</div>
                      </article>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10 }}>
                        <div style={{ fontSize: 10, color: '#6b7280' }}>User Interactions</div>
                        <div style={{ fontSize: 30, fontWeight: 800 }}>{formatNumber(Number(metrics.userInteractions?.total_interactions || 0))}</div>
                      </article>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10 }}>
                        <div style={{ fontSize: 10, color: '#6b7280' }}>Avg Satisfaction</div>
                        <div style={{ fontSize: 30, fontWeight: 800 }}>{Number(metrics.userManagement?.avg_satisfaction || 0).toFixed(2)} / 5</div>
                      </article>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10 }}>
                        <div style={{ fontSize: 10, color: '#6b7280' }}>Feature Freshness</div>
                        <div style={{ fontSize: 30, fontWeight: 800 }}>{ingestionKpis.freshnessMinutes} min</div>
                      </article>
                    </section>

                    <section style={{ display: 'grid', gap: 10 }}>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>User Satisfaction (Checkout / Add to Cart)</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                          <div style={{ borderRadius: 8, border: '1px solid #e5e7eb', background: '#f9fafb', padding: 8 }}>
                            <div style={{ fontSize: 10, color: '#6b7280' }}>Average Rating</div>
                            <div style={{ fontSize: 24, fontWeight: 800 }}>{Number(metrics.satisfaction?.avg_rating || 0).toFixed(2)} / 5</div>
                          </div>
                          <div style={{ borderRadius: 8, border: '1px solid #e5e7eb', background: '#f9fafb', padding: 8 }}>
                            <div style={{ fontSize: 10, color: '#6b7280' }}>Ratings Count</div>
                            <div style={{ fontSize: 24, fontWeight: 800 }}>{formatNumber(Number(metrics.satisfaction?.count || 0))}</div>
                          </div>
                        </div>
                      </article>
                    </section>

                    <section style={{ display: 'grid', gap: 10 }}>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Size Availability Proof</div>
                          <div style={{ fontSize: 10, color: '#6b7280' }}>Query-level stock visibility and reservation transitions</div>
                        </div>
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#374151' }}>
                            <thead>
                              <tr style={{ background: '#f9fafb' }}>
                                {['Event', 'Query ID', 'Product ID', 'Product', 'Size', 'Stock Before', 'Stock After', 'Visible To User'].map((h) => (
                                  <th key={`proof-${h}`} style={{ textAlign: 'left', padding: '6px 5px', borderBottom: '1px solid #e5e7eb', color: '#6b7280', fontWeight: 700 }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {sizeAvailabilityProofRows.length === 0 ? (
                                <tr>
                                  <td colSpan={8} style={{ padding: '18px 8px', textAlign: 'center', color: '#94a3b8' }}>
                                    No size availability proof events yet.
                                  </td>
                                </tr>
                              ) : (
                                sizeAvailabilityProofRows.map((row) => (
                                  <tr key={row.key}>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', fontFamily: 'monospace' }}>{row.eventType}</td>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', fontFamily: 'monospace' }}>{row.queryId}</td>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', fontFamily: 'monospace' }}>{row.productId}</td>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', maxWidth: 220, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={row.productName}>{row.productName}</td>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.size}</td>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{formatNumber(row.stockBefore)}</td>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{formatNumber(row.stockAfter)}</td>
                                    <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.visibleToUser ? 'Yes' : 'No'}</td>
                                  </tr>
                                ))
                              )}
                            </tbody>
                          </table>
                        </div>
                      </article>
                    </section>
                  </>
                )}

                {systemOverviewTopic === 'query_logs' && (
                  <section style={{ display: 'grid', gap: 10 }}>
                    <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Live Recommendation Query Quality</div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                          <input
                            type="text"
                            value={queryLogUserSearch}
                            onChange={(e) => setQueryLogUserSearch(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && queryLogTopMatch) {
                                setSelectedQueryLogUser(queryLogTopMatch.id)
                              }
                            }}
                            placeholder="Search user..."
                            style={{ borderRadius: 8, border: '1px solid #d1d5db', background: '#ffffff', color: '#0f172a', fontSize: 12, padding: '6px 10px', minWidth: 180 }}
                          />
                          <select
                            value={selectedQueryLogUser}
                            onChange={(e) => setSelectedQueryLogUser(e.target.value)}
                            style={{ borderRadius: 8, border: '1px solid #d1d5db', background: '#ffffff', color: '#0f172a', fontSize: 12, padding: '6px 10px', minWidth: 170 }}
                          >
                            <option value="all">Select user</option>
                            {queryLogFilteredUserOptions.map((item) => (
                              <option key={`overview-${item.id}`} value={item.id}>
                                {item.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                      {queryLogUserSearch.trim() && queryLogTopMatch && (
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                          Suggested match:{' '}
                          <button
                            type="button"
                            onClick={() => setSelectedQueryLogUser(queryLogTopMatch.id)}
                            style={{ border: 'none', background: 'transparent', color: '#2563eb', cursor: 'pointer', padding: 0, fontSize: 11, fontWeight: 700 }}
                          >
                            {queryLogTopMatch.label}
                          </button>
                        </div>
                      )}
                    </article>

                    <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>User Query Logs</div>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#374151' }}>
                          <thead>
                            <tr style={{ background: '#f9fafb' }}>
                              {['User', 'Query', 'Intent', 'Fallback', 'Personalized', 'Weight', 'Model Route', 'KG Used', 'PKL Used', 'LLM', 'Fine-tuned'].map((h) => (
                                <th key={`user-${h}`} style={{ textAlign: 'left', padding: '6px 5px', borderBottom: '1px solid #e5e7eb', color: '#6b7280', fontWeight: 700 }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {selectedUserQueryLogs.length === 0 ? (
                              <tr>
                                <td colSpan={11} style={{ padding: '18px 8px', textAlign: 'center', color: '#94a3b8' }}>
                                  {selectedQueryLogUser === 'all' ? 'Select a user to view user-specific query logs.' : 'No query logs found for this user.'}
                                </td>
                              </tr>
                            ) : (
                              selectedUserQueryLogs.slice(0, 40).map((log: any, idx: number) => (
                                <tr key={`user-row-${log.ts || idx}-${log.user_id || 'u'}`}>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{getQueryLogUserLabel(log.user_id)}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', maxWidth: 260, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={String(log.query || '')}>{String(log.query || '-')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.intent || 'n/a')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.fallback_used ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.personalized ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{Number(log.final_response_weight || 0).toFixed(3)}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.model_route || log.intent_method || '-')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.uses_kg ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.pkl_model_used ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.llm_used || 'n/a')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.fine_tuned_model || '-')}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </article>

                    <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>All Query Logs</div>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#374151' }}>
                          <thead>
                            <tr style={{ background: '#f9fafb' }}>
                              {['User', 'Query', 'Intent', 'Fallback', 'Personalized', 'Weight', 'Model Route', 'KG Used', 'PKL Used', 'LLM', 'Fine-tuned'].map((h) => (
                                <th key={`all-${h}`} style={{ textAlign: 'left', padding: '6px 5px', borderBottom: '1px solid #e5e7eb', color: '#6b7280', fontWeight: 700 }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {allQueryLogs.length === 0 ? (
                              <tr>
                                <td colSpan={11} style={{ padding: '18px 8px', textAlign: 'center', color: '#94a3b8' }}>
                                  No query logs fetched yet.
                                </td>
                              </tr>
                            ) : (
                              allQueryLogs.slice(0, 60).map((log: any, idx: number) => (
                                <tr key={`all-row-${log.ts || idx}-${log.user_id || 'u'}`}>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{getQueryLogUserLabel(log.user_id)}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', maxWidth: 260, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={String(log.query || '')}>{String(log.query || '-')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.intent || 'n/a')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.fallback_used ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.personalized ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{Number(log.final_response_weight || 0).toFixed(3)}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.model_route || log.intent_method || '-')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.uses_kg ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{log.pkl_model_used ? 'Yes' : 'No'}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.llm_used || 'n/a')}</td>
                                  <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{String(log.fine_tuned_model || '-')}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </article>

                    <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Data Engineer Insights</div>
                        {insightHighlights.slice(0, 3).map((insight) => (
                          <div key={insight} style={{ borderRadius: 7, border: '1px solid #e5e7eb', background: '#f9fafb', padding: '7px 8px', fontSize: 11, color: '#4b5563' }}>
                            {insight}
                          </div>
                        ))}
                      </article>
                      <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Recommendation Paths</div>
                        {(metrics.topPaths.length > 0 ? metrics.topPaths.slice(0, 3) : ['No recommendation path traces yet.']).map((item: string) => (
                          <div key={item} style={{ borderRadius: 7, border: '1px solid #e5e7eb', background: '#f9fafb', padding: '7px 8px', fontSize: 11, color: '#4b5563' }}>
                            {item}
                          </div>
                        ))}
                      </article>
                    </section>
                  </section>
                )}
              </div>
            </section>
          </>
        )}

        {activeSection === 'featureops_workflow' && <FeatureOpsWorkflowPanel />}

        {activeSection === 'feedback_center' && (
          <>
            <section style={{ background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0', padding: 12, color: '#0f172a' }}>
              <div style={{ maxWidth: 1200, margin: '0 auto', display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>Recommendation Feedback</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Live quality, satisfaction, and recommendation behavior from production telemetry.</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setMetricsRefreshTick((v) => v + 1)}
                    title="Refresh feedback center metrics"
                    aria-label="Refresh feedback center metrics"
                    style={{ borderRadius: 999, border: '2px solid #334155', background: '#e2e8f0', color: '#0f172a', width: 38, height: 38, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: '0 1px 5px rgba(15,23,42,0.12)' }}
                  >
                    <RefreshCw size={18} color="#020617" strokeWidth={3} />
                  </button>
                </div>

                <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 8 }}>
                  <article style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Average Rating</div>
                    <div style={{ fontSize: 24, fontWeight: 800 }}>{Number(metrics.satisfaction?.avg_rating || 0).toFixed(2)} / 5</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Ratings Count</div>
                    <div style={{ fontSize: 24, fontWeight: 800 }}>{formatNumber(Number(metrics.satisfaction?.count || 0))}</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Checkout Feedback</div>
                    <div style={{ fontSize: 24, fontWeight: 800 }}>{formatNumber(Number(metrics.satisfaction?.checkout_count || 0))}</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Add-to-Cart Feedback</div>
                    <div style={{ fontSize: 24, fontWeight: 800 }}>{formatNumber(Number(metrics.satisfaction?.add_to_cart_count || 0))}</div>
                  </article>
                  <article style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#ffffff', padding: 10 }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>Fallback Rate</div>
                    <div style={{ fontSize: 24, fontWeight: 800 }}>
                      {(() => {
                        const logs = Array.isArray(metrics.queryLogs) ? metrics.queryLogs : []
                        if (logs.length === 0) return '0.0%'
                        const fallbackCount = logs.filter((item: any) => !!item?.fallback_used).length
                        return `${((fallbackCount / logs.length) * 100).toFixed(1)}%`
                      })()}
                    </div>
                  </article>
                </section>

                <section>
                  <article style={{ borderRadius: 8, border: '1px solid #e2e8f0', background: '#ffffff', padding: 10, display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Query Feedback Analytics</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 8 }}>
                      <div style={{ borderRadius: 8, border: '1px solid #bae6fd', background: '#f0f9ff', padding: 10 }}>
                        <div style={{ fontSize: 11, color: '#0369a1' }}>Total Query Feedback</div>
                        <div style={{ fontSize: 24, fontWeight: 800 }}>{formatNumber(Number(metrics.queryFeedbackSummary?.total || 0))}</div>
                      </div>
                      <div style={{ borderRadius: 8, border: '1px solid #bbf7d0', background: '#f0fdf4', padding: 10 }}>
                        <div style={{ fontSize: 11, color: '#166534' }}>Positive Feedback Rate</div>
                        <div style={{ fontSize: 24, fontWeight: 800 }}>{Number(metrics.queryFeedbackSummary?.positive_rate || 0).toFixed(1)}%</div>
                      </div>
                      <div style={{ borderRadius: 8, border: '1px solid #fecaca', background: '#fef2f2', padding: 10 }}>
                        <div style={{ fontSize: 11, color: '#991b1b' }}>Negative Feedback Rate</div>
                        <div style={{ fontSize: 24, fontWeight: 800 }}>{Number(metrics.queryFeedbackSummary?.negative_rate || 0).toFixed(1)}%</div>
                      </div>
                      <div style={{ borderRadius: 8, border: '1px solid #fde68a', background: '#fffbeb', padding: 10 }}>
                        <div style={{ fontSize: 11, color: '#92400e' }}>Skip Rate</div>
                        <div style={{ fontSize: 24, fontWeight: 800 }}>{Number(metrics.queryFeedbackSummary?.skip_rate || 0).toFixed(1)}%</div>
                      </div>
                    </div>
                  </article>
                </section>

                <section style={{ display: 'grid', gap: 10 }}>
                  <article style={{ borderRadius: 8, background: '#ffffff', border: '1px solid #e5e7eb', padding: 10, display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#111827' }}>Query Feedback Analytics</div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, color: '#374151' }}>
                        <thead>
                          <tr style={{ background: '#f9fafb' }}>
                            {['Feedback ID', 'Query ID', 'User', 'Query', 'Intent', 'Feedback', 'Reco Count', 'Model Route', 'Style', 'Event', 'Budget'].map((h) => (
                              <th key={`qf-${h}`} style={{ textAlign: 'left', padding: '6px 5px', borderBottom: '1px solid #e5e7eb', color: '#6b7280', fontWeight: 700 }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {queryFeedbackRows.length === 0 ? (
                            <tr>
                              <td colSpan={11} style={{ padding: '18px 8px', textAlign: 'center', color: '#94a3b8' }}>
                                No query feedback records yet.
                              </td>
                            </tr>
                          ) : (
                            queryFeedbackRows.map((row) => (
                              <tr key={row.key}>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', fontFamily: 'monospace' }}>{row.feedbackId}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', fontFamily: 'monospace' }}>{row.queryId}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.userId}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6', maxWidth: 240, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={row.queryText}>{row.queryText}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.detectedIntent}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.feedbackType}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{formatNumber(row.recommendationCount)}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.modelRoute}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.structuredStyle}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.structuredEvent}</td>
                                <td style={{ padding: '6px 5px', borderBottom: '1px solid #f3f4f6' }}>{row.structuredBudget}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </article>
                </section>

              </div>
            </section>
          </>
        )}


      </div>
    </div>
  )
}


