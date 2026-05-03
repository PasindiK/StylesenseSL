"""LLM client wrapper (Groq) with a mock mode for local development.

This module keeps existing helper function names for compatibility,
but routes all LLM calls through Groq only.
"""
import os
import json
import typing
import logging
import time

from openai import OpenAI

logger = logging.getLogger(__name__)

# Rate limiting: track last request time
_last_request_time = 0
_min_request_interval = 5.0  # Minimum 5 seconds between requests to avoid 429 errors

_mock_flag = os.getenv("GEMINI_MOCK", os.getenv("LLM_MOCK", "0"))
LLM_MOCK = _mock_flag in ("1", "true", "True")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
STYLING_GROQ_API_KEY = os.getenv("STYLING_GROQ_API_KEY", "")
STYLING_GROQ_MODEL = os.getenv("STYLING_GROQ_MODEL", GROQ_MODEL)

def _get_groq_client(api_key: str | None = None) -> OpenAI:
    resolved_key = api_key or GROQ_API_KEY
    if not resolved_key:
        raise RuntimeError("GROQ_API_KEY is required for LLM calls")
    return OpenAI(api_key=resolved_key, base_url="https://api.groq.com/openai/v1")


def _call_groq(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    max_output_tokens: int = 512,
    temperature: float = 0.0,
    system_prompt: str = "You are a helpful fashion assistant.",
) -> dict:
    global _last_request_time

    resolved_key = api_key or GROQ_API_KEY
    resolved_model = model or GROQ_MODEL

    if resolved_key:
        elapsed = time.time() - _last_request_time
        if elapsed < _min_request_interval:
            time.sleep(_min_request_interval - elapsed)

    if not resolved_key:
        return {"predictions": [""]}

    try:
        client = _get_groq_client(resolved_key)
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        _last_request_time = time.time()
        text = (response.choices[0].message.content or "").strip()
        return {"predictions": [text]}
    except Exception as e:
        logger.warning(f"Groq API call failed: {e}")
        return {"predictions": [""]}


def _normalize_styling_advice(user_name: str, advice: str) -> str:
    cleaned = advice.strip().strip('"\'').replace("\r\n", "\n")
    intro_prefixes = (
        f"hey {user_name.lower()}",
        f"hi {user_name.lower()}",
        f"hello {user_name.lower()}",
        "here are",
        "here's",
    )

    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    while lines and any(lines[0].lower().startswith(prefix) for prefix in intro_prefixes):
        lines.pop(0)

    bullet_lines = []
    for line in lines:
        normalized = line.lstrip("-*•✓").strip()
        if normalized:
            bullet_lines.append(f"- {normalized.rstrip(' ,;')}")

    return "\n".join(bullet_lines[:5])


def predict(prompt: str, max_output_tokens: int = 512, temperature: float = 0.0) -> dict:
    """Return a dict with a `predictions` key containing the textual LLM response(s).

    In mock mode this returns a small canned plan derived heuristically from the prompt.
    In real mode this calls Groq chat completions and returns {'predictions': [text]}.
    """
    if LLM_MOCK:
        # very small heuristic: if prompt contains keywords produce a simple plan
        lp = prompt.lower()
        plan = []
        if "beach" in lp or "beach wear" in lp:
            plan.append({"action": "catalog_search", "params": {"tag": "beach wear", "max_price": 5000}})
        elif "shop" in lp and "foa" in lp:
            plan.append({"action": "catalog_search", "params": {"tag": "beach wear", "max_price": 5000, "shop": "FOA"}})
        else:
            # fallback: simple search by text
            plan.append({"action": "catalog_search", "params": {"tag": None, "max_price": None, "category": None, "q": prompt}})
        text = json.dumps(plan)
        return {"predictions": [text]}
    
    return _call_groq(
        prompt,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )


def extract_text(response: typing.Any) -> str:
    """Extract a single response text from predict-like responses.
    
    Handles normalized predict-like response format.
    """
    if not response:
        return ""
    
    if isinstance(response, dict):
        # Try normalized format (predictions)
        preds = response.get("predictions")
        if isinstance(preds, list) and len(preds) > 0:
            first = preds[0]
            if isinstance(first, dict):
                return first.get("content") or first.get("text") or json.dumps(first)
            return str(first)
        
        # Fallback: look for content at top-level
        if "content" in response:
            return response.get("content")
    
    return str(response)


def parse_query_with_gemini(query: str) -> dict:
    """Use Gemini to parse ambiguous product queries.
    
    Note: On free tier with rate limits, returns None values.
    The system will fall back to fuzzy matching in catalog_agent.py
    
    Args:
        query: Raw user query string
    
    Returns:
        dict with extracted: category, color, size, budget, style_preferences
        (or all None if API is limited/unavailable)
    """
    # Free tier rate limiting makes this unreliable - disable for now
    # The catalog agent has good fuzzy matching as fallback
    return {"category": None, "color": None, "size": None, "budget": None, "style_preferences": None}


