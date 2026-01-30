"""
Test the LangGraph AI Agent System
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from graph import process_message
from config import settings
from loguru import logger

# Configure logger
logger.add(sys.stdout, level="INFO")


async def test_spam_detection():
    """Test spam detection"""
    print("\n" + "="*60)
    print("TEST 1: Spam Detection")
    print("="*60)
    
    spam_message = "Win $1000000! Click here now! Free money!"
    
    result = await process_message(
        message=spam_message,
        user_id="test_spam_001",
        session_id="test_spam_session_001",
        channel="webhook"
    )
    
    assert result["is_spam"], "Spam detection failed"
    print("✅ Spam detection working")
    print(f"   Spam score: {result['spam_score']}")
    print(f"   Reasons: {result['spam_reasons']}")


async def test_language_detection():
    """Test language detection"""
    print("\n" + "="*60)
    print("TEST 2: Language Detection")
    print("="*60)
    
    test_cases = [
        ("Jag vill flytta till Sverige", "Swedish"),
        ("I want to move to Sweden", "English"),
        ("Quiero mudarme a Suecia", "Spanish"),
    ]
    
    for message, expected_lang in test_cases:
        result = await process_message(
            message=message,
            user_id=f"test_lang_{expected_lang}",
            session_id=f"test_lang_session_{expected_lang}",
            channel="webhook"
        )
        
        detected = result.get("detected_language")
        print(f"✅ Message: '{message[:30]}...'")
        print(f"   Expected: {expected_lang}, Detected: {detected}")


async def test_conversation_flow():
    """Test full conversation flow"""
    print("\n" + "="*60)
    print("TEST 3: Full Conversation Flow")
    print("="*60)
    
    messages = [
        "I want to relocate to Sweden for work",
        "What documents do I need for a work visa?",
        "Can you help me with housing in Stockholm?",
    ]
    
    user_id = "test_user_flow"
    
    for i, message in enumerate(messages, 1):
        print(f"\n--- Message {i} ---")
        print(f"User: {message}")
        
        result = await process_message(
            message=message,
            user_id=user_id,
            session_id=f"test_session_{user_id}",
            channel="webhook",
            user_name="Test User"
        )
        
        print(f"AI: {result.get('ai_response', 'No response')[:200]}...")
        print(f"Language: {result.get('detected_language')}")
        print(f"KB Used: {result.get('knowledge_base_used')}")
        print(f"Human Required: {result.get('requires_human')}")


async def test_admin_handoff():
    """Test admin handoff logic"""
    print("\n" + "="*60)
    print("TEST 4: Admin Handoff")
    print("="*60)
    
    # User explicitly asks for human
    message = "I want to speak with a human agent"
    
    result = await process_message(
        message=message,
        user_id="test_handoff_001",
        session_id="test_handoff_session_001",
        channel="webhook"
    )
    
    print(f"Message: {message}")
    print(f"Requires Human: {result.get('requires_human')}")
    print(f"Handoff Reason: {result.get('handoff_reason')}")
    print(f"Assigned To: {result.get('assigned_admin_name', 'Pending')}")
    print(f"Queue Status: {result.get('queue_status', 'N/A')}")


async def test_multilanguage_response():
    """Test multi-language responses"""
    print("\n" + "="*60)
    print("TEST 5: Multi-Language Responses")
    print("="*60)
    
    test_cases = [
        ("Jag vill åka till Brasilien. Vad är proceduren?", "Swedish"),
        ("How do I apply for a Swedish visa?", "English"),
    ]
    
    for message, language in test_cases:
        print(f"\n--- {language} Test ---")
        print(f"Input: {message}")
        
        result = await process_message(
            message=message,
            user_id=f"test_multilang_{language}",
            session_id=f"test_multilang_session_{language}",
            channel="webhook"
        )
        
        response = result.get('ai_response', '')
        print(f"Response: {response[:200]}...")
        print(f"Detected Language: {result.get('detected_language')}")
        
        # Verify response is in same language
        if language == "Swedish":
            # Check for Swedish words in response
            swedish_words = ['vi', 'är', 'och', 'för', 'på']
            has_swedish = any(word in response.lower() for word in swedish_words)
            if has_swedish:
                print("✅ Response appears to be in Swedish")
            else:
                print("⚠️  Response may not be in Swedish")


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("🧪 LANGGRAPH AI AGENT TESTS")
    print("="*60)
    print(f"\nModel: {settings.GROQ_MODEL}")
    print(f"Database: {settings.DATABASE_URL[:50]}...")
    print(f"Vector Store: {settings.VECTOR_STORE_TYPE}")
    
    try:
        # Run tests
        await test_spam_detection()
        await test_language_detection()
        await test_conversation_flow()
        await test_admin_handoff()
        await test_multilanguage_response()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60)
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ TEST FAILED")
        print("="*60)
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
