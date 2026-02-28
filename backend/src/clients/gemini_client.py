"""Simple Gemini Pro client wrapper with a mock mode for local development.

Usage:
  - Set environment vars: `GEMINI_MOCK=1` to use mock mode (no cloud calls).
  - Set `GEMINI_API_KEY` for direct Gemini Pro API access (recommended)
  - For Vertex AI set:
      `GOOGLE_SERVICE_ACCOUNT_FILE` -> path to service account JSON
      `GEMINI_PROJECT`, `GEMINI_LOCATION`, `GEMINI_ENDPOINT_ID`

The client returns a dict resembling Vertex AI predict responses with a
`predictions` list where the first item is the response text (string).
"""
import os
import json
import typing
import logging
import time
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

# Rate limiting: track last request time
_last_request_time = 0
_min_request_interval = 5.0  # Minimum 5 seconds between requests to avoid 429 errors

# Disable mock mode by default since we have a real API key
GEMINI_MOCK = os.getenv("GEMINI_MOCK", "0") in ("1", "true", "True")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyA70RQJ4279U48aX8yWhM5X91pGCmIyGvk")

# Force disable mock if API key is present
if GEMINI_API_KEY and GEMINI_API_KEY != "AIzaSyA70RQJ4279U48aX8yWhM5X91pGCmIyGvk":
    GEMINI_MOCK = False

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
PROJECT = os.getenv("GEMINI_PROJECT")
LOCATION = os.getenv("GEMINI_LOCATION")
ENDPOINT_ID = os.getenv("GEMINI_ENDPOINT_ID")

def _make_endpoint_url():
    if not PROJECT or not LOCATION or not ENDPOINT_ID:
        return None
    return f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}/endpoints/{ENDPOINT_ID}:predict"


def _get_access_token() -> str:
    # lazy import to avoid hard dependency when using mock mode
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except Exception as e:
        raise RuntimeError("google-auth package required for real Gemini calls. Install google-auth") from e

    if not SERVICE_ACCOUNT_FILE:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE environment variable is required for real calls")

    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def predict(prompt: str, max_output_tokens: int = 512, temperature: float = 0.0) -> dict:
    """Return a dict with a `predictions` key containing the textual LLM response(s).

    In mock mode this returns a small canned plan derived heuristically from the prompt.
    With GEMINI_API_KEY, calls Google's Gemini Pro API directly.
    In real mode this calls the Vertex AI endpoint identified by env vars.
    """
    global _last_request_time
    
    # Rate limiting to avoid 429 errors
    if GEMINI_API_KEY:
        elapsed = time.time() - _last_request_time
        if elapsed < _min_request_interval:
            time.sleep(_min_request_interval - elapsed)
    
    if GEMINI_MOCK:
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
    
    # Try Gemini Pro API first (simpler, recommended)
    if GEMINI_API_KEY:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_output_tokens
                }
            }
            resp = requests.post(
                f"{url}?key={GEMINI_API_KEY}",
                headers=headers,
                json=payload,
                timeout=30
            )
            _last_request_time = time.time()  # Update last request time
            resp.raise_for_status()
            data = resp.json()
            # Extract text from Gemini response format
            if "candidates" in data and len(data["candidates"]) > 0:
                content = data["candidates"][0].get("content", {})
                parts = content.get("parts", [])
                if parts and "text" in parts[0]:
                    return {"predictions": [parts[0]["text"]]}
            return {"predictions": [json.dumps(data)]}
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}, falling back to empty response")
            # Return empty text that will trigger fallback in calling function
            return {"predictions": [""]}

    url = _make_endpoint_url()
    if not url:
        raise RuntimeError("GEMINI_PROJECT, GEMINI_LOCATION and GEMINI_ENDPOINT_ID must be set for real calls")

    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "instances": [{"content": prompt}],
        "parameters": {"temperature": temperature, "maxOutputTokens": max_output_tokens},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        # return raw text if JSON parsing fails
        return {"predictions": [resp.text]}


def extract_text(response: typing.Any) -> str:
    """Extract a single response text from predict-like responses.
    
    Handles both Vertex AI format (predictions) and Gemini API format (candidates).
    """
    if not response:
        return ""
    
    if isinstance(response, dict):
        # Try Gemini API format first (candidates)
        if "candidates" in response and isinstance(response["candidates"], list) and len(response["candidates"]) > 0:
            first_candidate = response["candidates"][0]
            if isinstance(first_candidate, dict) and "content" in first_candidate:
                content = first_candidate["content"]
                if isinstance(content, dict) and "parts" in content:
                    parts = content["parts"]
                    if isinstance(parts, list) and len(parts) > 0:
                        part = parts[0]
                        if isinstance(part, dict) and "text" in part:
                            return part["text"]
                if isinstance(content, dict) and "text" in content:
                    return content["text"]
        
        # Try Vertex AI format (predictions)
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


def generate_styling_advice_with_gemini(user_name: str, query: str, fashion_topic: str = None) -> str:
    """Generate personalized styling advice using Gemini API.
    
    Args:
        user_name: User's name for personalization
        query: Original user query/topic
        fashion_topic: Extracted topic (e.g., 'joggers', 't-shirts')
    
    Returns:
        Friendly, personalized styling advice (text only, no JSON)
    """
    if not GEMINI_API_KEY:
        return f"Hey {user_name}! Here are some universal fashion tips: Fit is key, start with basics, layer thoughtfully, and remember confidence is your best accessory!"
    
    try:
        topic_context = fashion_topic if fashion_topic else "styling in general"
        
        # Force text-only output with explicit instruction
        prompt = f"""You are a friendly fashion stylist named StylesenseSL.

User Name: {user_name}
Topic: How to style {topic_context}

IMPORTANT: Return ONLY human-readable text. NO JSON, NO CODE, NO ACTIONS. Just plain text tips.

Give exactly 3-5 concise styling tips. Start each tip with a checkmark symbol (✓). Keep each tip 2-3 sentences maximum.

Tone: Warm, casual, encouraging, conversational.
Include actionable, specific advice that the user can apply immediately.

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


def clarify_ambiguous_query(query: str, user_name: str = None) -> str:
    """Use Gemini to generate clarification request for ambiguous queries.
    
    Args:
        query: The ambiguous user query
        user_name: User's name for personalization
    
    Returns:
        Friendly clarification message (text only, no JSON)
    """
    if not GEMINI_API_KEY:
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
    if GEMINI_API_KEY:
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
