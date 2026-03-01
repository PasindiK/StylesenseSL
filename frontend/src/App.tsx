import React, { useState, useRef, useEffect } from 'react'
import './App.css'
import ProductCard from './components/ProductCard'
import type { Product } from './components/ProductCard'

type Message = {
  id: string
  sender: 'user' | 'ai' | 'system'
  text: string
  metadata?: any
}

type ModuleKey = 'dashboard' | 'agentic' | 'data-mesh' | 'data-fabric' | 'architecture'

type ModuleHealthState = {
  status: 'idle' | 'checking' | 'online' | 'offline'
  message: string
}

export default function App() {
  // Current module view
  const [currentModule, setCurrentModule] = useState<ModuleKey>('dashboard')
  const [showModules, setShowModules] = useState(false)
  
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
  const [userFilter, setUserFilter] = useState('')
  
  // Collapsible explainability panel
  const [showExplainability, setShowExplainability] = useState(false)

  // Cart state
  const [showCart, setShowCart] = useState(false)
  const [cartData, setCartData] = useState<any>(null)
  const [cartItemCount, setCartItemCount] = useState(0)

  // Message list ref
  const listRef = useRef<HTMLDivElement | null>(null)
  const modulesSectionRef = useRef<HTMLDivElement | null>(null)

  // Main chat interface API_base - MUST be before useEffect
  const API_BASE = typeof window !== 'undefined' && (window as any).VITE_API_URL 
    ? (window as any).VITE_API_URL
    : (typeof import.meta !== 'undefined' && (import.meta.env.VITE_API_URL as any)) || '/api'

  const AGENTIC_API_URL = (typeof import.meta !== 'undefined' && (import.meta.env.VITE_AGENTIC_API_URL as any)) || API_BASE
  const DATA_MESH_API_URL = (typeof import.meta !== 'undefined' && (import.meta.env.VITE_DATA_MESH_API_URL as any)) || 'http://localhost:8001'
  const DATA_FABRIC_API_URL = (typeof import.meta !== 'undefined' && (import.meta.env.VITE_DATA_FABRIC_API_URL as any)) || 'http://localhost:8002'
  const DATA_ARCH_API_URL = (typeof import.meta !== 'undefined' && (import.meta.env.VITE_DATA_ARCH_API_URL as any)) || 'http://localhost:8003'

  const [moduleHealth, setModuleHealth] = useState<Record<Exclude<ModuleKey, 'dashboard'>, ModuleHealthState>>({
    agentic: { status: 'idle', message: 'Not checked yet' },
    'data-mesh': { status: 'idle', message: 'Not checked yet' },
    'data-fabric': { status: 'idle', message: 'Not checked yet' },
    architecture: { status: 'idle', message: 'Not checked yet' },
  })

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
    if (currentModule === 'agentic') {
      fetchCart()
    }
  }, [API_BASE, currentModule])

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

  const moduleDescriptions: Record<Exclude<ModuleKey, 'dashboard'>, string> = {
    agentic: 'Main AI chat and recommendations module',
    'data-mesh': 'Shop-wise data mesh module (coming soon)',
    'data-fabric': 'Shop collection data fabric module (coming soon)',
    architecture: 'Data architecture workspace module (coming soon)',
  }

  function getModuleBackend(module: Exclude<ModuleKey, 'dashboard'>) {
    if (module === 'agentic') return { baseUrl: AGENTIC_API_URL, healthPath: '/health' }
    if (module === 'data-mesh') return { baseUrl: DATA_MESH_API_URL, healthPath: '/api/health' }
    if (module === 'data-fabric') return { baseUrl: DATA_FABRIC_API_URL, healthPath: '/api/health/ping' }
    return { baseUrl: DATA_ARCH_API_URL, healthPath: '/api/health' }
  }

  async function checkModuleHealth(module: Exclude<ModuleKey, 'dashboard'>) {
    const cfg = getModuleBackend(module)
    const url = `${cfg.baseUrl}${cfg.healthPath}`

    setModuleHealth((s) => ({
      ...s,
      [module]: { status: 'checking', message: `Checking ${url}` },
    }))

    try {
      const res = await fetch(url)
      if (!res.ok) {
        setModuleHealth((s) => ({
          ...s,
          [module]: { status: 'offline', message: `Backend unavailable (${res.status})` },
        }))
        return
      }

      setModuleHealth((s) => ({
        ...s,
        [module]: { status: 'online', message: `Connected to ${cfg.baseUrl}` },
      }))
    } catch {
      setModuleHealth((s) => ({
        ...s,
        [module]: { status: 'offline', message: `Cannot reach ${cfg.baseUrl}` },
      }))
    }
  }

  function openModule(module: Exclude<ModuleKey, 'dashboard'>) {
    setCurrentModule(module)
    checkModuleHealth(module)
  }

  function scrollToModules() {
    setShowModules(true)
    setTimeout(() => {
      modulesSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 50)
  }

  if (currentModule === 'dashboard') {
    return (
      <div className="module-dashboard-page premium-dashboard">
        {!showModules ? (
          <section className="hero-section">
            <div className="hero-center">
              <h1 className="brand-title">StylesenseSL</h1>
              <p className="brand-subtitle">
                A unified intelligence platform connecting Agentic AI, Data Mesh, Data Fabric, and Data Architecture for smarter fashion discovery and operations.
              </p>
              <div className="brand-loading">
                <span>Preparing the Stylesense ecosystem</span>
              </div>
              <button className="scroll-to-modules-btn" onClick={scrollToModules}>
                Explore Modules ↓
              </button>
            </div>
          </section>
        ) : (
          <section className="modules-section" ref={modulesSectionRef}>
            <div className="module-dashboard-container">
              <div className="module-dashboard-header premium-header">
                <div>
                  <h2>StylesenseSL</h2>
                  <p>Choose a component to continue</p>
                </div>
              </div>
              <div className="module-grid">
                <button className="module-tile" onClick={() => openModule('agentic')}>
                  <h3>Agentic AI</h3>
                  <p>Personalized chat assistant and style recommendations</p>
                </button>
                <button className="module-tile" onClick={() => openModule('data-mesh')}>
                  <h3>Data Mesh</h3>
                  <p>Shop-wise data domains and distributed ownership</p>
                </button>
                <button className="module-tile" onClick={() => openModule('data-fabric')}>
                  <h3>Data Fabric</h3>
                  <p>Collection pipelines, transformation, and metadata flow</p>
                </button>
                <button className="module-tile" onClick={() => openModule('architecture')}>
                  <h3>Data Architecture</h3>
                  <p>Platform governance, structure, and long-term design</p>
                </button>
              </div>
            </div>
          </section>
        )}
      </div>
    )
  }

  if (currentModule !== 'agentic') {
    const health = moduleHealth[currentModule]
    return (
      <div className="module-placeholder-page">
        <div className="module-placeholder-card">
          <h2>{currentModule.replace('-', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}</h2>
          <p>{moduleDescriptions[currentModule]}</p>
          <p className={`module-health ${health.status}`}>{health.message}</p>
          <div className="module-placeholder-actions">
            <button className="module-back-button" onClick={() => checkModuleHealth(currentModule)}>
              Recheck Backend
            </button>
          </div>
          <button className="module-back-button" onClick={() => setCurrentModule('dashboard')}>
            ← Back to Dashboard
          </button>
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

  return (
    <div id="agent-console" className={`theme-${darkMode ? 'dark' : 'light'}`}>
      <div className="chat-layout">
        {/* LEFT SIDEBAR */}
        <aside className="chat-sidebar">
          <div className="sidebar-header">
            <h2>StylesenseSL</h2>
          </div>

          <div className="sidebar-controls">
            <label>
              User:&nbsp;
              <select value={userId} onChange={(e) => {
                setUserId(e.target.value)
                const u = users.find(x => x.id === e.target.value)
                setUserName(u?.name || e.target.value)
              }}>
                {users
                  .filter((u) =>
                    !userFilter || u.id.toLowerCase().includes(userFilter.toLowerCase()) ||
                    (u.name || '').toLowerCase().includes(userFilter.toLowerCase())
                  )
                  .slice(0, 100)
                  .map((u) => (
                    <option key={u.id} value={u.id}>{u.name || u.id}</option>
                  ))}
              </select>
            </label>
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
              className="sidebar-btn back-btn"
              onClick={() => setCurrentModule('dashboard')}
              title="Back to dashboard"
            >
              ↩️
            </button>
          </div>
        </aside>

        {/* RIGHT CHAT AREA */}
        <main className="chat-main">
          <div className="chat-header">
            <h1>Chat with StylesenseSL</h1>
            <p className="chat-subtitle">Find your perfect style with AI recommendations</p>
          </div>

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
              type="text"
              placeholder="What are you in the mood to wear today?"
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="input-field"
            />
            <button type="submit" className="send-button">Send</button>
          </form>
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
