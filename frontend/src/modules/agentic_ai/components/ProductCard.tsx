import React, { useState } from 'react'

export type Product = {
  id: string
  name: string
  price_LKR?: number
  personalization_score?: number
  why?: string[]
  available_sizes?: string[]
  size_stock?: Record<string, number>
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
  
  // Prefer stock-aware available_sizes from backend, fallback to size_range.
  const sizes = Array.isArray(product.available_sizes) && product.available_sizes.length > 0
    ? product.available_sizes
    : (product.size_range
      ? product.size_range.split(',').map(s => s.trim()).filter(s => s)
      : [])
  
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
      {sizes.length > 0 && <div className="pc-sizes">Sizes: {sizes.join(', ')}</div>}

      {product.why && product.why.length > 0 && (
        <ul className="pc-why">
          {product.why.map((w, i) => (
            <li key={`why-${i}-${w.substring(0, 10)}`}>{w}</li>
          ))}
        </ul>
      )}
      
      {/* Match scores are intentionally hidden from card UI. */}
      
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
