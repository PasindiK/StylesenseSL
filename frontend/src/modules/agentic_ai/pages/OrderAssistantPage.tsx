import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Star } from 'lucide-react'
import {
  sendOrderAssistantMessage,
  type OrderAssistantProfile,
  type OrderAssistantProduct,
  type OrderAssistantResponse,
  type OrderAssistantSummary,
} from '../services/orderAssistant'

// Guard cart-checkout handoff against duplicate processing (e.g. StrictMode remount in dev).
const consumedCheckoutRequestIdsGlobal = new Set<string>()

function nowText() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
}

function isJunkInput(value: string) {
  const text = value.trim()
  if (!text) return true
  if (text.length < 2) return true
  const alphaChars = (text.match(/[a-z]/gi) || []).length
  if (alphaChars === 0) return true
  if (/^[^a-z0-9]+$/i.test(text)) return true
  return false
}

function shouldAutoConfirm(response: OrderAssistantResponse) {
  return response.state === 'await_start_confirmation'
}

type ChatMessage = {
  id: string
  sender: 'assistant' | 'user'
  text: string
  at: string
  product?: OrderAssistantProduct
  summary?: OrderAssistantSummary
  profile?: OrderAssistantProfile
  selection?: SelectionDraft
  pendingLink?: string
}

type SelectionDraft = {
  quantity: number
  size?: string
  color?: string
}

type ShopifyVariantMap = Record<string, number>

type EditableProfile = OrderAssistantProfile
type SatisfactionAction = 'checkout' | 'add_to_cart'

type PriceBreakdown = {
  currency: string
  baseTotal: number
  shippingFee: number
  checkoutTotal: number
  shippingText: string
}

function hasValue(value: unknown) {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim() !== '' && value.trim().toLowerCase() !== 'n/a'
  return true
}

function looksLikeUrl(value: string) {
  return /^https?:\/\/\S+$/i.test(value.trim())
}

function buildSelectedProductUrl(url: string | undefined, selection: SelectionDraft) {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    if (selection.size) {
      parsed.searchParams.set('size', selection.size)
      parsed.searchParams.set('variant', selection.size)
      parsed.searchParams.set('option', selection.size)
    }
    if (selection.color) parsed.searchParams.set('color', selection.color)
    if (selection.quantity > 0) parsed.searchParams.set('quantity', String(selection.quantity))
    return parsed.toString()
  } catch {
    return url
  }
}

function normalizeVariantToken(value: string | undefined) {
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '')
}

function parseVariantIdFromAddToCartUrl(url: string | undefined) {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    const idParam = parsed.searchParams.get('id')
    if (idParam && /^\d+$/.test(idParam)) {
      return Number(idParam)
    }

    const pathMatch = parsed.pathname.match(/\/cart\/(\d+)(?::\d+)?/i)
    if (pathMatch?.[1]) {
      return Number(pathMatch[1])
    }
  } catch {
    return undefined
  }
  return undefined
}

function resolveVariantIdForSelection(variantMap: ShopifyVariantMap | undefined, selection: SelectionDraft) {
  if (!variantMap) return undefined

  const desiredSize = normalizeVariantToken(selection.size)
  const desiredColor = normalizeVariantToken(selection.color)

  for (const [compoundKey, variantId] of Object.entries(variantMap)) {
    const entries = compoundKey.split('|').map((pair) => {
      const [key, value] = pair.split(':')
      return { key: String(key || '').toLowerCase(), value: normalizeVariantToken(value) }
    })

    if (desiredSize) {
      const sizeEntry = entries.find((entry) => entry.key.includes('size') || entry.key === 'option1')
      if (!sizeEntry || sizeEntry.value !== desiredSize) {
        continue
      }
    }

    if (desiredColor) {
      const colorEntry = entries.find((entry) => entry.key.includes('color') || entry.key.includes('colour'))
      if (!colorEntry || colorEntry.value !== desiredColor) {
        continue
      }
    }

    return variantId
  }

  return undefined
}

