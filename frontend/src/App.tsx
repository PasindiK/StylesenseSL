import React, { useState, useRef, useEffect } from 'react'
import { HardDrive } from 'lucide-react'
import './App.css'
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
  
  // Collapsible explainability panel
  const [showExplainability, setShowExplainability] = useState(false)

  // Cart state
  const [showCart, setShowCart] = useState(false)
  const [cartData, setCartData] = useState<any>(null)
  const [cartItemCount, setCartItemCount] = useState(0)

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
    // Keep signals visible in chat so preference capture feels connected to the agent flow.
    appendMessage('system', `Captured preference: ${signal.type} = ${signal.value}`)
    setMeta({
      mode: 'kg_preference_signal',
      request: `user=${signal.userId}`,
      response: signal,
    })
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
  }

  // Add product from recommendation card to cart
  async function handleAddProductToCart(url: string, selectedSize?: string) {
    try {
      console.log('[CART] Adding product from recommendation:', url, 'Size:', selectedSize)
      const res = await fetch(`${API_BASE}/cart/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, quantity: 1, size: selectedSize })
      })
      
      if (res.ok) {
        const data = await res.json()
        console.log('[CART] Product added successfully:', data)
        // Refresh cart
        fetchCart()
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

  // Perform the selected action against the backend.
  // Uses the Vite dev proxy: calls are made to `/api/...` which the dev server proxies to the FastAPI backend.
  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault()
    const q = text.trim()
    if (!q) return

    appendMessage('user', q)
    setText('')
    setIsTyping(true)

    try {
      // POST /api/answer (free-text)
      const res = await fetch(`${API_BASE}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
        body: JSON.stringify({ text: q }),
      })
      
      if (!res.ok) {
        const errorText = await res.text()
        setIsTyping(false)
        appendMessage('ai', `Sorry, I encountered an error: ${errorText}`)
        return
      }
      
      const payload = await safeParseResponse(res)
      console.log('[DEBUG] Payload received:', payload)
      
      // Check multiple message fields
      const responseMessage = payload.reply || payload.message || payload.answer || payload.text
      
      setIsTyping(false)
      
      if (!responseMessage) {
        console.error('[ERROR] No message in payload:', payload)
        appendMessage('ai', "I'm having trouble generating a response. Please try rephrasing your query.")
      } else {
        appendMessage('ai', responseMessage, { response: payload })
      }
      
      setMeta({ mode: 'answer', request: q, response: payload })
      
      // Refresh cart if cart-related intent
      if (payload.intent && ['add_to_cart', 'view_cart', 'clear_cart', 'multi_task'].includes(payload.intent)) {
        console.log('[CART] Cart-related intent detected:', payload.intent)
        // If view_cart intent has cart data, use it directly
        if (payload.intent === 'view_cart' && payload.cart) {
          console.log('[CART] Using cart data from view_cart response')
          setCartData(payload.cart)
          setCartItemCount(payload.cart?.total_items || 0)
          // Auto-open cart panel for view_cart
          setShowCart(true)
        } else {
          // Otherwise fetch fresh cart data
          fetchCart()
        }
      }
    } catch (err: any) {
      console.error('[ERROR] Exception in handleSubmit:', err)
      appendMessage('ai', 'Error contacting backend: ' + String(err))
    }
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

  function normalizeSearchResponse(payload: any, q: string) {
    const products: any[] = Array.isArray(payload?.products) ? payload.products : []

    // If no products returned, synthesize a small demo set
    if (products.length === 0) {
      const sample = [
        { id: 'p-demo-1', name: 'Red A-line Dress', price_LKR: 4500 },
        { id: 'p-demo-2', name: 'Deep Red Maxi Dress', price_LKR: 6200 },
        { id: 'p-demo-3', name: 'Casual Red Wrap Dress', price_LKR: 3200 },
      ]
      return {
        products: sample.map((p) => ({ ...p, personalization_score: 0.72, why: guessWhyForProduct(p, q) })),
        personalization_score: 0.72,
        why: ['No direct matches — showing relaxed results'],
        fallback_steps: ['Relax color/size filters', 'Expand price range', 'Use semantic search'],
      }
    }

    // Ensure every product has a personalization_score and why
    const augmentedProducts = products.map((p: any) => ({
      ...p,
      personalization_score: p.personalization_score ?? 0.5,
      why: p.why ?? guessWhyForProduct(p, q),
    }))

    return {
      ...payload,
      products: augmentedProducts,
      personalization_score: payload.personalization_score ?? augmentedProducts[0]?.personalization_score ?? 0.5,
      why: payload.why ?? augmentedProducts[0]?.why ?? ['Matches basic filters'],
      fallback_steps: payload.fallback_steps ?? [],
    }
  }

  function normalizeAnswerResponse(payload: any, q: string) {
    // /api/answer returns { intent, shop, results, fallbacks }
    const results: any[] = Array.isArray(payload?.results) ? payload.results : []

    // Augment each result with personalization_score and why if missing
    const augmentedResults = results.map((p: any) => ({
      ...p,
      personalization_score: p.personalization_score ?? 0.65,
      why: p.why ?? guessWhyForProduct(p, q),
    }))

    return {
      intent: payload?.intent || {},
      shop: payload?.shop,
      results: augmentedResults,
      fallbacks: payload?.fallbacks || [],
      answer:
        augmentedResults.length > 0
          ? `Found ${augmentedResults.length} product${augmentedResults.length === 1 ? '' : 's'} matching your query.`
          : `No products found matching your query. Try refining your search (e.g., "affordable dresses under 5000").`,
    }
  }

  function normalizeOrchestrateResponse(payload: any, q: string) {
    if (!payload || (!payload.plan && !payload.trace)) {
      const plan = [
        { step: 'parse_intent', detail: 'Extract color and category' },
        { step: 'catalog_search', detail: 'Search products with filters' },
        { step: 'personalize', detail: 'Score by user preferences' },
      ]
      const trace = [
        { step: 'parse_intent', ok: true, output: { color: 'red', category: 'dress' } },
        { step: 'catalog_search', ok: true, output: { found: 3 } },
        { step: 'personalize', ok: true, output: { top: 'p-demo-1' } },
      ]
      return { plan, trace, summary: `Executed ${plan.length} steps. Found 3 candidates.` }
    }
    return payload
  }

  function guessWhyForProduct(p: any, q: string) {
    const reasons: string[] = []
    if (/red/i.test(q) || /red/i.test(p?.name)) reasons.push('Matches color preference: red')
    if (/dress|dresses/i.test(q) || /dress/i.test(p?.name)) reasons.push('Matches category: dress')
    if (/affordable|cheap|budget|low|under/i.test(q)) reasons.push('Within requested budget')
    if (!reasons.length) reasons.push('Matches some query attributes')
    return reasons
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
        <main className="chat-main">
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
                  
                  // Only show products if this is an AI message with product results
                  const showProducts = m.sender === 'ai' && messageMeta?.response && 
                    (messageMeta.response.intent === 'product_search' || 
                     messageMeta.response.intent === 'multi_task' ||
                     messageMeta.response.best_matches?.length > 0 ||
                     messageMeta.response.new_suggestions?.length > 0)
                  
                  return (
                    <React.Fragment key={m.id}>
                      <div className={`message ${m.sender}`}>
                        <div className="message-avatar">{avatarEmoji}</div>
                        <div className="message-content">
                          <div className="message-sender">{displayName}</div>
                          <div className="message-text" style={{whiteSpace: 'pre-line'}}>{m.text}</div>
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
                                      onAddToCart: handleAddProductToCart
                                    }} 
                                    showScore={false} 
                                  />
                                ))}
                              </div>
                            </>
                          )}
                          {messageMeta.response.new_suggestions && messageMeta.response.new_suggestions.length > 0 && (
                            <>
                              <h3 className="products-title">New Suggestions</h3>
                              <div className="product-grid">
                                {messageMeta.response.new_suggestions.map((p: any, pIdx: number) => (
                                  <ProductCard 
                                    key={`${m.id}-new-${p.product_id}-${pIdx}`} 
                                    product={{ 
                                      ...p, 
                                      id: p.product_id || p.id || `new-${pIdx}`,
                                      onAddToCart: handleAddProductToCart
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
                                    onAddToCart: handleAddProductToCart
                                  }} 
                                />
                              ))}
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
                
                {/* Explainability toggle button */}
                {meta && (
                  <div className="meta-toggle-section">
                    <button
                      type="button"
                      onClick={() => setShowExplainability(!showExplainability)}
                      className="meta-toggle-btn"
                    >
                      {showExplainability ? '▼ Hide' : '▶ Show'} Technical Details
                    </button>
                  </div>
                )}

                {/* Explainability Panel */}
                {showExplainability && meta && (
                  <div className="explainability-panel">
                    <h3>Technical Details</h3>
                    <div className="meta-block">
                      <h4>Request</h4>
                      <pre className="small">{meta.request}</pre>

                      <h4>Mode</h4>
                      <pre className="small">{meta.mode}</pre>

                      <h4>Response (raw)</h4>
                      <pre className="small">{JSON.stringify(meta.response, null, 2)}</pre>

                      {meta.response?.personalization_score !== undefined && (
                        <>
                          <h4>Personalization Score</h4>
                          <div className="score">{String(meta.response.personalization_score)}</div>
                        </>
                      )}

                      {meta.response?.why && (
                        <>
                          <h4>Why Recommended</h4>
                          <div className="why">{String(meta.response.why)}</div>
                        </>
                      )}

                      {meta.response?.fallback_steps && (
                        <>
                          <h4>Fallback Steps</h4>
                          <pre className="small">{JSON.stringify(meta.response.fallback_steps, null, 2)}</pre>
                        </>
                      )}

                      {meta.response?.fallbacks && (
                        <>
                          <h4>Applied Fallbacks</h4>
                          <pre className="small">{JSON.stringify(meta.response.fallbacks, null, 2)}</pre>
                        </>
                      )}

                      {meta.response?.plan && (
                        <>
                          <h4>Agent Plan</h4>
                          <pre className="small">{JSON.stringify(meta.response.plan, null, 2)}</pre>
                        </>
                      )}

                      {meta.response?.intent && (
                        <>
                          <h4>Parsed Intent</h4>
                          <pre className="small">{JSON.stringify(meta.response.intent, null, 2)}</pre>
                        </>
                      )}

                      {meta.response?.trace && (
                        <>
                          <h4>Execution Trace</h4>
                          <pre className="small">{JSON.stringify(meta.response.trace, null, 2)}</pre>
                        </>
                      )}
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
