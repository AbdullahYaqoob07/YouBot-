import requests

url = "http://localhost:8000/integrations/social/sc_gyyRAya-J41Tndk8SnqSazYMp1vRkXq7/messages"
payload = {
    "message": "Hello, I want to learn more about your services.",
    "userId": "test_user_123",
    "channel": "instagram",
    "userName": "Test User",
}

print(f"Sending POST to {url}")
print(f"Payload: {payload}")

try:
    response = requests.post(url, json=payload, timeout=30)
    print(f"\nStatus Code: {response.status_code}")
    
    try:
        data = response.json()
        print("\nResponse JSON:")
        import json
        print(json.dumps(data, indent=2))
    except ValueError:
        print("\nRaw Response Text:")
        print(response.text)
        
except Exception as e:
    print(f"Error: {e}")
