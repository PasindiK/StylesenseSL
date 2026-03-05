export type KGPreferenceType = 'category' | 'color' | 'style'

export type KGPreferenceSignal = {
  userId: string
  type: KGPreferenceType
  value: string
  weight?: number
}

export type KGFeedbackSignal = {
  userId: string
  productId: string
  feedback: 'like' | 'dislike'
}

export const COLD_START_QUESTIONS = [
  {
    id: 'q-style',
    label: 'Which style do you prefer most?',
    options: ['Casual', 'Formal', 'Streetwear', 'Minimalist'],
    mapsTo: 'style' as KGPreferenceType,
  },
  {
    id: 'q-color',
    label: 'Which color palette do you usually buy?',
    options: ['Black', 'Blue', 'Neutral', 'Bright'],
    mapsTo: 'color' as KGPreferenceType,
  },
  {
    id: 'q-category',
    label: 'What are you shopping for today?',
    options: ['T-SHIRTS', 'JOGGERS & PANTS', 'COATS', 'BEACH WEAR'],
    mapsTo: 'category' as KGPreferenceType,
  },
]

export function toPreferenceSignal(userId: string, type: KGPreferenceType, value: string, weight = 1): KGPreferenceSignal {
  return {
    userId,
    type,
    value,
    weight,
  }
}

export function toFeedbackSignal(userId: string, productId: string, liked: boolean): KGFeedbackSignal {
  return {
    userId,
    productId,
    feedback: liked ? 'like' : 'dislike',
  }
}