function buildExternalSiteCartUrl(product: OrderAssistantProduct, selection: SelectionDraft) {
  const baseProductUrl = product.url
  const addToCartUrl = product.add_to_cart_url
  const qty = Math.max(1, Number(selection.quantity || 1))

  const isShopifyProduct = Boolean(baseProductUrl && /\/products\/[^/?#]+/i.test(baseProductUrl))
  if (isShopifyProduct && baseProductUrl) {
    let shopifyVariantMap: ShopifyVariantMap | undefined
    if (product.variants && typeof product.variants === 'object') {
      const rawMap = (product.variants as { shopify_variant_map?: ShopifyVariantMap }).shopify_variant_map
      if (rawMap && typeof rawMap === 'object') {
        shopifyVariantMap = rawMap
      }
    }

    const variantId =
      resolveVariantIdForSelection(shopifyVariantMap, selection) ||
      parseVariantIdFromAddToCartUrl(addToCartUrl)

    if (variantId) {
      try {
        const parsed = new URL(baseProductUrl)
        const addUrl = new URL(`${parsed.protocol}//${parsed.host}/cart/add`)
        addUrl.searchParams.set('id', String(variantId))
        addUrl.searchParams.set('quantity', String(qty))
        addUrl.searchParams.set('return_to', '/cart')
        return addUrl.toString()
      } catch {
        return undefined
      }
    }

    return undefined
  }

  if (addToCartUrl) {
    const lower = addToCartUrl.toLowerCase()
    if (lower.includes('checkout')) {
      return undefined
    }

    try {
      const parsedAddUrl = new URL(addToCartUrl)
      if (parsedAddUrl.pathname.toLowerCase().includes('/cart/add')) {
        parsedAddUrl.searchParams.set('quantity', String(qty))
        if (!parsedAddUrl.searchParams.has('return_to')) {
          parsedAddUrl.searchParams.set('return_to', '/cart')
        }
        return parsedAddUrl.toString()
      }
    } catch {
      return buildSelectedProductUrl(addToCartUrl, selection)
    }

    return buildSelectedProductUrl(addToCartUrl, selection)
  }

  return undefined
}

function computePriceBreakdown(product: OrderAssistantProduct, selection: SelectionDraft): PriceBreakdown {
  const currency = String(product.currency || 'LKR').toUpperCase()
  const unitPrice = Number(product.price || 0)
  const quantity = Math.max(1, Number(selection.quantity || 1))
  const baseTotal = unitPrice * quantity

  const explicitShipping = product.shipping_fee
  let shippingFee = 0
  let shippingText = 'Shipping at checkout'

  if (typeof explicitShipping === 'number' && Number.isFinite(explicitShipping) && explicitShipping >= 0) {
    shippingFee = explicitShipping
    shippingText = explicitShipping > 0 ? '+ shipping' : 'Free Shipping'
  }

  return {
    currency,
    baseTotal,
    shippingFee,
    checkoutTotal: baseTotal + shippingFee,
    shippingText,
  }
}

function shouldAttachSelectionCard(state: string) {
  return (
    state === 'await_summary_confirmation' ||
    state === 'await_checkout_action' ||
    state === 'await_profile_confirmation' ||
    state === 'await_payment_method' ||
    state === 'await_payment_completion' ||
    state === 'await_final_confirmation'
  )
}

function isSelectionState(state: string) {
  return state === 'await_quantity' || state === 'await_variant' || state === 'await_color'
}

function normalizeOptionValues(value: unknown): string[] {
  const cleanOption = (raw: string) =>
    raw
      .replace(/\((?:out\s*of\s*stock|sold\s*out|unavailable)\)/gi, '')
      .replace(/[-:]\s*(?:out\s*of\s*stock|sold\s*out|unavailable)\b/gi, '')
      .trim()

  const isUnavailableOption = (raw: string) => /out\s*of\s*stock|sold\s*out|unavailable|not\s*available/i.test(raw)

  if (Array.isArray(value)) {
    return value
      .map((v) => String(v).trim())
      .filter((v) => !isUnavailableOption(v))
      .map((v) => cleanOption(v))
      .filter((v) => hasValue(v))
  }
  if (typeof value === 'string') {
    return value
      .split(/[|,]/g)
      .map((v) => v.trim())
      .filter((v) => !isUnavailableOption(v))
      .map((v) => cleanOption(v))
      .filter((v) => hasValue(v))
  }
  return []
}

function isOutOfStockAvailability(value: unknown) {
  const text = String(value || '').toLowerCase().trim()
  if (!text) return false
  return /out\s*of\s*stock|sold\s*out|unavailable|not\s*available|no\s*stock/.test(text)
}

function formatAvailabilityLabel(value: unknown) {
  const raw = String(value || '').trim()
  if (!raw) return 'Unknown'
  const lower = raw.toLowerCase()

  if (lower.includes('schema.org/outofstock') || isOutOfStockAvailability(raw)) {
    return 'Out of stock'
  }
  if (lower.includes('schema.org/instock') || /in\s*stock|available/.test(lower)) {
    return 'In stock'
  }
  return raw
}

function canonicalChoice(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '')
}

function matchesAvailableOption(selected: string, option: string) {
  const selectedKey = canonicalChoice(selected)
  const optionKey = canonicalChoice(option)
  if (!selectedKey || !optionKey) return false
  return selectedKey === optionKey || optionKey.includes(selectedKey)
}

function extractListFromReply(reply: string, label: 'sizes' | 'colors'): string[] {
  const pattern = label === 'sizes' ? /Available\s+sizes:\s*([^\n]+)/i : /Available\s+colors:\s*([^\n]+)/i
  const match = reply.match(pattern)
  if (!match || !match[1]) return []
  return normalizeOptionValues(match[1])
}

export default function OrderAssistantPage({
  userId,
  onOpenShoppingCart,
  checkoutRequest,
  onCheckoutRequestConsumed,
  automationSettings,
  onCartUpdated,
}: {
  userId?: string
  onOpenShoppingCart?: () => void | Promise<void>
  checkoutRequest?: {
    id: string
    url: string
    quantity?: number
    size?: string
    color?: string
    name?: string
  }
  onCheckoutRequestConsumed?: () => void
  automationSettings?: {
    auto_fill_checkout?: boolean
    auto_apply_preferences?: boolean
    confirm_before_checkout?: boolean
  }
  onCartUpdated?: () => void | Promise<void>
}) {
  const [sessionId, setSessionId] = useState<string>('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [isScraping, setIsScraping] = useState(false)
  const [pendingInputType, setPendingInputType] = useState<'text' | 'select'>('text')
  const [pendingOptions, setPendingOptions] = useState<string[]>([])
  const [pendingState, setPendingState] = useState<string>('')
  const [editableProfile, setEditableProfile] = useState<EditableProfile | null>(null)
  const [profileEditMode, setProfileEditMode] = useState(false)
  const [selectionPromptShown, setSelectionPromptShown] = useState(false)
  const [selectionDraft, setSelectionDraft] = useState<SelectionDraft>({ quantity: 1 })
  const [currentProduct, setCurrentProduct] = useState<OrderAssistantProduct | null>(null)
  const [detectedSizes, setDetectedSizes] = useState<string[]>([])
  const [detectedColors, setDetectedColors] = useState<string[]>([])
  const [pendingReplacementLink, setPendingReplacementLink] = useState<string | null>(null)
  const [isCartCheckoutFlow, setIsCartCheckoutFlow] = useState(false)
  const [profileCheckoutOnlyMode, setProfileCheckoutOnlyMode] = useState(false)
  const [pendingSatisfactionAction, setPendingSatisfactionAction] = useState<SatisfactionAction | null>(null)
  const [selectedSatisfactionStars, setSelectedSatisfactionStars] = useState(0)
  const [satisfactionSubmitting, setSatisfactionSubmitting] = useState(false)
  const [satisfactionMessage, setSatisfactionMessage] = useState<string | null>(null)
  const messageListRef = useRef<HTMLDivElement | null>(null)

  const effectiveAutomation = useMemo(
    () => ({
      auto_fill_checkout: automationSettings?.auto_fill_checkout !== false,
      auto_apply_preferences: automationSettings?.auto_apply_preferences !== false,
      confirm_before_checkout: automationSettings?.confirm_before_checkout !== false,
    }),
    [automationSettings],
  )

  function addUserActionMessage(text: string) {
    const cleaned = text.trim()
    if (!cleaned) return
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        sender: 'user',
        text: cleaned,
        at: nowText(),
      },
    ])
  }

  async function submitSatisfactionRating(rating: number) {
    if (!pendingSatisfactionAction || !sessionId || satisfactionSubmitting) return
    setSatisfactionSubmitting(true)
    setSatisfactionMessage(null)
    try {
      const res = await fetch(`${apiBase}/order-assistant/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          session_id: sessionId,
          action: pendingSatisfactionAction,
          rating,
        }),
      })
      if (!res.ok) {
        const txt = await res.text()
        setSatisfactionMessage(`Could not save rating (${res.status}): ${txt}`)
        return
      }
      setSelectedSatisfactionStars(rating)
      setSatisfactionMessage('Thanks! Rating captured.')
      setPendingSatisfactionAction(null)
    } catch {
      setSatisfactionMessage('Could not save rating right now.')
    } finally {
      setSatisfactionSubmitting(false)
    }
  }

  function resetSelectionContext() {
    setSelectionDraft({ quantity: 1 })
    setCurrentProduct(null)
    setDetectedSizes([])
    setDetectedColors([])
    setSelectionPromptShown(false)
  }

  function shouldAskBeforeReplacingLink() {
    if (!currentProduct) return false
    return !['await_start_confirmation', 'await_product_link', 'canceled', 'completed'].includes(pendingState)
  }

  async function processProductLink(link: string, sessionForRequest?: string) {
    resetSelectionContext()
    setIsScraping(true)
    try {
      let activeSession = sessionForRequest || sessionId
      if (pendingState === 'await_start_confirmation') {
        const initResponse = await sendOrderAssistantMessage(apiBase, {
          text: 'yes',
          session_id: activeSession,
          user_id: userId,
        })
        activeSession = initResponse.session_id
        setSessionId(initResponse.session_id)
        setPendingInputType(initResponse.input_type || 'text')
        setPendingOptions(Array.isArray(initResponse.options) ? initResponse.options : [])
        setPendingState(initResponse.state || '')
      }

      const response = await sendOrderAssistantMessage(apiBase, {
        text: link,
        session_id: activeSession,
        user_id: userId,
      })
      await applyAssistantResponse(response)
      return response
    } finally {
      setIsScraping(false)
    }
  }

  function resolveRequestedChoice(requested: string | undefined, options: string[]) {
    const cleanOptions = options.map((opt) => String(opt).trim()).filter(Boolean)
    const requestedValue = String(requested || '').trim()
    if (!requestedValue) return cleanOptions[0] || 'N/A'
    const directMatch = cleanOptions.find((opt) => matchesAvailableOption(requestedValue, opt))
    return directMatch || requestedValue
  }

  async function autoAdvanceCartCheckoutFlow(
    initialResponse: OrderAssistantResponse | undefined,
    request: {
      quantity?: number
      size?: string
      color?: string
    },
  ) {
    let response = initialResponse
    let nextSessionId = response?.session_id || sessionId
    let nextState = response?.state || pendingState

    let chosenQuantity = Math.max(1, Number(request.quantity || 1))
    let chosenSize = request.size
    let chosenColor = request.color

    for (let i = 0; i < 8; i += 1) {
      let textToSend: string | null = null

      if (nextState === 'await_quantity') {
        textToSend = String(chosenQuantity)
      } else if (nextState === 'await_variant') {
        const options = Array.isArray(response?.options) ? response?.options : []
        chosenSize = resolveRequestedChoice(chosenSize, options)
        textToSend = chosenSize
      } else if (nextState === 'await_color') {
        const options = Array.isArray(response?.options) ? response?.options : []
        chosenColor = resolveRequestedChoice(chosenColor, options)
        textToSend = chosenColor
      } else if (nextState === 'await_summary_confirmation') {
        textToSend = 'yes'
      } else if (nextState === 'await_checkout_action') {
        textToSend = 'Buy Now'
      } else {
        break
      }

      response = await sendOrderAssistantMessage(apiBase, {
        text: textToSend,
        session_id: nextSessionId,
        user_id: userId,
      })
      nextSessionId = response.session_id
      nextState = response.state

      if (nextState === 'await_profile_confirmation') {
        setProfileCheckoutOnlyMode(true)
        break
      }
    }

    setSelectionDraft({
      quantity: chosenQuantity,
      size: chosenSize || undefined,
      color: chosenColor || undefined,
    })

    if (response) {
      await applyAssistantResponse(response)
    }
  }

  async function handleReplacementLinkChoice(yes: boolean, link: string) {
    setPendingReplacementLink(null)
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        sender: 'user',
        text: yes ? 'Yes' : 'No',
        at: nowText(),
      },
    ])

    if (!yes) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: 'Okay, I will continue with your current product flow.',
          at: nowText(),
        },
      ])
      return
    }

    setLoading(true)
    try {
      await processProductLink(link)
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: `Request failed: ${String(err)}`,
          at: nowText(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const apiBase = useMemo(() => {
    if (typeof window !== 'undefined' && (window as { VITE_API_URL?: string }).VITE_API_URL) {
      return (window as { VITE_API_URL?: string }).VITE_API_URL || '/api'
    }
    return (typeof import.meta !== 'undefined' && (import.meta.env.VITE_API_URL as string)) || '/api'
  }, [])

  useEffect(() => {
    let active = true
    const bootstrapSession = async () => {
      setLoading(true)
      try {
        const response = await sendOrderAssistantMessage(apiBase, { user_id: userId })
        if (!active) return
        setSessionId(response.session_id)
        setPendingInputType(response.input_type || 'text')
        setPendingOptions(Array.isArray(response.options) ? response.options : [])
        setPendingState(response.state || '')
      } catch (err) {
        if (!active) return
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: `Unable to start order assistant: ${String(err)}`,
            at: nowText(),
          },
        ])
      } finally {
        if (active) setLoading(false)
      }
    }

    bootstrapSession()
    return () => {
      active = false
    }
  }, [apiBase, userId])

  useEffect(() => {
    const list = messageListRef.current
    if (!list) return
    requestAnimationFrame(() => {
      list.scrollTop = list.scrollHeight
    })
  }, [messages, loading])

  useEffect(() => {
    const bootstrapCheckoutFromCart = async () => {
      if (!checkoutRequest || !sessionId || loading) return
      if (!checkoutRequest.url || consumedCheckoutRequestIdsGlobal.has(checkoutRequest.id)) return

      consumedCheckoutRequestIdsGlobal.add(checkoutRequest.id)
      onCheckoutRequestConsumed?.()

      addUserActionMessage('Checkout')

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: `Starting checkout flow for ${checkoutRequest.name || 'selected cart item'}. I will now verify product details, then we will confirm your user details before payment.`,
          at: nowText(),
        },
      ])

      setLoading(true)
      setIsCartCheckoutFlow(true)
      try {
        const initial = await processProductLink(checkoutRequest.url, sessionId)
        if (isOutOfStockAvailability(initial?.product?.availability)) {
          return
        }
        await autoAdvanceCartCheckoutFlow(initial, {
          quantity: checkoutRequest.quantity,
          size: checkoutRequest.size,
          color: checkoutRequest.color,
        })
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: `Could not start checkout from cart item: ${String(err)}`,
            at: nowText(),
          },
        ])
      } finally {
        setIsCartCheckoutFlow(false)
        setLoading(false)
      }
    }

    void bootstrapCheckoutFromCart()
  }, [checkoutRequest, sessionId, loading])

  async function submitTextMessage(text: string) {
    const cleaned = text.trim()
    if (!cleaned || !sessionId || loading) return
    const isLinkInput = looksLikeUrl(cleaned)

    if (!isLinkInput) {
      if (pendingState === 'await_quantity') {
        const q = Number.parseInt(cleaned, 10)
        if (Number.isFinite(q) && q > 0) {
          setSelectionDraft((prev) => ({ ...prev, quantity: q }))
        }
      }
      if (pendingState === 'await_variant') {
        setSelectionDraft((prev) => ({ ...prev, size: cleaned }))
      }
      if (pendingState === 'await_color') {
        setSelectionDraft((prev) => ({ ...prev, color: cleaned }))
      }
    }

    if (isJunkInput(cleaned)) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: 'I am your Order Assistant agent. Please send a clear message, for example: paste a product link, or choose a quick action at the top.',
          at: nowText(),
        },
      ])
      return
    }

    const userMessage: ChatMessage = { id: crypto.randomUUID(), sender: 'user', text: cleaned, at: nowText() }
    setMessages((prev) => [...prev, userMessage])

    if (isLinkInput && shouldAskBeforeReplacingLink()) {
      setPendingReplacementLink(cleaned)
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: 'Do you want me to proceed with this new product link?',
          pendingLink: cleaned,
          at: nowText(),
        },
      ])
      setInput('')
      return
    }

    setInput('')
    setLoading(true)

    try {
      if (isLinkInput) {
        await processProductLink(cleaned, sessionId)
      } else {
        const response = await sendOrderAssistantMessage(apiBase, { text: cleaned, session_id: sessionId, user_id: userId })
        await applyAssistantResponse(response)
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: `Request failed: ${String(err)}`,
          at: nowText(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (isSelectionState(pendingState)) {
      await submitCombinedSelection()
      return
    }
    const text = input.trim()
    await submitTextMessage(text)
  }

  async function applyAssistantResponse(response: OrderAssistantResponse, depth = 0): Promise<void> {
    setSessionId(response.session_id)
    setPendingInputType(response.input_type || 'text')
    setPendingOptions(Array.isArray(response.options) ? response.options : [])
    setPendingState(response.state || '')

    if (response.state === 'await_product_confirmation') {
      if (response.product) {
        setCurrentProduct(response.product)
      }
      const parsedSizes = [
        ...normalizeOptionValues(response.product?.available_options),
        ...normalizeOptionValues(response.product?.variants?.sizes),
        ...extractListFromReply(response.reply, 'sizes'),
      ]
      const parsedColors = [
        ...normalizeOptionValues(response.product?.available_colors),
        ...normalizeOptionValues(response.product?.variants?.colors),
        ...extractListFromReply(response.reply, 'colors'),
      ]
      setDetectedSizes(Array.from(new Set(parsedSizes)))
      setDetectedColors(Array.from(new Set(parsedColors)))
      setSelectionPromptShown(false)
      // Cart-triggered checkout already has item context; avoid rendering a duplicate product card.
      if (!isCartCheckoutFlow) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: '',
            at: nowText(),
            product: response.product,
            profile: response.profile,
          },
        ])
      }

      if (isOutOfStockAvailability(response.product?.availability)) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: 'This product is currently out of stock. Please share another product URL to continue.',
            at: nowText(),
          },
        ])

        if (depth < 5) {
          const next = await sendOrderAssistantMessage(apiBase, {
            text: 'no',
            session_id: response.session_id,
            user_id: userId,
          })
          setSessionId(next.session_id)
          setPendingInputType(next.input_type || 'text')
          setPendingOptions(Array.isArray(next.options) ? next.options : [])
          setPendingState(next.state || 'await_product_link')
        }
        return
      }

      if (depth < 5) {
        const next = await sendOrderAssistantMessage(apiBase, {
          text: 'yes',
          session_id: response.session_id,
          user_id: userId,
        })
        await applyAssistantResponse(next, depth + 1)
      }
      return
    }

    if (shouldAutoConfirm(response) && depth < 5) {
      const next = await sendOrderAssistantMessage(apiBase, {
        text: 'yes',
        session_id: response.session_id,
        user_id: userId,
      })
      await applyAssistantResponse(next, depth + 1)
      return
    }

    if (isSelectionState(response.state)) {
      if (isCartCheckoutFlow) {
        if (response.product) {
          setCurrentProduct(response.product)
        }
        return
      }

      if (!selectionPromptShown) setSelectionPromptShown(true)
      if (response.product) {
        setCurrentProduct(response.product)
      }
      return
    }

    if (response.state === 'await_profile_confirmation' && !effectiveAutomation.auto_fill_checkout && depth < 5) {
      const next = await sendOrderAssistantMessage(apiBase, {
        text: 'yes',
        session_id: response.session_id,
        user_id: userId,
      })
      await applyAssistantResponse(next, depth + 1)
      return
    }

    if (response.state === 'await_checkout_action' && !effectiveAutomation.confirm_before_checkout && depth < 5) {
      addUserActionMessage('Buy Now')
      const next = await sendOrderAssistantMessage(apiBase, {
        text: 'Buy Now',
        session_id: response.session_id,
        user_id: userId,
      })
      await applyAssistantResponse(next, depth + 1)
      if (next.checkout_url && typeof window !== 'undefined') {
        window.open(next.checkout_url, '_blank', 'noopener,noreferrer')
      }
      return
    }

    setSelectionPromptShown(false)

    const hasSelectionChanges = !!selectionDraft.size || !!selectionDraft.color || selectionDraft.quantity !== 1
    const baseProduct = response.product || currentProduct
    const selectionAppliedProduct =
      baseProduct && hasSelectionChanges && shouldAttachSelectionCard(response.state)
        ? {
            ...baseProduct,
            url: buildSelectedProductUrl(baseProduct.url, selectionDraft),
          }
        : response.product

    const assistantText =
      (response.state === 'await_summary_confirmation' || response.state === 'await_profile_confirmation') &&
      (selectionAppliedProduct || response.profile)
        ? ''
        : response.reply

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        sender: 'assistant',
        text: assistantText,
        at: nowText(),
        product: selectionAppliedProduct,
        summary: response.summary,
        profile: response.profile,
        selection: selectionAppliedProduct ? { ...selectionDraft } : undefined,
      },
    ])

    if (response.profile) {
      setEditableProfile(response.profile)
    }

    if (response.product) {
      setCurrentProduct(response.product)
    }
  }

  const disableTextInputForState = false

  const availableSizes = useMemo(() => {
    const fromProduct = [
      ...normalizeOptionValues(currentProduct?.available_options),
      ...normalizeOptionValues(currentProduct?.variants?.sizes),
    ]
      .filter((opt) => hasValue(opt))
      .map((opt) => String(opt).trim())
    if (fromProduct.length > 0) return Array.from(new Set(fromProduct))
    if (detectedSizes.length > 0) return detectedSizes
    if (pendingState === 'await_variant') return pendingOptions.filter((opt) => hasValue(opt))
    return [] as string[]
  }, [currentProduct, detectedSizes, pendingState, pendingOptions])

  const availableColors = useMemo(() => {
    const fromProduct = [
      ...normalizeOptionValues(currentProduct?.available_colors),
      ...normalizeOptionValues(currentProduct?.variants?.colors),
    ]
      .filter((opt) => hasValue(opt))
      .map((opt) => String(opt).trim())
    if (fromProduct.length > 0) return Array.from(new Set(fromProduct))
    if (detectedColors.length > 0) return detectedColors
    if (pendingState === 'await_color') return pendingOptions.filter((opt) => hasValue(opt))
    return [] as string[]
  }, [currentProduct, detectedColors, pendingState, pendingOptions])

  const showCombinedSelector = isSelectionState(pendingState) && !isCartCheckoutFlow

  useEffect(() => {
    if (pendingState !== 'await_profile_confirmation') {
      setProfileCheckoutOnlyMode(false)
    }
  }, [pendingState])

  function adjustQuantity(delta: number) {
    setSelectionDraft((prev) => {
      const next = Math.max(1, Math.min(20, prev.quantity + delta))
      return { ...prev, quantity: next }
    })
  }

  async function submitQuantitySelector() {
    if (loading) return
    await submitTextMessage(String(selectionDraft.quantity))
  }

  async function submitCombinedSelection() {
    if (!sessionId || loading) return

    if (!Number.isFinite(selectionDraft.quantity) || selectionDraft.quantity < 1 || selectionDraft.quantity > 20) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: 'Please enter a valid quantity between 1 and 20.',
          at: nowText(),
        },
      ])
      return
    }

    const selectedSize = selectionDraft.size?.trim()
    const selectedColor = selectionDraft.color?.trim()

    if (availableSizes.length > 0) {
      if (!selectedSize || !availableSizes.some((opt) => matchesAvailableOption(selectedSize, opt))) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: 'Please select a valid size from the available options.',
            at: nowText(),
          },
        ])
        return
      }
    }

    if (availableColors.length > 0) {
      if (!selectedColor || !availableColors.some((opt) => matchesAvailableOption(selectedColor, opt))) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: 'Please select a valid color from the available options.',
            at: nowText(),
          },
        ])
        return
      }
    }

    const summaryParts = [`quantity: ${selectionDraft.quantity}`]
    if (selectedSize) summaryParts.push(`size: ${selectedSize}`)
    if (selectedColor) summaryParts.push(`color: ${selectedColor}`)

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        sender: 'user',
        text: summaryParts.join(', '),
        at: nowText(),
      },
    ])

    setLoading(true)
    try {
      let nextState = pendingState
      let nextSessionId = sessionId
      let finalResponse: OrderAssistantResponse | null = null

      for (let i = 0; i < 6; i += 1) {
        let messageToSend = ''

        if (nextState === 'await_quantity') {
          messageToSend = String(selectionDraft.quantity)
        } else if (nextState === 'await_variant') {
          if (!selectedSize) break
          messageToSend = selectedSize
        } else if (nextState === 'await_color') {
          if (!selectedColor) break
          messageToSend = selectedColor
        } else {
          break
        }

        const response = await sendOrderAssistantMessage(apiBase, {
          text: messageToSend,
          session_id: nextSessionId,
          user_id: userId,
        })

        finalResponse = response
        nextSessionId = response.session_id
        nextState = response.state
        setSessionId(response.session_id)
        setPendingInputType(response.input_type || 'text')
        setPendingOptions(Array.isArray(response.options) ? response.options : [])
        setPendingState(response.state || '')

        if (!isSelectionState(response.state)) break
      }

      if (finalResponse) {
        await applyAssistantResponse(finalResponse)
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: `Request failed: ${String(err)}`,
          at: nowText(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  async function addToGlobalCart(product: OrderAssistantProduct, selection: SelectionDraft) {
    const targetUrl = buildSelectedProductUrl(product.url, selection)
    if (!targetUrl) {
      throw new Error('No product URL available for cart action.')
    }

    const res = await fetch(`${apiBase}/cart/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: targetUrl,
        quantity: selection.quantity,
        size: selection.size,
        color: selection.color,
      }),
    })

    const payloadText = await res.text()
    if (!res.ok) {
      throw new Error(payloadText || `Cart add failed with ${res.status}`)
    }

    let payload: { success?: boolean; message?: string; error?: string } = {}
    try {
      payload = JSON.parse(payloadText) as { success?: boolean; message?: string; error?: string }
    } catch {
      payload = { success: true }
    }

    if (payload.success === false) {
      throw new Error(payload.error || 'Could not add item to app cart.')
    }
  }

  async function handleActionBubbleClick(kind: 'checkout' | 'add-to-cart', product: OrderAssistantProduct, selection: SelectionDraft) {
    const filteredProductUrl = buildSelectedProductUrl(product.url, selection)
    const filteredCheckoutUrl = buildSelectedProductUrl(product.buy_now_url || product.checkout_url || product.url, selection)
    const externalSiteCartUrl = buildExternalSiteCartUrl(product, selection)

    if (kind === 'add-to-cart') {
      addUserActionMessage('Add to Cart')
      setLoading(true)
      try {
        await addToGlobalCart(product, selection)
        let openedSiteCart = false
        if (externalSiteCartUrl && typeof window !== 'undefined') {
          window.open(externalSiteCartUrl, '_blank', 'noopener,noreferrer')
          openedSiteCart = true
        }
        if (onOpenShoppingCart) {
          await onOpenShoppingCart()
        }
        if (onCartUpdated) {
          await onCartUpdated()
        }
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: openedSiteCart
              ? 'Added to site cart and app global cart.'
              : 'Added to app global cart. External site cart link is unavailable for this product/selection.',
            at: nowText(),
          },
        ])
        setPendingSatisfactionAction('add_to_cart')
        setSelectedSatisfactionStars(0)
        setSatisfactionMessage('How satisfied are you with this Add to Cart experience?')
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: `Add to cart failed: ${String(err)}`,
            at: nowText(),
          },
        ])
      } finally {
        setLoading(false)
      }
      return
    }

    setLoading(true)
    try {
      addUserActionMessage('Checkout')

      if (pendingState === 'await_profile_confirmation') {
        if (effectiveAutomation.auto_fill_checkout) {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              sender: 'assistant',
              text: 'Please confirm your user details first using the Confirm Details button.',
              at: nowText(),
            },
          ])
          return
        }
      }

      if (pendingState === 'await_order_placed_confirmation') {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            sender: 'assistant',
            text: 'Please answer whether you placed the order: Yes or No.',
            at: nowText(),
          },
        ])
        return
      }

      let latestResponse: OrderAssistantResponse | null = null
      let checkoutTargetFromApi: string | undefined

      const sendStep = async (text: string) => {
        latestResponse = await sendOrderAssistantMessage(apiBase, {
          text,
          session_id: sessionId,
          user_id: userId,
          profile: editableProfile || undefined,
        })
        if (latestResponse.checkout_url) {
          checkoutTargetFromApi = latestResponse.checkout_url
        }
        return latestResponse
      }

      if (filteredProductUrl) {
        // Keep backend order session aligned with the card selection before checkout.
        if (pendingState === 'await_summary_confirmation') {
          const updateParts = [`quantity ${selection.quantity}`]
          if (selection.size && selection.size !== 'N/A') updateParts.push(`size ${selection.size}`)
          if (selection.color && selection.color !== 'N/A') updateParts.push(`color ${selection.color}`)
          await sendStep(updateParts.join(' '))
        }

        let response: OrderAssistantResponse | null = null
        if (pendingState === 'await_summary_confirmation') {
          response = await sendStep('yes')
        } else if (pendingState === 'await_checkout_action') {
          response = await sendStep('Buy Now')
        } else {
          response = await sendStep('yes')
          if (response.state === 'await_checkout_action') {
            response = await sendStep('Buy Now')
          }
        }

        if (latestResponse) {
          await applyAssistantResponse(latestResponse)
        }

        // Checkout should open only after profile confirmation + Buy Now.
        if (response?.state === 'await_profile_confirmation') {
          return
        }
      }

      const checkoutTarget = checkoutTargetFromApi || filteredCheckoutUrl
      if (checkoutTarget && typeof window !== 'undefined') {
        window.open(checkoutTarget, '_blank', 'noopener,noreferrer')
        setPendingSatisfactionAction('checkout')
        setSelectedSatisfactionStars(0)
        setSatisfactionMessage('How satisfied are you with this Checkout flow?')
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: `Checkout flow failed: ${String(err)}`,
          at: nowText(),
        },
      ])
      if (filteredCheckoutUrl && typeof window !== 'undefined') {
        window.open(filteredCheckoutUrl, '_blank', 'noopener,noreferrer')
      }
    } finally {
      setLoading(false)
    }
  }

  function renderTextWithLinks(text: string) {
    const urlRegex = /(https?:\/\/[^\s]+)/g
    const lines = text.split('\n')

    return lines.map((line, lineIndex) => {
      const parts = line.split(urlRegex)
      return (
        <React.Fragment key={`line-${lineIndex}`}>
          {parts.map((part, partIndex) => {
            if (/^https?:\/\//i.test(part)) {
              return (
                <a
                  key={`link-${lineIndex}-${partIndex}`}
                  href={part}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: '#93c5fd', textDecoration: 'underline' }}
                >
                  {part}
                </a>
              )
            }
            return <React.Fragment key={`txt-${lineIndex}-${partIndex}`}>{part}</React.Fragment>
          })}
          {lineIndex < lines.length - 1 ? <br /> : null}
        </React.Fragment>
      )
    })
  }

  async function handleQuickAction(action: 'product-link' | 'cart-checkout') {
    if (action === 'product-link') {
      addUserActionMessage('I need to place an order with a link.')
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: 'Please paste the product link of the item you want to order.',
          at: nowText(),
        },
      ])
      return
    }

    if (onOpenShoppingCart) {
      await onOpenShoppingCart()
    }

    addUserActionMessage('Checkout')
    // Cart quick action should only show user action + open cart.
  }

  async function handleSaveProfile() {
    if (!sessionId || !editableProfile || loading) return
    addUserActionMessage('Save Profile')
    setLoading(true)
    try {
      const response = await sendOrderAssistantMessage(apiBase, {
        text: 'save profile',
        session_id: sessionId,
        user_id: userId,
        profile: editableProfile,
      })
      setProfileEditMode(false)
      await applyAssistantResponse(response)
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: `Profile save failed: ${String(err)}`,
          at: nowText(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirmProfileDetails() {
    if (!sessionId || loading) return
    const actionLabel = profileCheckoutOnlyMode ? 'Checkout' : 'Confirmed'
    addUserActionMessage(actionLabel)
    setLoading(true)
    try {
      const first = await sendOrderAssistantMessage(apiBase, {
        text: 'yes',
        session_id: sessionId,
        user_id: userId,
        profile: editableProfile || undefined,
      })
      await applyAssistantResponse(first)

      if (first.state === 'await_checkout_action') {
        addUserActionMessage('Buy Now')
        const second = await sendOrderAssistantMessage(apiBase, {
          text: 'Buy Now',
          session_id: first.session_id,
          user_id: userId,
          profile: editableProfile || undefined,
        })
        await applyAssistantResponse(second)
        if (second.checkout_url && typeof window !== 'undefined') {
          window.open(second.checkout_url, '_blank', 'noopener,noreferrer')
          setPendingSatisfactionAction('checkout')
          setSelectedSatisfactionStars(0)
          setSatisfactionMessage('How satisfied are you with this Checkout flow?')
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          text: `Profile confirmation failed: ${String(err)}`,
          at: nowText(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <section
      style={{
        borderRadius: 12,
        border: '1px solid rgba(148,163,184,0.25)',
        background: 'rgba(15,23,42,0.55)',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        height: '100%',
      }}
    >
      <header style={{ padding: '12px 14px 8px', borderBottom: '1px solid rgba(148,163,184,0.2)' }}>
        <h3 style={{ margin: 0, color: '#e2e8f0', fontSize: 18 }}>Order Assistant Chat Interface</h3>
      </header>

      <div style={{ padding: '10px 14px', borderBottom: '1px solid rgba(148,163,184,0.2)', display: 'grid', gap: 8 }}>
        <div style={{ color: '#94a3b8', fontSize: 12 }}>Quick actions:</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => handleQuickAction('product-link')}
            disabled={loading}
            style={{
              borderRadius: 999,
              border: '1px solid rgba(96,165,250,0.55)',
              background: 'rgba(37,99,235,0.28)',
              color: '#eff6ff',
              padding: '7px 12px',
              fontSize: 12,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            Want to place an order from a product link?
          </button>
          <button
            type="button"
            onClick={() => handleQuickAction('cart-checkout')}
            disabled={loading}
            style={{
              borderRadius: 999,
              border: '1px solid rgba(96,165,250,0.55)',
              background: 'rgba(37,99,235,0.28)',
              color: '#eff6ff',
              padding: '7px 12px',
              fontSize: 12,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            Want to checkout from shopping cart?
          </button>
        </div>
        {(pendingSatisfactionAction || satisfactionMessage) && (
          <div
            style={{
              marginTop: 2,
              borderRadius: 10,
              border: '1px solid rgba(148,163,184,0.3)',
              background: 'rgba(2,6,23,0.35)',
              padding: '8px 10px',
              display: 'grid',
              gap: 6,
            }}
          >
            <div style={{ fontSize: 12, color: '#cbd5e1' }}>
              {satisfactionMessage || 'Rate your recent action'}
            </div>
            {pendingSatisfactionAction && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {[1, 2, 3, 4, 5].map((star) => {
                  const active = selectedSatisfactionStars >= star
                  return (
                    <button
                      key={`satisfaction-star-${star}`}
                      type="button"
                      onClick={() => {
                        setSelectedSatisfactionStars(star)
                        void submitSatisfactionRating(star)
                      }}
                      disabled={satisfactionSubmitting}
                      style={{
                        border: 'none',
                        background: 'transparent',
                        padding: 0,
                        cursor: satisfactionSubmitting ? 'not-allowed' : 'pointer',
                        color: active ? '#facc15' : '#64748b',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                      title={`Rate ${star}`}
                      aria-label={`Rate ${star}`}
                    >
                      <Star size={18} fill={active ? '#facc15' : 'none'} />
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 12, padding: 14, flex: 1, minHeight: 0 }}>
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
          <div ref={messageListRef} style={{ overflowY: 'auto', display: 'grid', gap: 10, flex: 1, minHeight: 0 }}>
            {messages.map((m) => (
              <div
                key={m.id}
                style={{
                  justifySelf: m.sender === 'user' ? 'end' : 'start',
                  maxWidth: '88%',
                  padding: '10px 12px',
                  borderRadius: 10,
                  color: '#e2e8f0',
                  background: m.sender === 'user' ? 'rgba(37,99,235,0.35)' : 'rgba(2,6,23,0.52)',
                  border: '1px solid rgba(148,163,184,0.24)',
                  whiteSpace: 'pre-line',
                  fontSize: 13,
                  lineHeight: 1.45,
                }}
              >
                {m.sender === 'user' && (
                  <div style={{ fontSize: 11, color: '#93c5fd', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    You
                  </div>
                )}
                {m.sender === 'assistant' ? (m.text.trim() ? renderTextWithLinks(m.text) : null) : m.text}
                <div style={{ marginTop: 6, fontSize: 11, color: '#94a3b8', textAlign: 'right' }}>{m.at}</div>
                {m.sender === 'assistant' && m.pendingLink && pendingReplacementLink === m.pendingLink && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                    <button
                      type="button"
                      onClick={() => {
                        void handleReplacementLinkChoice(true, m.pendingLink as string)
                      }}
                      style={{
                        borderRadius: 999,
                        border: '1px solid rgba(16,185,129,0.55)',
                        background: 'rgba(16,185,129,0.18)',
                        color: '#dcfce7',
                        padding: '6px 12px',
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
                    >
                      Yes
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        void handleReplacementLinkChoice(false, m.pendingLink as string)
                      }}
                      style={{
                        borderRadius: 999,
                        border: '1px solid rgba(239,68,68,0.55)',
                        background: 'rgba(239,68,68,0.16)',
                        color: '#fee2e2',
                        padding: '6px 12px',
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
                    >
                      No
                    </button>
                  </div>
                )}
                {m.sender === 'assistant' && m.product && (
                  (() => {
                    const cardSelection = m.selection || { quantity: 1 }
                    const hasCardSelectionChanges = !!cardSelection.size || !!cardSelection.color || cardSelection.quantity !== 1
                    const breakdown = computePriceBreakdown(m.product, cardSelection)
                    const checkoutLink = buildSelectedProductUrl(m.product.buy_now_url || m.product.checkout_url || m.product.url, cardSelection)
                    const addToCartLink = buildSelectedProductUrl(m.product.add_to_cart_url || m.product.url, cardSelection)
                    const summaryCurrency = String(m.summary?.currency || breakdown.currency)
                    const summaryShipping = typeof m.summary?.shipping_fee === 'number' ? m.summary.shipping_fee : breakdown.shippingFee
                    const summaryCheckoutTotal = typeof m.summary?.total_cost === 'number' ? m.summary.total_cost : breakdown.checkoutTotal
                    const summaryBaseTotal = typeof m.summary?.unit_price === 'number' && typeof m.summary?.quantity === 'number'
                      ? m.summary.unit_price * m.summary.quantity
                      : breakdown.baseTotal
                    const stockLabel = formatAvailabilityLabel(m.product.availability)
                    const stockOut = isOutOfStockAvailability(stockLabel)
                    const stockCount = typeof m.product.stock_count === 'number' && m.product.stock_count >= 0 ? m.product.stock_count : null
                    const exactShippingKnown =
                      typeof m.summary?.shipping_fee === 'number' ||
                      typeof m.product.shipping_fee === 'number'
                    const shippingBubbleLabel = exactShippingKnown
                      ? summaryShipping === 0
                        ? 'Free Shipping'
                        : `Shipping: ${summaryCurrency} ${summaryShipping.toFixed(2)}`
                      : 'Shipping: Unknown'
                    return (
                  <div
                    style={{
                      marginTop: 10,
                      borderRadius: 8,
                      border: '1px solid rgba(148,163,184,0.3)',
                      background: 'rgba(15,23,42,0.5)',
                      padding: '8px 10px',
                      display: 'grid',
                      gap: 4,
                      fontSize: 12,
                    }}
                  >
                    <div style={{ color: '#93c5fd', fontWeight: 600 }}>Fetched product details:</div>
                    <div>
                      Product: <strong>{m.product.name || m.product.title || 'N/A'}</strong>
                    </div>
                    <div>
                      Shop: <strong>{m.product.shop || m.product.seller || 'N/A'}</strong>
                    </div>
                    <div>
                      Price: <strong>{String(m.product.currency || 'LKR').toUpperCase()} {Number(m.product.price || 0).toFixed(2)}</strong>
                    </div>
                    {!hasCardSelectionChanges && (
                      <div>
                        Stock:{' '}
                        <strong style={stockOut ? { color: '#ef4444' } : undefined}>
                          {stockCount !== null ? stockCount : stockLabel}
                        </strong>
                      </div>
                    )}
                    {!hasCardSelectionChanges && normalizeOptionValues(m.product.available_options || m.product.variants?.sizes).length > 0 && (
                      <div>
                        Available Sizes: <strong>{normalizeOptionValues(m.product.available_options || m.product.variants?.sizes).join(', ')}</strong>
                      </div>
                    )}
                    {!hasCardSelectionChanges && normalizeOptionValues(m.product.available_colors || m.product.variants?.colors).length > 0 && (
                      <div>
                        Available Colors: <strong>{normalizeOptionValues(m.product.available_colors || m.product.variants?.colors).join(', ')}</strong>
                      </div>
                    )}
                    {m.product.image && (
                      <div style={{ marginTop: 4 }}>
                        <img
                          src={m.product.image}
                          alt={m.product.name || 'Product image'}
                          style={{ width: 86, height: 86, objectFit: 'cover', borderRadius: 8, border: '1px solid rgba(148,163,184,0.3)' }}
                        />
                      </div>
                    )}
                    {!hasCardSelectionChanges && m.product.url && (
                      <div>
                        Product Link:{' '}
                        <a href={m.product.url} target="_blank" rel="noreferrer" style={{ color: '#93c5fd', textDecoration: 'underline' }}>
                          Open
                        </a>
                      </div>
                    )}
                    {hasCardSelectionChanges && (
                      <>
                        {cardSelection.size && (
                          <div>
                            Selected size: <strong>{cardSelection.size}</strong>
                          </div>
                        )}
                        {cardSelection.color && (
                          <div>
                            Selected color: <strong>{cardSelection.color}</strong>
                          </div>
                        )}
                        <div>
                          Selected quantity: <strong>{cardSelection.quantity}</strong>
                        </div>
                      </>
                    )}
                    {m.product.url && hasCardSelectionChanges && (
                      <div>
                        Updated Link:{' '}
                        <a
                          href={buildSelectedProductUrl(m.product.url, cardSelection)}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: '#93c5fd', textDecoration: 'underline' }}
                        >
                          Open
                        </a>
                      </div>
                    )}
                    {hasCardSelectionChanges && (
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
                        {checkoutLink && (
                          <button
                            type="button"
                            onClick={() => {
                              void handleActionBubbleClick('checkout', m.product as OrderAssistantProduct, cardSelection)
                            }}
                            style={{
                              borderRadius: 999,
                              border: '1px solid rgba(191,219,254,0.95)',
                              background: 'rgba(37,99,235,0.92)',
                              color: '#ffffff',
                              padding: '7px 12px',
                              fontSize: 12,
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            Checkout: {summaryCurrency} {summaryCheckoutTotal.toFixed(2)} ({shippingBubbleLabel})
                          </button>
                        )}
                        {addToCartLink && (
                          <button
                            type="button"
                            onClick={() => {
                              void handleActionBubbleClick('add-to-cart', m.product as OrderAssistantProduct, cardSelection)
                            }}
                            style={{
                              borderRadius: 999,
                              border: '1px solid rgba(187,247,208,0.95)',
                              background: 'rgba(5,150,105,0.92)',
                              color: '#ffffff',
                              padding: '7px 12px',
                              fontSize: 12,
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            Add to Cart: {summaryCurrency} {summaryBaseTotal.toFixed(2)}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                    )
                  })()
                )}
                {m.sender === 'assistant' && m.profile && (
                  <div
                    style={{
                      marginTop: 10,
                      borderRadius: 8,
                      border: '1px solid rgba(148,163,184,0.3)',
                      background: 'rgba(15,23,42,0.5)',
                      padding: '8px 10px',
                      display: 'grid',
                      gap: 4,
                      fontSize: 12,
                    }}
                  >
                    <div style={{ color: '#93c5fd', fontWeight: 600 }}>User Details</div>
                    {!effectiveAutomation.auto_fill_checkout && (
                      <div style={{ color: '#cbd5e1', fontSize: 11 }}>
                        Auto-fill checkout is OFF. Personal detail confirmation is skipped in checkout flow.
                      </div>
                    )}
                    {profileEditMode && editableProfile ? (
                      <>
                        <label>
                          Name:
                          <input
                            value={editableProfile.name || ''}
                            onChange={(e) => setEditableProfile((prev) => ({ ...(prev || {}), name: e.target.value }))}
                            style={{ width: '100%', marginTop: 4, marginBottom: 6 }}
                          />
                        </label>
                        <label>
                          Email:
                          <input
                            value={editableProfile.email || ''}
                            onChange={(e) => setEditableProfile((prev) => ({ ...(prev || {}), email: e.target.value }))}
                            style={{ width: '100%', marginTop: 4, marginBottom: 6 }}
                          />
                        </label>
                        <label>
                          Phone:
                          <input
                            value={editableProfile.phone || ''}
                            onChange={(e) => setEditableProfile((prev) => ({ ...(prev || {}), phone: e.target.value }))}
                            style={{ width: '100%', marginTop: 4, marginBottom: 6 }}
                          />
                        </label>
                        <label>
                          Shipping Address:
                          <input
                            value={editableProfile.shipping_address || ''}
                            onChange={(e) => setEditableProfile((prev) => ({ ...(prev || {}), shipping_address: e.target.value }))}
                            style={{ width: '100%', marginTop: 4, marginBottom: 6 }}
                          />
                        </label>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button
                            type="button"
                            onClick={handleSaveProfile}
                            disabled={loading}
                            style={{
                              borderRadius: 6,
                              border: '1px solid rgba(34,197,94,0.5)',
                              background: 'rgba(22,163,74,0.8)',
                              color: '#ffffff',
                              padding: '8px 14px',
                              fontSize: 13,
                              fontWeight: 600,
                              cursor: loading ? 'not-allowed' : 'pointer',
                              opacity: loading ? 0.6 : 1,
                            }}
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              addUserActionMessage('Cancel Profile Edit')
                              setProfileEditMode(false)
                            }}
                            disabled={loading}
                            style={{
                              borderRadius: 6,
                              border: '1px solid rgba(107,114,128,0.5)',
                              background: 'rgba(55,65,81,0.6)',
                              color: '#e2e8f0',
                              padding: '8px 14px',
                              fontSize: 13,
                              fontWeight: 600,
                              cursor: loading ? 'not-allowed' : 'pointer',
                              opacity: loading ? 0.6 : 1,
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div>Name: <strong>{(editableProfile?.name ?? m.profile.name) || 'N/A'}</strong></div>
                        <div>Email: <strong>{(editableProfile?.email ?? m.profile.email) || 'N/A'}</strong></div>
                        <div>Phone: <strong>{(editableProfile?.phone ?? m.profile.phone) || 'N/A'}</strong></div>
                        <div>Shipping Address: <strong>{(editableProfile?.shipping_address ?? m.profile.shipping_address) || 'N/A'}</strong></div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          {effectiveAutomation.auto_fill_checkout && (
                            <button
                              type="button"
                              onClick={() => {
                                addUserActionMessage('Edit Profile')
                                setEditableProfile({
                                  name: editableProfile?.name ?? m.profile?.name,
                                  email: editableProfile?.email ?? m.profile?.email,
                                  phone: editableProfile?.phone ?? m.profile?.phone,
                                  shipping_address: editableProfile?.shipping_address ?? m.profile?.shipping_address,
                                })
                                setProfileEditMode(true)
                              }}
                              disabled={loading}
                              style={{
                                borderRadius: 6,
                                border: '1px solid rgba(59,130,246,0.5)',
                                background: 'rgba(37,99,235,0.7)',
                                color: '#ffffff',
                                padding: '8px 14px',
                                fontSize: 13,
                                fontWeight: 600,
                                cursor: loading ? 'not-allowed' : 'pointer',
                                opacity: loading ? 0.6 : 1,
                              }}
                            >
                              Edit Profile
                            </button>
                          )}
                          {pendingState === 'await_profile_confirmation' && (
                            <button
                              type="button"
                              onClick={() => {
                                void handleConfirmProfileDetails()
                              }}
                              disabled={loading}
                              style={{
                                borderRadius: 6,
                                border: '1px solid rgba(34,197,94,0.5)',
                                background: 'rgba(22,163,74,0.8)',
                                color: '#ffffff',
                                padding: '8px 14px',
                                fontSize: 13,
                                fontWeight: 600,
                                cursor: loading ? 'not-allowed' : 'pointer',
                                opacity: loading ? 0.6 : 1,
                              }}
                            >
                              {profileCheckoutOnlyMode ? 'Checkout' : 'Confirm Details'}
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div
                style={{
                  justifySelf: 'start',
                  color: '#93c5fd',
                  fontSize: 12,
                  border: '1px dashed rgba(147,197,253,0.5)',
                  borderRadius: 8,
                  padding: '6px 10px',
                }}
              >
                {isScraping ? 'Scraping...' : 'Processing...'}
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 8, paddingTop: 12, borderTop: '1px solid rgba(148,163,184,0.2)' }}>
            {showCombinedSelector && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <label style={{ color: '#cbd5e1', fontSize: 12, minWidth: 96 }}>Quantity:</label>
                <button
                  type="button"
                  onClick={() => adjustQuantity(-1)}
                  disabled={loading || selectionDraft.quantity <= 1}
                  style={{
                    borderRadius: 8,
                    border: '1px solid rgba(148,163,184,0.3)',
                    background: 'rgba(2,6,23,0.45)',
                    color: '#e2e8f0',
                    padding: '8px 12px',
                    fontSize: 14,
                    cursor: loading ? 'not-allowed' : 'pointer',
                  }}
                >
                  -
                </button>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={selectionDraft.quantity}
                  onChange={(e) => {
                    const next = Number.parseInt(e.target.value, 10)
                    if (Number.isFinite(next)) {
                      setSelectionDraft((prev) => ({ ...prev, quantity: Math.max(1, Math.min(20, next)) }))
                    }
                  }}
                  disabled={loading}
                  style={{
                    width: 72,
                    textAlign: 'center',
                    borderRadius: 8,
                    border: '1px solid rgba(148,163,184,0.3)',
                    background: 'rgba(2,6,23,0.45)',
                    color: '#e2e8f0',
                    padding: '8px 10px',
                    fontSize: 13,
                  }}
                />
                <button
                  type="button"
                  onClick={() => adjustQuantity(1)}
                  disabled={loading || selectionDraft.quantity >= 20}
                  style={{
                    borderRadius: 8,
                    border: '1px solid rgba(148,163,184,0.3)',
                    background: 'rgba(2,6,23,0.45)',
                    color: '#e2e8f0',
                    padding: '8px 12px',
                    fontSize: 14,
                    cursor: loading ? 'not-allowed' : 'pointer',
                  }}
                >
                  +
                </button>
                {availableSizes.length > 0 && (
                  <>
                    <label style={{ color: '#cbd5e1', fontSize: 12 }}>Size:</label>
                    <select
                      value={selectionDraft.size || ''}
                      onChange={(e) => setSelectionDraft((prev) => ({ ...prev, size: e.target.value || undefined }))}
                      disabled={loading}
                      style={{
                        borderRadius: 8,
                        border: '1px solid rgba(148,163,184,0.3)',
                        background: 'rgba(2,6,23,0.45)',
                        color: '#e2e8f0',
                        padding: '8px 10px',
                        fontSize: 13,
                      }}
                    >
                      <option value="">Select</option>
                      {availableSizes.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  </>
                )}

                {availableColors.length > 0 && (
                  <>
                    <label style={{ color: '#cbd5e1', fontSize: 12 }}>Color:</label>
                    <select
                      value={selectionDraft.color || ''}
                      onChange={(e) => setSelectionDraft((prev) => ({ ...prev, color: e.target.value || undefined }))}
                      disabled={loading}
                      style={{
                        borderRadius: 8,
                        border: '1px solid rgba(148,163,184,0.3)',
                        background: 'rgba(2,6,23,0.45)',
                        color: '#e2e8f0',
                        padding: '8px 10px',
                        fontSize: 13,
                      }}
                    >
                      <option value="">Select</option>
                      {availableColors.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={disableTextInputForState ? 'Choose one available option above' : pendingInputType === 'select' ? 'Or type a custom value...' : 'Type your response...'}
                style={{
                  flex: 1,
                  borderRadius: 8,
                  border: '1px solid rgba(148,163,184,0.3)',
                  background: 'rgba(2,6,23,0.45)',
                  color: '#e2e8f0',
                  padding: '10px 12px',
                  fontSize: 13,
                }}
                disabled={loading || disableTextInputForState}
              />
              <button
                type="submit"
                disabled={loading || (isSelectionState(pendingState) ? false : !input.trim())}
                style={{
                  borderRadius: 8,
                  border: '1px solid rgba(96,165,250,0.55)',
                  background: 'rgba(37,99,235,0.5)',
                  color: '#eff6ff',
                  padding: '10px 14px',
                  fontSize: 13,
                  cursor: loading ? 'not-allowed' : 'pointer',
                }}
              >
                Send
              </button>
            </div>
          </form>
        </div>

      </div>

    </section>
  )
}
