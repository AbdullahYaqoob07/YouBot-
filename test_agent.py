"""Quick test script for the agent"""
import requests
import json

# Test the agent
url = "http://localhost:8000/webhook/ai-agent"
test_message = {
    "message": "Hello, I need help with visa requirements for Sweden",
    "userId": "test_user_999",
    "channel": "webhook"
}

print("Testing agent at:", url)
print("Sending message:", test_message["message"])
print("-" * 60)

try:
    response = requests.post(url, json=test_message, timeout=30)
    print(f"Status Code: {response.status_code}")
    print("\nResponse:")
    print(json.dumps(response.json(), indent=2))
except requests.exceptions.ConnectionError:
    print("❌ ERROR: Cannot connect to server on port 8000")
    print("Make sure the server is running with:")
    print("  python -m uvicorn app:app --reload --port 8000")
except Exception as e:
    print(f"❌ ERROR: {e}")
