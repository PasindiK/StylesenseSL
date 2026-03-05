import React, { useState } from 'react'

export type Product = {
  id: string
  name: string
  price_LKR?: number
  personalization_score?: number
  why?: string[]
  product_url?: string
  _shop_name?: string
  size_range?: string
  color?: string
  showScore?: boolean
  _show_match_score?: boolean
  _match_score_percent?: number
  _is_repeated?: boolean
  onAddToCart?: (url: string, selectedSize?: string) => void
}

export default function ProductCard({ product, showScore = false }: { product: Product; showScore?: boolean }) {
  const [isHovering, setIsHovering] = useState(false)
  const [isAdding, setIsAdding] = useState(false)
  const [selectedSize, setSelectedSize] = useState<string>('')
  
  const price = product.price_LKR !== undefined ? `LKR ${product.price_LKR.toLocaleString()}` : '—'
  const score = product.personalization_score !== undefined ? `${Math.round(product.personalization_score * 100)}%` : '—'
  const scoreNum = product.personalization_score ?? 0
  const scoreClass = scoreNum >= 0.75 ? 'badge green' : scoreNum >= 0.5 ? 'badge orange' : 'badge'
  
  // Parse size_range into array (e.g., "XS, S, M, L, XL" -> ["XS", "S", "M", "L", "XL"])
  const sizes = product.size_range 
    ? product.size_range.split(',').map(s => s.trim()).filter(s => s)
    : []
  
  const handleAddToCart = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!product.product_url || !product.onAddToCart) return
    
    setIsAdding(true)
    try {
      await product.onAddToCart(product.product_url, selectedSize || undefined)
    } finally {
      setIsAdding(false)
    }
  }
  
  const CardContent = (
    <>
      <div className="pc-title">{product.name}</div>
      <div className="pc-price">{price}</div>
      {product._shop_name && <div className="pc-shop">From: {product._shop_name}</div>}
      {product.color && <div className="pc-color">Color: <span style={{ fontWeight: 500 }}>{product.color}</span></div>}
      {product.size_range && <div className="pc-sizes">Sizes: {product.size_range}</div>}

      {product.why && product.why.length > 0 && (
        <ul className="pc-why">
          {product.why.map((w, i) => (
            <li key={`why-${i}-${w.substring(0, 10)}`}>{w}</li>
          ))}
        </ul>
      )}
      
      {/* Show match score only if explicitly enabled AND above 40% threshold */}
      {product._show_match_score && product._match_score_percent !== null && product._match_score_percent !== undefined && (
        <div className="pc-score-section">
          <div>Match Score: <strong className={product._match_score_percent >= 75 ? 'badge green' : product._match_score_percent >= 50 ? 'badge orange' : 'badge'}>{product._match_score_percent}%</strong></div>
        </div>
      )}
      
      {/* Fallback to personalization score if requested via showScore */}
      {!product._show_match_score && showScore && product.personalization_score !== undefined && (
        <div className="pc-score-section">
          <div>Match Score: <strong className={scoreClass}>{score}</strong></div>
        </div>
      )}
      
      {/* Add to Cart overlay on hover */}
      {isHovering && product.product_url && product.onAddToCart && (
        <div className="pc-overlay" onClick={(e) => e.preventDefault()}>
          {sizes.length > 0 && (
            <div className="pc-size-selector" onClick={(e) => e.stopPropagation()}>
              <label>Size:</label>
              <select 
                value={selectedSize}
                onChange={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  setSelectedSize(e.target.value)
                }}
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                }}
              >
                <option value="">Select...</option>
                {sizes.map(size => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </select>
            </div>
          )}
          <button 
            className="pc-add-btn"
            onClick={handleAddToCart}
            disabled={isAdding || (sizes.length > 0 && !selectedSize)}
          >
            {isAdding ? '⏳ Adding...' : '🛒 Add to Cart'}
          </button>
        </div>
      )}
    </>
  )
  
  if (product.product_url) {
    return (
      <article 
        className="product-card"
        style={{
          background: 'linear-gradient(160deg, #0f172a 0%, #1e293b 65%, #0f3a5b 100%)',
          border: '1px solid rgba(148,163,184,0.25)',
          boxShadow: '0 12px 24px rgba(2,6,23,0.3)',
          color: '#e2e8f0',
        }}
        onMouseEnter={() => setIsHovering(true)}
        onMouseLeave={() => setIsHovering(false)}
      >
        <a href={product.product_url} target="_blank" rel="noopener noreferrer">
          {CardContent}
        </a>
      </article>
    )
  }
  
  return (
    <article
      className="product-card"
      style={{
        background: 'linear-gradient(160deg, #0f172a 0%, #1e293b 65%, #0f3a5b 100%)',
        border: '1px solid rgba(148,163,184,0.25)',
        boxShadow: '0 12px 24px rgba(2,6,23,0.3)',
        color: '#e2e8f0',
      }}
    >
      {CardContent}
    </article>
  )
}
