import React, { useState, useRef, useEffect } from 'react'
import { HardDrive } from 'lucide-react'
import './App.css'
import shoppingAssistantAvatar from './assets/shopping-assistant-avatar.svg'
import ProductCard from './modules/agentic_ai/components/ProductCard'
import type { Product } from './modules/agentic_ai/components/ProductCard'
import AgenticAIDashboard from './modules/agentic_ai/pages/AgenticAIDashboard'
import type { KGPreferenceSignal } from './modules/agentic_ai/services/kgSignals'
import DataFabricTestingPage from './modules/data_fabric/components/DataFabricTestingPage'
import DataArchitectureTestingPage from './modules/data_architecture/components/DataArchitectureTestingPage'
// @ts-ignore - legacy JSX module without TypeScript declarations
import DataMeshApp from './modules/data_mesh/src/App.jsx'

type Message = {
  id: string
  sender: 'user' | 'ai' | 'system'
  text: string
  metadata?: any
}

type ComponentKey = 'agentic_ai' | 'data_mesh' | 'data_fabric' | 'data_architecture'

type OrderAssistantCheckoutRequest = {
  id: string
  url: string
  quantity?: number
  size?: string
  color?: string
  name?: string
}

const componentCards: Array<{
  key: ComponentKey
  title: string
  description: string
}> = [
  {
    key: 'agentic_ai',
    title: 'Agentic AI',
    description: 'Conversational fashion assistant for personalized recommendations, product discovery, and smart cart actions.',
  },
  {
    key: 'data_mesh',
    title: 'Data Mesh',
    description: 'Domain-oriented data access and governance view for distributed ownership and discoverability.',
  },
  {
    key: 'data_fabric',
    title: 'Data Fabric',
    description: 'Unified integration layer connecting data pipelines, metadata, and intelligent automation across sources.',
  },
  {
    key: 'data_architecture',
    title: 'Data Architecture',
    description: 'High-level architecture perspective for models, standards, and platform design decisions.',
  },
]