def generate_styling_advice_with_gemini(
    user_name: str,
    query: str,
    fashion_topic: str = None,
    personalization_context: dict | None = None,
) -> str:
    """Generate personalized styling advice using Gemini API.
    
    Args:
        user_name: User's name for personalization
        query: Original user query/topic
        fashion_topic: Extracted topic (e.g., 'joggers', 't-shirts')
    
    Returns:
        Friendly, personalized styling advice (text only, no JSON)
    """
    styling_key = STYLING_GROQ_API_KEY or GROQ_API_KEY
    if not styling_key:
        fallback_advice = """- Fit is everything, so choose pieces that sit cleanly on your shoulders and chest.
- Start with versatile neutrals, then add one standout layer or accessory.
- Keep the outfit balanced by matching the formality of your top, bottom, and shoes."""
        return f"Hey {user_name}! Here's my styling advice:\n\n{fallback_advice}\n\nWould you like me to suggest some specific items that match this style?"

    try:
        topic_context = fashion_topic if fashion_topic else query or "styling in general"
        context = personalization_context or {}
        ctx_lines = []
        if context.get("preferred_style"):
            ctx_lines.append(f"Preferred style: {context.get('preferred_style')}")
        if context.get("favorite_colors"):
            ctx_lines.append(f"Favorite colors: {context.get('favorite_colors')}")
        if context.get("size"):
            ctx_lines.append(f"Usual size: {context.get('size')}")
        if context.get("budget"):
            ctx_lines.append(f"Budget preference: {context.get('budget')}")
        if context.get("recent_recommended_items"):
            recent = context.get("recent_recommended_items")
            if isinstance(recent, list) and recent:
                ctx_lines.append(f"Recent recommended items: {', '.join([str(x) for x in recent[:3]])}")
        personalization_block = "\n".join(ctx_lines) if ctx_lines else "No known user preferences."

        prompt = f"""You are a friendly fashion stylist named StylesenseSL.

User Name: {user_name}
Topic: How to style {topic_context}
User context:\n{personalization_block}

IMPORTANT: Return ONLY human-readable text. NO JSON, NO CODE, NO ACTIONS.
Do not greet the user. Do not repeat their name. Do not add an introduction or conclusion.
Give exactly 3 concise styling tips.
Start each tip with a hyphen (-).
Keep each tip to 1-2 short sentences.

Tone: Warm, casual, encouraging, conversational.
Include actionable, specific advice that the user can apply immediately.
When user context is available, adapt the advice to it naturally.
"""

        response = _call_groq(
            prompt,
            api_key=styling_key,
            model=STYLING_GROQ_MODEL,
            max_output_tokens=180,
            temperature=0.5,
            system_prompt="You are a precise fashion stylist who returns clean bullet-point advice.",
        )
        advice = _normalize_styling_advice(user_name, extract_text(response))
        advice_lower = advice.lower()
        has_json = advice.startswith("[") or advice.startswith("{") or '"action"' in advice or "'action'" in advice or "catalog_search" in advice_lower
        has_prompt = "you are a friendly fashion stylist" in advice_lower or "important:" in advice_lower or "user name:" in advice_lower
        if advice and len(advice) > 20 and not has_json and not has_prompt:
            return f"Hey {user_name}! Here's my styling advice:\n\n{advice}\n\nWould you like me to suggest some specific items that match this style?"
    except Exception as e:
        logger.warning(f"Styling advice generation failed: {e}")

    if not GROQ_API_KEY:
        return f"Hey {user_name}! Here are some universal fashion tips: Fit is key, start with basics, layer thoughtfully, and remember confidence is your best accessory!"
    
    try:
        topic_context = fashion_topic if fashion_topic else "styling in general"
        context = personalization_context or {}
        ctx_lines = []
        if context.get("preferred_style"):
            ctx_lines.append(f"Preferred style: {context.get('preferred_style')}")
        if context.get("favorite_colors"):
            ctx_lines.append(f"Favorite colors: {context.get('favorite_colors')}")
        if context.get("size"):
            ctx_lines.append(f"Usual size: {context.get('size')}")
        if context.get("budget"):
            ctx_lines.append(f"Budget preference: {context.get('budget')}")
        if context.get("recent_recommended_items"):
            recent = context.get("recent_recommended_items")
            if isinstance(recent, list) and recent:
                ctx_lines.append(f"Recent recommended items: {', '.join([str(x) for x in recent[:3]])}")
        personalization_block = "\n".join(ctx_lines) if ctx_lines else "No known user preferences."
        
        # Force text-only output with explicit instruction
        prompt = f"""You are a friendly fashion stylist named StylesenseSL.

User Name: {user_name}
Topic: How to style {topic_context}
User context:\n{personalization_block}

IMPORTANT: Return ONLY human-readable text. NO JSON, NO CODE, NO ACTIONS. Just plain text tips.

Give exactly 3-5 concise styling tips. Start each tip with a checkmark symbol (✓). Keep each tip 2-3 sentences maximum.

Tone: Warm, casual, encouraging, conversational.
Include actionable, specific advice that the user can apply immediately.
When user context is available, adapt the advice to it naturally.

Example format:
✓ Pair joggers with a fitted hoodie or jacket for a casual, balanced look.
✓ Choose clean sneakers to elevate the outfit.
✓ Experiment with layering and neutral colors for versatility.

Now write your response:"""
        
        print(f"[DEBUG] Generating styling advice for {user_name} about {topic_context}")
        response = predict(prompt, max_output_tokens=200, temperature=0.8)
        print(f"[DEBUG] Raw response type: {type(response)}, keys: {response.keys() if isinstance(response, dict) else 'N/A'}")
        if isinstance(response, dict) and "predictions" in response:
            print(f"[DEBUG] Response predictions: {response['predictions'][:100] if response['predictions'] else 'empty'}")
        advice = extract_text(response).strip()
        
        # Clean up any quotes if present
        advice = advice.strip('"\'')
        
        print(f"[DEBUG] Extracted advice (first 100 chars): {advice[:100]}")
        
        # CRITICAL: Validate response is NOT JSON/action objects
        # Check for JSON indicators: starts with [ or { or contains "action"
        advice_lower = advice.lower()
        has_json = advice.startswith("[") or advice.startswith("{") or '"action"' in advice or "'action'" in advice or "catalog_search" in advice_lower
        has_prompt = "you are a friendly fashion stylist" in advice_lower or "important:" in advice_lower or "now write your response" in advice_lower
        
        print(f"[DEBUG] Validation - has_json: {has_json}, has_prompt: {has_prompt}, len: {len(advice)}")
        
        if advice and len(advice) > 20 and not has_json and not has_prompt:
            print(f"[DEBUG] Styling advice PASSED validation: {len(advice)} chars")
            return f"Hey {user_name}! Here's my styling advice:\n\n{advice}\n\nWould you like me to suggest some specific items that match this style?"
    except Exception as e:
        logger.warning(f"Styling advice generation failed: {e}")
        print(f"[DEBUG] Styling advice error: {e}")
    
    # Fallback with checkmarks guaranteed (only used if API fails completely or returns invalid format)
    fallback_advice = f"""✓ Fit is everything - make sure clothes hug your body properly without being tight
✓ Start with basics in solid colors that are easy to mix and match
✓ Layer thoughtfully with jackets, hoodies, or cardigans to add depth
✓ Good shoes can make or break your outfit - invest in quality
✓ Confidence is your best accessory - wear what makes you feel amazing!"""
    
    return f"Hey {user_name}! Here's my styling advice:\n\n{fallback_advice}\n\nWould you like me to suggest some specific items?"


