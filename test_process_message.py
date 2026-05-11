import asyncio
from graph import process_message

async def test():
    try:
        res = await process_message(
            message="What are ATM withdrawal limits",
            user_id="test_user_123",
            session_id="test_sess_1",
            tenant_id="public",
            workspace_id="95c81811-ba6d-449d-9331-d0ece018fb8c"
        )
        print("RESULT:")
        print(res.get("ai_response"))
        print(res.get("error"))
    except Exception as e:
        print("EXCEPTION:", e)

if __name__ == "__main__":
    asyncio.run(test())
