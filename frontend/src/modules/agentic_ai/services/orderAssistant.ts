export type OrderAssistantProduct = {
  shop?: string
  name?: string
  title?: string
  seller?: string
  image?: string
  price?: number
  currency?: string
  available_options?: string[]
  available_colors?: string[]
  variants?: {
    sizes?: string[]
    colors?: string[]
  }
  availability?: string
  stock_count?: number | null
  shipping_availability?: string
  shipping_fee?: number
  url?: string
  checkout_url?: string
  buy_now_url?: string
  add_to_cart_url?: string
}

export type OrderAssistantSummary = {
  currency?: string
  unit_price?: number
  quantity?: number
  shipping_fee?: number
  total_cost?: number
}

export type OrderAssistantProfile = {
  user_id?: string
  name?: string
  email?: string
  phone?: string
  shipping_address?: string
}

export type OrderAssistantResponse = {
  session_id: string
  state: string
  reply: string
  checkout_url?: string
  input_type?: 'text' | 'select'
  options?: string[]
  product?: OrderAssistantProduct
  profile?: OrderAssistantProfile
  summary?: OrderAssistantSummary
  requires_input?: boolean
  completed?: boolean
  detail?: string
}

export async function sendOrderAssistantMessage(
  apiBase: string,
  payload: { text?: string; session_id?: string; user_id?: string; profile?: OrderAssistantProfile },
): Promise<OrderAssistantResponse> {
  const res = await fetch(`${apiBase}/order-assistant/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    const errorText = await res.text()
    throw new Error(errorText || `Order assistant request failed with ${res.status}`)
  }

  const data = (await res.json()) as OrderAssistantResponse
  return data
}