def generate_outfit_explanation_with_gemini(query: str, top_products: list, structured_query: dict = None) -> str:
    """Generate concise outfit explanation text for already-ranked top products."""
    if not top_products:
        return "I selected these items because they align with your fashion request and profile preferences."

    if not GROQ_API_KEY:
        names = [str(p.get("name") or p.get("product_name") or "item") for p in top_products[:3]]
        return (
            "These picks work well together for your request. "
            f"Top options like {', '.join(names)} balance style, color, and budget."
        )

    try:
        product_lines = []
        for p in top_products[:3]:
            name = str(p.get("name") or p.get("product_name") or "Item")
            category = str(p.get("category") or "")
            color = str(p.get("color") or "")
            price = p.get("price") or p.get("price_LKR")
            product_lines.append(f"- {name} | category={category} | color={color} | price={price}")

        sq = structured_query or {}
        prompt = (
            "You are a fashion assistant. Explain why these top products match the request. "
            "Return ONLY plain text, 2-3 short sentences, no JSON.\n"
            f"User query: {query}\n"
            f"Structured query: style={sq.get('style')}, event={sq.get('event')}, budget={sq.get('budget')}\n"
            "Top products:\n"
            + "\n".join(product_lines)
        )
        response = predict(prompt, max_output_tokens=120, temperature=0.4)
        text = extract_text(response).strip().strip('"\'')
        if text and len(text) > 20 and not text.startswith("{") and not text.startswith("["):
            return text
    except Exception as e:
        logger.warning(f"Outfit explanation generation failed: {e}")

    names = [str(p.get("name") or p.get("product_name") or "item") for p in top_products[:3]]
    return f"These picks were chosen to match your request, with strong fit on style and relevance. Top options include {', '.join(names)}."


