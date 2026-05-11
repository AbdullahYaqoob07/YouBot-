import asyncio
import httpx
import json
import time

URL = "http://127.0.0.1:8000/webhook/ai-agent"
HEADERS = {"Content-Type": "application/json"}

async def test_multilingual():
    print("Testing Multilingual Support & Caching...")
    
    # 1. Ask in English (Populate Cache)
    payload_en = {
        "message": "How do I apply for a work visa in Sweden?",
        "userId": "test_user_en",
        "channel": "test"
    }
    
    print("\n1. Sending English Query...")
    async with httpx.AsyncClient() as client:
        start = time.time()
        resp = await client.post(URL, json=payload_en, timeout=30.0)
        duration = time.time() - start
        print(f"Status: {resp.status_code}, Time: {duration:.2f}s")
        print(f"Response: {resp.json().get('message')[:100]}...")

    # 2. Ask in Urdu (Should hit cache + translate)
    payload_ur = {
        "message": "Mein Sweden ka work visa kaise apply karun?",
        "userId": "test_user_ur",
        "channel": "test"
    }
    
    print("\n2. Sending Urdu Query (Expect Cache Hit + Translation)...")
    async with httpx.AsyncClient() as client:
        start = time.time()
        resp = await client.post(URL, json=payload_ur, timeout=30.0)
        duration = time.time() - start
        
        data = resp.json()
        print(f"Status: {resp.status_code}, Time: {duration:.2f}s")
        print(f"Detected Language: {data.get('language')}")
        print(f"Response: {data.get('message')}")
        
    # 3. Test Explicit Translation Request
    payload_trans = {
        "message": "Translate that to Swedish",
        "userId": "test_user_trans",
        "sessionId": data.get("sessionId"), # Carry over session
        "channel": "test"
    }
    
    print("\n3. Testing Explicit Translation Request...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(URL, json=payload_trans, timeout=30.0)
        print(f"Response: {resp.json().get('message')}")

if __name__ == "__main__":
    asyncio.run(test_multilingual())