export default function App() {
  // Landing page state
  const [showLanding, setShowLanding] = useState(true)
  const [selectedComponent, setSelectedComponent] = useState<ComponentKey | null>(null)
  
  // Dark mode state
  const [darkMode, setDarkMode] = useState(true)

  // Selected demo user for personalization header
  const [userId, setUserId] = useState('')
  const [userName, setUserName] = useState('')

  // Chat messages shown in the center column
  const [messages, setMessages] = useState<Message[]>([])

  // Typing indicator state
  const [isTyping, setIsTyping] = useState(false)

  // Input box state
  const [text, setText] = useState('')

  // Metadata shown in right-side explainability panel
  const [meta, setMeta] = useState<any>(null)

  // Users for dropdown
  const [users, setUsers] = useState<{ id: string; name: string }[]>([])
  
  // Cart state
  const [showCart, setShowCart] = useState(false)
  const [cartData, setCartData] = useState<any>(null)
  const [cartItemCount, setCartItemCount] = useState(0)
  const [showOrderingAssistantHint, setShowOrderingAssistantHint] = useState(false)
  const [agenticInitialSection, setAgenticInitialSection] = useState<'chat' | 'order_assistant'>('chat')
  const [orderAssistantCheckoutRequest, setOrderAssistantCheckoutRequest] = useState<OrderAssistantCheckoutRequest | null>(null)
  const [queryFeedbackByMessage, setQueryFeedbackByMessage] = useState<Record<string, 'yes' | 'no' | 'skip'>>({})
  const [mandatoryFeedbackByMessage, setMandatoryFeedbackByMessage] = useState<Record<string, boolean>>({})
  const [pendingMandatoryFeedbackMessageId, setPendingMandatoryFeedbackMessageId] = useState<string | null>(null)
  const recommendationFeedbackPromptCountRef = useRef(0)

  // Message list ref
  const listRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Main chat interface API_base - MUST be before useEffect
  const API_BASE = typeof window !== 'undefined' && (window as any).VITE_API_URL 
    ? (window as any).VITE_API_URL
    : (typeof import.meta !== 'undefined' && (import.meta.env.VITE_API_URL as any)) || '/api'

  // Apply dark mode class to document
  useEffect(() => {
    if (darkMode) {
      document.documentElement.setAttribute('data-theme', 'dark')
    } else {
      document.documentElement.setAttribute('data-theme', 'light')
    }
  }, [darkMode])

  // Load users from backend
  useEffect(() => {
    fetch(`${API_BASE}/users`)
      .then((r) => r.json())
      .then((j) => {
        if (Array.isArray(j?.users) && j.users.length > 0) {
          setUsers(j.users)
          if (!userId) {
            setUserId(j.users[0].id)
            setUserName(j.users[0].name || j.users[0].id)
          }
        }
      })
      .catch(() => {})
  }, [API_BASE, userId])

  // Load cart data
  useEffect(() => {
    if (!showLanding) {
      fetchCart()
    }
  }, [API_BASE, showLanding])

  // Fetch cart from backend
  async function fetchCart() {
    try {
      console.log('[CART] Fetching cart from', `${API_BASE}/cart`)
      const res = await fetch(`${API_BASE}/cart`)
      console.log('[CART] Response status:', res.status)
      if (res.ok) {
        const data = await res.json()
        console.log('[CART] Received cart data:', data)
        setCartData(data)
        setCartItemCount(data?.total_items || 0)
        console.log('[CART] Updated cartItemCount to:', data?.total_items)
      } else {
        console.error('[CART] Failed to fetch cart, status:', res.status)
      }
    } catch (err) {
      console.error('[CART] Fetch error:', err)
    }
  }

  // Dark mode toggle button
  function toggleDarkMode() {
    setDarkMode(!darkMode)
  }

  function goToTilesHome() {
    setShowLanding(false)
    setSelectedComponent(null)
  }

  function handleDashboardUserChange(nextUserId: string) {
    setUserId(nextUserId)
    const selected = users.find((u) => u.id === nextUserId)
    setUserName(selected?.name || nextUserId)
  }

  function handlePreferenceSignal(signal: KGPreferenceSignal) {
    // Keep preference updates visible in chat using concise status text.
    appendMessage('system', signal.value || 'Preference updated.')
    setMeta({
      mode: 'kg_preference_signal',
      request: `user=${signal.userId}`,
      response: signal,
    })
  }

  async function handleOpenShoppingCartFromOrderAssistant() {
    await fetchCart()
    setShowCart(true)
  }

  function handleOpenOrderingAssistant() {
    window.dispatchEvent(new CustomEvent('open-ordering-assistant'))
  }

  function handleCheckoutCartItem(item: any) {
    const itemUrl = String(item?.url || item?.product_url || '').trim()
    if (!itemUrl) {
      appendMessage('system', 'Cannot start checkout for this item because the product URL is missing.')
      return
    }

    setOrderAssistantCheckoutRequest({
      id: crypto.randomUUID(),
      url: itemUrl,
      quantity: Number(item?.quantity || 1),
      size: item?.selected_size ? String(item.selected_size) : undefined,
      color: item?.selected_color ? String(item.selected_color) : undefined,
      name: item?.name ? String(item.name) : undefined,
    })
    // Always route into the Agentic AI surface before opening Order Assistant.
    setShowLanding(false)
    setShowCart(false)
    setSelectedComponent('agentic_ai')
    setAgenticInitialSection('order_assistant')
  }

  // Landing page component
  if (showLanding) {
    return (
      <div className="landing-page">
        {/* Animated background shapes */}
        <div className="landing-bg-shapes">
          <div className="shape shape-1"></div>
          <div className="shape shape-2"></div>
          <div className="shape shape-3"></div>
        </div>

        <div className="landing-container">
          <div className="landing-content">
            <h1 className="landing-title">StylesenseSL</h1>
            <p className="landing-description">
              Discover your perfect style with AI-powered fashion recommendations.
              Get personalized product suggestions tailored to your unique taste and preferences.
            </p>
            <div className="landing-actions">
              <button 
                className="landing-button"
                onClick={() => {
                  console.log('Explore button clicked!')
                  setShowLanding(false)
                  setSelectedComponent(null)
                }}
              >
                Explore Now
              </button>
            </div>
          </div>
        </div>

        <footer className="app-footer landing-footer">
          <span>© 2026 StylesenseSL</span>
          <span>AI-Powered Fashion Intelligence Platform</span>
        </footer>

        {/* Dark mode toggle - top right */}
        <button className="theme-toggle" onClick={toggleDarkMode} title="Toggle dark mode">
          {darkMode ? '☀️' : '🌙'}
        </button>
      </div>
    )
  }

  if (!selectedComponent) {
    return (
      <div id="agent-console" className={`theme-${darkMode ? 'dark' : 'light'}`}>
        <div className="component-tile-page">
          <div className="chat-header tile-header">
            <h1>Select a Platform Component</h1>
            <p className="chat-subtitle">Choose one of the four modules to continue</p>
          </div>

          <div className="component-tile-grid">
            {componentCards.map((component) => (
              <button
                key={component.key}
                type="button"
                className="component-tile-card"
                onClick={() => setSelectedComponent(component.key)}
              >
                <h3>{component.title}</h3>
                <p>{component.description}</p>
              </button>
            ))}
          </div>

          <div className="component-tile-actions">
            <button
              type="button"
              className="sidebar-btn"
              onClick={() => setShowLanding(true)}
              title="Go to landing"
            >
              🏠
            </button>
            <button className="theme-toggle" onClick={toggleDarkMode} title="Toggle dark mode">
              {darkMode ? '☀️' : '🌙'}
            </button>
          </div>

          <footer className="app-footer tiles-footer">
            <span>Enterprise Data & AI Modules</span>
            <span>Agentic AI • Data Mesh • Data Fabric • Data Architecture</span>
          </footer>
        </div>
      </div>
    )
  }

  if (selectedComponent !== 'agentic_ai') {
    const component = componentCards.find((c) => c.key === selectedComponent)
    return (
      <div id="agent-console" className={`theme-${darkMode ? 'dark' : 'light'}`}>
        <div className="chat-layout">
          <aside className="chat-sidebar">
            <div className="sidebar-header">
              <h2>{component?.title || 'Component'}</h2>
            </div>

            <div className="sidebar-controls component-sidebar-text">
              <div className="component-nav">
                {componentCards.map((card) => (
                  <button
                    key={card.key}
                    type="button"
                    className={`component-nav-btn ${selectedComponent === card.key ? 'active' : ''}`}
                    onClick={() => setSelectedComponent(card.key)}
                    title={card.title}
                  >
                    {card.key === 'data_architecture' && <HardDrive size={16} strokeWidth={2} style={{ marginRight: '6px' }} />}
                    {card.title}
                  </button>
                ))}
              </div>
              <p>{component?.description}</p>
            </div>

            <div className="sidebar-footer">
              <button
                className="sidebar-btn theme-toggle-btn"
                onClick={toggleDarkMode}
                title="Toggle dark mode"
              >
                {darkMode ? '☀️' : '🌙'}
              </button>
              <button
                className="sidebar-btn home-btn"
                onClick={goToTilesHome}
                title="Home"
              >
                🏠
              </button>
            </div>
          </aside>

          <main className="chat-main">
            <div className="chat-header">
              <h1>{component?.title}</h1>
              <p className="chat-subtitle">{component?.description}</p>
            </div>

            <div className={`component-view ${selectedComponent === 'data_mesh' ? 'data-mesh-host' : ''}`}>
              {selectedComponent === 'data_mesh' ? (
                <DataMeshApp />
              ) : selectedComponent === 'data_fabric' ? (
                <DataFabricTestingPage />
              ) : selectedComponent === 'data_architecture' ? (
                <DataArchitectureTestingPage />
              ) : (
                <div className="component-placeholder">Component dashboard is not available yet.</div>
              )}
            </div>
          </main>
        </div>
      </div>
    )
  }

  // Utility: append message to chat
  function appendMessage(sender: Message['sender'], text: string, metadata?: any) {
    const m: Message = { 
      id: String(Date.now()) + Math.random(), 
      sender, 
      text,
      metadata 
    }
    setMessages((s) => [...s, m])
    // scroll to bottom after render
    setTimeout(() => listRef.current?.scrollTo({ top: 99999, behavior: 'smooth' }), 50)
    return m.id
  }

  // Add product from recommendation card to cart
  async function handleAddProductToCart(url: string, selectedSize?: string, queryId?: string) {
    try {
      console.log('[CART] Adding product from recommendation:', url, 'Size:', selectedSize)
      const res = await fetch(`${API_BASE}/cart/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          quantity: 1,
          size: selectedSize,
          user_id: userId,
          query_id: queryId,
        })
      })
      
      if (res.ok) {
        const data = await res.json()
        console.log('[CART] Product added successfully:', data)
        // Refresh cart first so the newly added item is visible immediately.
        await fetchCart()
        // Auto-open cart panel
        setShowCart(true)
        // Show success message
        appendMessage('system', `✅ Added "${data.product?.name}" ${selectedSize ? `(${selectedSize})` : ''} to cart!`)
      } else {
        const error = await res.text()
        console.error('[CART] Failed to add product:', error)
        appendMessage('system', `❌ Failed to add product to cart`)
      }
    } catch (err) {
      console.error('[CART] Error:', err)
      appendMessage('system', `❌ Error adding product to cart`)
    }
  }

  async function submitQuery(query: string, displayText?: string) {
    const q = query.trim()
    if (!q) return

    appendMessage('user', displayText || q)
    setText('')
    setIsTyping(true)

    try {
      const res = await fetch(`${API_BASE}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
        body: JSON.stringify({ text: q, user_id: userId }),
      })

      if (!res.ok) {
        const errorText = await res.text()
        setIsTyping(false)
        appendMessage('ai', `Sorry, I encountered an error: ${errorText}`)
        return
      }

      const payload = await safeParseResponse(res)
      console.log('[DEBUG] Payload received:', payload)

      let responseMessage = payload.reply || payload.message || payload.answer || payload.text

      if (payload.intent === 'product_search' && payload.structured_query) {
        const sq = payload.structured_query
        const style = sq.style || 'n/a'
        const event = sq.event || 'n/a'
        const budget = sq.budget || 'n/a'
        const suffix = `\n\n[Structured Query] style=${style}, event=${event}, budget=${budget}`
        responseMessage = `${responseMessage || ''}${suffix}`.trim()
      }

      setIsTyping(false)

      if (!responseMessage) {
        console.error('[ERROR] No message in payload:', payload)
        appendMessage('ai', "I'm having trouble generating a response. Please try rephrasing your query.")
      } else {
        const aiMessageId = appendMessage('ai', responseMessage, { response: payload })
        const hasRecommendationPayload = Boolean(
          String(payload?.query_id || '').trim() && (
            (Array.isArray(payload?.best_matches) && payload.best_matches.length > 0) ||
            (Array.isArray(payload?.new_suggestions) && payload.new_suggestions.length > 0) ||
            (Array.isArray(payload?.results) && payload.results.length > 0) ||
            payload?.intent === 'product_search' ||
            payload?.intent === 'multi_task'
          )
        )
        if (hasRecommendationPayload) {
          recommendationFeedbackPromptCountRef.current += 1
          const isMandatory = recommendationFeedbackPromptCountRef.current >= 3
          setMandatoryFeedbackByMessage((prev) => ({ ...prev, [aiMessageId]: isMandatory }))
          if (isMandatory) {
            setPendingMandatoryFeedbackMessageId(aiMessageId)
          }
        }
      }

      setMeta({ mode: 'answer', request: q, response: payload })

      if (payload.intent && ['add_to_cart', 'view_cart', 'clear_cart', 'multi_task'].includes(payload.intent)) {
        console.log('[CART] Cart-related intent detected:', payload.intent)
        if (payload.intent === 'view_cart' && payload.cart) {
          console.log('[CART] Using cart data from view_cart response')
          setCartData(payload.cart)
          setCartItemCount(payload.cart?.total_items || 0)
          setShowCart(true)
        } else {
          fetchCart()
        }
      }
    } catch (err: any) {
      console.error('[ERROR] Exception in handleSubmit:', err)
      appendMessage('ai', 'Error contacting backend: ' + String(err))
    }
  }

  async function submitQueryFeedback(message: Message, responsePayload: any, feedbackType: 'yes' | 'no' | 'skip') {
    const queryId = String(responsePayload?.query_id || '').trim()
    if (!queryId) {
      appendMessage('system', 'Unable to save feedback: query id is missing for this response.')
      return
    }

    try {
      const isMandatory = !!mandatoryFeedbackByMessage[message.id]
      if (isMandatory && feedbackType === 'skip') {
        appendMessage('system', 'From the 3rd recommendation onward, please choose Yes or No.')
        return
      }

      const recommendationCount = [
        ...(Array.isArray(responsePayload?.best_matches) ? responsePayload.best_matches : []),
        ...(Array.isArray(responsePayload?.new_suggestions) ? responsePayload.new_suggestions : []),
        ...(Array.isArray(responsePayload?.results) ? responsePayload.results : []),
      ].length

      const structured = responsePayload?.structured_query || {}
      const body = {
        query_id: queryId,
        user_id: userId || 'anonymous',
        query_text: String(responsePayload?.query_text || responsePayload?.request_text || ''),
        detected_intent: String(responsePayload?.detected_intent || responsePayload?.intent || 'unknown'),
        feedback_type: feedbackType,
        recommendation_count: recommendationCount,
        model_route: String(responsePayload?.model_route || responsePayload?.intent_method || ''),
        structured_style: String(structured?.style || ''),
        structured_event: String(structured?.event || ''),
        structured_budget: String(structured?.budget || ''),
      }

      const res = await fetch(`${API_BASE}/query-feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const errText = await res.text()
        appendMessage('system', `Failed to save feedback: ${errText}`)
        return
      }

      setQueryFeedbackByMessage((prev) => ({ ...prev, [message.id]: feedbackType }))
      if (isMandatory && (feedbackType === 'yes' || feedbackType === 'no')) {
        setPendingMandatoryFeedbackMessageId((prev) => (prev === message.id ? null : prev))
      }
    } catch (error) {
      appendMessage('system', `Failed to save feedback: ${String(error)}`)
    }
  }

  function handleClarificationChoice(intent: string, originalQuery?: string) {
    const clarifyText = originalQuery
      ? `I meant ${intent}. Original request: ${originalQuery}`
      : `I meant ${intent}.`
    submitQuery(clarifyText, `Intent clarification: ${intent}`)
  }

  // Perform the selected action against the backend.
  // Uses the Vite dev proxy: calls are made to `/api/...` which the dev server proxies to the FastAPI backend.
  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault()
    if (pendingMandatoryFeedbackMessageId && !queryFeedbackByMessage[pendingMandatoryFeedbackMessageId]) {
      appendMessage('system', 'Please rate the latest recommendations with Yes or No before sending a new message.')
      return
    }
    submitQuery(text)
  }

  // --- Response normalization helpers (demo-friendly) ---
  // Safe response parser that falls back to text for non-JSON responses
  async function safeParseResponse(res: Response) {
    const ct = res.headers.get('content-type') || ''
    try {
      // Read the response body once as text
      const text = await res.text()
      
      // Try to parse as JSON
      try {
        return JSON.parse(text)
      } catch (e) {
        // If not JSON, return as text field
        return { text: text }
      }
    } catch (e) {
      return { text: `Failed to parse response: ${String(e)}` }
    }
  }

  const agenticComponent = componentCards.find((c) => c.key === 'agentic_ai')

  return (
    <div id="agent-console" className={`theme-${darkMode ? 'dark' : 'light'}`}>
      <div className="chat-layout">
        {/* LEFT SIDEBAR */}
        <aside className="chat-sidebar">
          <div className="sidebar-header">
            <h2>StylesenseSL</h2>
          </div>

          <div className="sidebar-controls">
            <div className="component-nav">
              {componentCards.map((card) => (
                <button
                  key={card.key}
                  type="button"
                  className={`component-nav-btn ${selectedComponent === card.key ? 'active' : ''}`}
                  onClick={() => setSelectedComponent(card.key)}
                  title={card.title}
                >
                  {card.key === 'data_architecture' && <HardDrive size={16} strokeWidth={2} style={{ marginRight: '6px' }} />}
                  {card.title}
                </button>
              ))}
            </div>
          </div>

          <div className="sidebar-footer">
            <button 
              className="sidebar-btn cart-btn"
              onClick={() => setShowCart(!showCart)}
              title="View shopping cart"
            >
              🛒
              {cartItemCount > 0 && <span className="cart-badge">{cartItemCount}</span>}
            </button>
            <button 
              className="sidebar-btn theme-toggle-btn"
              onClick={toggleDarkMode}
              title="Toggle dark mode"
            >
              {darkMode ? '☀️' : '🌙'}
            </button>
            <button
              className="sidebar-btn home-btn"
              onClick={goToTilesHome}
              title="Home"
            >
              🏠
            </button>
          </div>
        </aside>

        {/* RIGHT CHAT AREA */}
        <main className={`chat-main ${showCart ? 'cart-open' : ''}`}>
          <div className="chat-header">
            <div>
              <h1>{agenticComponent?.title || 'Agentic AI'}</h1>
              <p className="chat-subtitle">{agenticComponent?.description || 'Find your perfect style with AI recommendations'}</p>
            </div>
          </div>

          <div style={{ flex: 1, minHeight: 0, padding: '0 16px 16px' }}>
            <AgenticAIDashboard
              userId={userId}
              users={users}
              onUserChange={handleDashboardUserChange}
              onPreferenceSignal={handlePreferenceSignal}
              onOpenShoppingCart={handleOpenShoppingCartFromOrderAssistant}
              initialSection={agenticInitialSection}
              orderAssistantCheckoutRequest={orderAssistantCheckoutRequest}
              onOrderAssistantCheckoutRequestConsumed={() => setOrderAssistantCheckoutRequest(null)}
              chatContent={
                <section className="chat-conversation-pane" style={{ height: '100%' }}>
                  <div className="message-list" ref={listRef}>
                {messages.length === 0 && (
                  <div className="empty-state">
                    <div className="empty-icon">✨</div>
                    <div className="empty-title">Start Your Style Journey</div>
                    <div className="empty-text">Ask me about fashion, colors, trends, or get personalized recommendations</div>
                  </div>
                )}
                {messages.map((m, idx) => {
                  const displayName = m.sender === 'user' ? userName : 'StylesenseSL'
                  const avatarEmoji = m.sender === 'user' ? '👤' : '✨'
                  
                  // Get metadata for this specific message
                  const messageMeta = m.metadata
                  const clarification = messageMeta?.response?.clarification
                  const hasClarificationChoices = Boolean(
                    m.sender === 'ai' &&
                    messageMeta?.response?.intent === 'clarification_request' &&
                    Array.isArray(clarification?.candidates) &&
                    clarification.candidates.length > 0
                  )
                  
                  // Only show products if this is an AI message with product results
                  const showProducts = m.sender === 'ai' && messageMeta?.response && 
                    (messageMeta.response.intent === 'product_search' || 
                     messageMeta.response.intent === 'multi_task' ||
                     messageMeta.response.best_matches?.length > 0 ||
                     messageMeta.response.new_suggestions?.length > 0)
                  const hasQueryFeedbackPrompt = showProducts && !!String(messageMeta?.response?.query_id || '').trim()
                  const selectedFeedback = queryFeedbackByMessage[m.id]
                  const isMandatoryFeedback = !!mandatoryFeedbackByMessage[m.id]
                  
                  return (
                    <React.Fragment key={m.id}>
                      <div className={`message ${m.sender}`}>
                        <div className="message-avatar">{avatarEmoji}</div>
                        <div className="message-content">
                          <div className="message-sender">{displayName}</div>
                          <div className="message-text" style={{whiteSpace: 'pre-line'}}>{m.text}</div>
                          {hasClarificationChoices && (
                            <div className="clarification-choices">
                              {clarification.candidates.map((c: any, cIdx: number) => (
                                <button
                                  key={`${m.id}-clarify-${c.intent}-${cIdx}`}
                                  type="button"
                                  className="clarification-choice-btn"
                                  onClick={() => handleClarificationChoice(c.intent, clarification.original_query)}
                                >
                                  {c.intent} ({((Number(c.confidence) || 0) * 100).toFixed(1)}%)
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      
                      {/* Show products from current AI response only */}
                      {showProducts && messageMeta?.response && (
                        <div className="products-section">
                          {messageMeta.response.best_matches && messageMeta.response.best_matches.length > 0 && (
                            <>
                              <h3 className="products-title">Best Matches</h3>
                              <div className="product-grid">
                                {messageMeta.response.best_matches.map((p: any, pIdx: number) => (
                                  <ProductCard 
                                    key={`${m.id}-best-${p.product_id}-${pIdx}`} 
                                    product={{ 
                                      ...p, 
                                      id: p.product_id || p.id || `best-${pIdx}`,
                                      onAddToCart: (url: string, size?: string) => handleAddProductToCart(url, size, messageMeta.response.query_id)
                                    }} 
                                    showScore={false} 
                                  />
                                ))}
                              </div>
                            </>
                          )}
                          {messageMeta.response.new_suggestions && messageMeta.response.new_suggestions.length > 0 && (
                            <>
                              <h3 className="products-title">New Recommendations</h3>
                              <div className="product-grid">
                                {messageMeta.response.new_suggestions.map((p: any, pIdx: number) => (
                                  <ProductCard 
                                    key={`${m.id}-new-${p.product_id}-${pIdx}`} 
                                    product={{ 
                                      ...p, 
                                      id: p.product_id || p.id || `new-${pIdx}`,
                                      onAddToCart: (url: string, size?: string) => handleAddProductToCart(url, size, messageMeta.response.query_id)
                                    }} 
                                    showScore={false} 
                                  />
                                ))}
                              </div>
                            </>
                          )}
                          {messageMeta.response.results && messageMeta.response.results.length > 0 && !messageMeta.response.best_matches?.length && !messageMeta.response.new_suggestions?.length && (
                            <div className="product-grid">
                              {messageMeta.response.results.map((p: any, pIdx: number) => (
                                <ProductCard 
                                  key={`${m.id}-result-${p.product_id}-${pIdx}`} 
                                  product={{ 
                                    ...p,
                                    id: p.product_id || p.id || `result-${pIdx}`,
                                    onAddToCart: (url: string, size?: string) => handleAddProductToCart(url, size, messageMeta.response.query_id)
                                  }} 
                                />
                              ))}
                            </div>
                          )}

                          {hasQueryFeedbackPrompt && !selectedFeedback && (
                            <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 10, border: '1px solid #e2e8f0', background: '#f8fafc' }}>
                              <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>
                                Did these recommendations match your request?
                              </div>
                              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                {[
                                  { key: 'yes' as const, label: '👍 Yes' },
                                  { key: 'no' as const, label: '👎 No' },
                                  ...(!isMandatoryFeedback ? [{ key: 'skip' as const, label: 'Skip' }] : []),
                                ].map((item) => {
                                  const active = selectedFeedback === item.key
                                  return (
                                    <button
                                      key={`${m.id}-feedback-${item.key}`}
                                      type="button"
                                      onClick={() => submitQueryFeedback(m, messageMeta.response, item.key)}
                                      style={{
                                        borderRadius: 8,
                                        border: active ? '1px solid #2563eb' : '1px solid #cbd5e1',
                                        background: active ? '#dbeafe' : '#ffffff',
                                        color: active ? '#1e3a8a' : '#0f172a',
                                        fontSize: 12,
                                        fontWeight: 700,
                                        padding: '6px 10px',
                                        cursor: 'pointer',
                                      }}
                                    >
                                      {item.label}
                                    </button>
                                  )
                                })}
                              </div>
                              {isMandatoryFeedback && (
                                <div style={{ marginTop: 8, fontSize: 11, color: '#b45309' }}>
                                  Rating is required for this recommendation response.
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </React.Fragment>
                  )
                })}
                
                {/* Typing indicator */}
                {isTyping && (
                  <div className="message ai">
                    <div className="message-avatar">✨</div>
                    <div className="message-content">
                      <div className="message-sender">StylesenseSL</div>
                      <div className="typing-indicator">
                        <div className="typing-dot"></div>
                        <div className="typing-dot"></div>
                        <div className="typing-dot"></div>
                      </div>
                    </div>
                  </div>
                )}
                
              </div>

              <form className="message-input" onSubmit={handleSubmit}>
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="What are you in the mood to wear today?"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="input-field"
                />
                <button type="submit" className="send-button">Send</button>
                <div
                  className="ordering-assistant-trigger-wrap"
                  onMouseEnter={() => setShowOrderingAssistantHint(true)}
                  onMouseLeave={() => setShowOrderingAssistantHint(false)}
                >
                  <button
                    type="button"
                    className="ordering-assistant-trigger"
                    title="Ordering Assistant"
                    aria-label="Open Ordering Assistant"
                    onClick={handleOpenOrderingAssistant}
                  >
                    <img src={shoppingAssistantAvatar} alt="Ordering Assistant" className="ordering-assistant-trigger-avatar" />
                  </button>
                  {showOrderingAssistantHint && (
                    <div className="ordering-assistant-tooltip">
                      <img src={shoppingAssistantAvatar} alt="Ordering Assistant profile" className="ordering-assistant-tooltip-avatar" />
                      <div>
                        <div className="ordering-assistant-tooltip-title">Ordering Assistant</div>
                        <div className="ordering-assistant-tooltip-text">Cart, checkout, and order help.</div>
                      </div>
                    </div>
                  )}
                </div>
              </form>
                </section>
              }
            />
          </div>
        </main>

        {/* CART PANEL */}
        {showCart && (
          <aside className="cart-panel">
            <div className="cart-header">
              <h2>🛒 Shopping Cart</h2>
              <button className="cart-close" onClick={() => setShowCart(false)}>✕</button>
            </div>
            
            <div className="cart-content">
              {!cartData || cartItemCount === 0 ? (
                <div className="cart-empty">
                  <div className="empty-cart-icon">🛒</div>
                  <p>Your cart is empty</p>
                  <p className="cart-hint">Add products by typing:<br/>"add to cart: [URL]"</p>
                </div>
              ) : (
                <div className="cart-items">
                  {Object.entries(cartData.by_shop || {}).map(([shopId, shopData]: [string, any]) => (
                    <div key={shopId} className="cart-shop-group">
                      <h3 className="cart-shop-name">🏪 {shopData.shop_name}</h3>
                      
                      {shopData.items.map((item: any, idx: number) => {
                        // Find global index of this item in all cart items
                        const globalIdx = cartData.items?.findIndex((i: any) => 
                          i.product_id === item.product_id && 
                          i.selected_size === item.selected_size
                        ) ?? idx
                        
                        return (
                          <div key={idx} className="cart-item">
                            {item.image && (
                              <img src={item.image} alt={item.name} className="cart-item-image" />
                            )}
                            <div className="cart-item-details">
                              {item.url || item.product_url ? (
                                <a 
                                  href={item.url || item.product_url} 
                                  target="_blank" 
                                  rel="noopener noreferrer"
                                  className="cart-item-name cart-item-link"
                                >
                                  {item.name} 🔗
                                </a>
                              ) : (
                                <div className="cart-item-name">{item.name}</div>
                              )}
                              {item.selected_size && (
                                <div className="cart-item-size">Size: <strong>{item.selected_size}</strong></div>
                              )}
                              <div className="cart-item-price">
                                {item.currency} {item.price?.toFixed(2)}
                              </div>
                              
                              {/* Quantity controls */}
                              <div className="cart-item-quantity">
                                <button 
                                  className="qty-btn"
                                  onClick={async () => {
                                    if (item.quantity > 1) {
                                      try {
                                        await fetch(`${API_BASE}/cart/item/${globalIdx}`, {
                                          method: 'PATCH',
                                          headers: { 'Content-Type': 'application/json' },
                                          body: JSON.stringify({ quantity: item.quantity - 1 })
                                        })
                                        fetchCart()
                                      } catch (err) {
                                        console.error('Failed to update quantity:', err)
                                      }
                                    }
                                  }}
                                  disabled={item.quantity <= 1}
                                >
                                  −
                                </button>
                                <span className="qty-display">{item.quantity}</span>
                                <button 
                                  className="qty-btn"
                                  onClick={async () => {
                                    try {
                                      await fetch(`${API_BASE}/cart/item/${globalIdx}`, {
                                        method: 'PATCH',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ quantity: item.quantity + 1 })
                                      })
                                      fetchCart()
                                    } catch (err) {
                                      console.error('Failed to update quantity:', err)
                                    }
                                  }}
                                >
                                  +
                                </button>
                                <button 
                                  className="remove-btn"
                                  onClick={async () => {
                                    try {
                                      await fetch(`${API_BASE}/cart/item/${globalIdx}`, {
                                        method: 'DELETE'
                                      })
                                      fetchCart()
                                      appendMessage('system', `🗑️ Removed "${item.name}" from cart`)
                                    } catch (err) {
                                      console.error('Failed to remove item:', err)
                                    }
                                  }}
                                >
                                  🗑️
                                </button>
                              </div>
                              
                              <div className="cart-item-subtotal">
                                Subtotal: {item.currency} {item.subtotal?.toFixed(2)}
                              </div>

                              <button
                                className="cart-item-checkout-btn"
                                onClick={() => handleCheckoutCartItem(item)}
                                disabled={!item.url && !item.product_url}
                                title={item.url || item.product_url ? 'Checkout this product in Order Assistant' : 'Product URL not available'}
                              >
                                Checkout This Item
                              </button>
                            </div>
                          </div>
                        )
                      })}
                      
                      <div className="cart-shop-totals">
                        <div className="cart-total-line cart-shop-total">
                          <span><strong>{shopData.shop_name} Total:</strong></span>
                          <span><strong>{shopData.currency} {shopData.subtotal?.toFixed(2)}</strong></span>
                        </div>
                      </div>
                    </div>
                  ))}
                  
                  <div className="cart-grand-total">
                    <span>💰 Grand Total:</span>
                    <span><strong>LKR {cartData.grand_total?.toFixed(2)}</strong></span>
                  </div>
                  
                  <div className="cart-actions">
                    <button 
                      className="cart-clear-btn"
                      onClick={async () => {
                        try {
                          await fetch(`${API_BASE}/cart/clear`, { method: 'DELETE' })
                          fetchCart()
                          appendMessage('system', 'Cart cleared successfully')
                        } catch (err) {
                          console.error('Failed to clear cart:', err)
                        }
                      }}
                    >
                      Clear Cart
                    </button>
                  </div>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