def clarify_ambiguous_query(query: str, user_name: str = None) -> str:
    """Use Gemini to generate clarification request for ambiguous queries.
    
    Args:
        query: The ambiguous user query
        user_name: User's name for personalization
    
    Returns:
        Friendly clarification message (text only, no JSON)
    """
    if not GROQ_API_KEY:
        return f"I'd love to help! Could you tell me more? For example: color, category (t-shirts, joggers), size, or budget?"
    
    try:
        user_context = f" {user_name}," if user_name else ""
        
        # Force text-only output
        prompt = f"""You are a helpful fashion assistant.
User: {user_name or 'there'}
Query: "{query}"

IMPORTANT: Return ONLY a friendly 2-sentence clarification request. NO JSON, NO CODE, NO ACTIONS.

Ask them to provide: category (t-shirts, joggers, etc), color, size, or budget.
Tone: Warm, helpful, conversational.
Keep it short and specific.

Response:"""
        
        print(f"[DEBUG] Generating clarification for ambiguous query: '{query}'")
        response = predict(prompt, max_output_tokens=100, temperature=0.7)
        clarification = extract_text(response).strip()
        
        # Clean up quotes
        clarification = clarification.strip('"\'')
        
        if clarification and len(clarification) > 15:
            print(f"[DEBUG] Clarification generated: {len(clarification)} chars")
            return f"I'm not sure what you mean{user_context} {clarification}"
    except Exception as e:
        logger.warning(f"Clarification generation failed: {e}")
        print(f"[DEBUG] Clarification error: {e}")
    
    # Fallback
    return f"I'm not sure what you mean{user_context}. Could you tell me more? For example: color, category (t-shirts, joggers, shirts), size, or budget?"


def dynamic_small_talk(user_name: str = None, last_product: str = None, recent_interaction: str = None) -> str:
    """Generate dynamic small talk using Gemini API.
    
    Args:
        user_name: Name of the user
        last_product: Last product they viewed
        recent_interaction: Recent interaction type (e.g., 'styling advice', 'browsing')
    
    Returns:
        A friendly, dynamic small talk message
    """
    import datetime
    import random
    
    # Auto-detect time of day
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 18:
        time_of_day = "afternoon"
    else:
        time_of_day = "evening"
    
    # Fallback variations (use these if Gemini is slow or fails)
    fallback_messages = [
        f"Good {time_of_day}, {user_name}! 😊 How can I help you find amazing fashion?" if user_name else f"Good {time_of_day}! 😊 How can I help you with your style?",
        f"Hey {user_name}! I'm doing great, thanks for asking! What fashion adventure are we going on today?" if user_name else "Hey! I'm doing great! What can I help you find?",
        f"{user_name}, great to see you! Ready to find some awesome pieces?" if user_name else "Ready to find some awesome fashion pieces?",
        f"Good {time_of_day}, {user_name}! I'm here to help you style up. What are you looking for?" if user_name else f"Good {time_of_day}! I'm here to help. What are you looking for?",
    ]
    
    # Try Gemini API for dynamic, context-aware responses
    if GROQ_API_KEY:
        try:
            # Build context-rich prompt for better responses
            context_parts = [f"user_name={user_name or 'there'}", f"time={time_of_day}"]
            if last_product:
                context_parts.append(f"last_viewed={last_product}")
            if recent_interaction:
                context_parts.append(f"recent_activity={recent_interaction}")
            
            context_str = ", ".join(context_parts)
            
            prompt = f"""You are StylesenseSL, a friendly fashion assistant. Generate a warm, casual 1-2 sentence greeting.
Context: {context_str}

Guidelines:
- Be naturally conversational, not robotic
- Reference the time of day if appropriate
- If they viewed a product recently, you can casually mention it
- End with an open question about what they're looking for
- Use emojis sparingly (max 1)
- Don't be overly formal

Output ONLY the greeting message, no quotes or extra text."""
            
            print(f"[DEBUG] Generating dynamic small talk with Gemini for {user_name or 'anonymous'}")
            response = predict(prompt, max_output_tokens=60, temperature=0.9)
            message = extract_text(response).strip()
            
            # Clean up quotes if Gemini adds them
            message = message.strip('"\'')
            
            if message and len(message) > 10 and len(message) < 250:
                print(f"[DEBUG] Gemini small talk: '{message[:80]}...'")
                return message
        except Exception as e:
            logger.warning(f"Gemini API call failed (using fallback): {e}")
    
    # Use random fallback if Gemini unavailable or failed
    print(f"[DEBUG] Using fallback small talk for {user_name or 'anonymous'}")
    return random.choice(fallback_messages)
