"""
Direct test of OpenAI API key to verify if it's valid and working
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env
env_path = Path(".env")
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("OPENAI_API_KEY")

print("=" * 80)
print("🔍 OPENAI API KEY TEST")
print("=" * 80)

if not api_key:
    print("❌ ERROR: OPENAI_API_KEY not found in .env")
    exit(1)

print(f"✅ API Key found: {api_key[:20]}...{api_key[-10:]}")
print(f"   Length: {len(api_key)} characters")

# Try direct API call
print("\n" + "=" * 80)
print("📡 Testing direct API call...")
print("=" * 80)

try:
    from openai import OpenAI
    
    client = OpenAI(api_key=api_key)
    
    print("🔗 Sending test request to OpenAI...")
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": "You are a test assistant. Respond with 'API KEY WORKS!' in exactly 3 words."
            },
            {
                "role": "user",
                "content": "Test this API key"
            }
        ],
        temperature=0.1,
        max_tokens=50
    )
    
    print(f"\n✅ SUCCESS! API KEY IS VALID AND WORKING")
    print(f"   Response: {response.choices[0].message.content}")
    print(f"   Model: {response.model}")
    print(f"   Tokens used: {response.usage.total_tokens}")
    
except Exception as e:
    error_str = str(e)
    print(f"\n❌ API CALL FAILED")
    print(f"   Error Type: {type(e).__name__}")
    print(f"   Error Message: {error_str}")
    
    # Analyze error type
    if "insufficient_quota" in error_str or "429" in error_str:
        print(f"\n   🔴 DIAGNOSIS: Quota exceeded or no credits")
        print(f"      - Free tier expired")
        print(f"      - No payment method on file")
        print(f"      - Account billing issue")
    elif "invalid_api_key" in error_str or "401" in error_str:
        print(f"\n   🔴 DIAGNOSIS: API key is INVALID")
        print(f"      - Key is revoked or never existed")
        print(f"      - Key is from wrong account")
        print(f"      - Key format is incorrect")
    elif "connection" in error_str.lower():
        print(f"\n   🔴 DIAGNOSIS: Network/connection issue")
        print(f"      - Check internet connection")
        print(f"      - OpenAI API might be down")
    else:
        print(f"\n   🔴 DIAGNOSIS: Unknown error")

print("\n" + "=" * 80)
