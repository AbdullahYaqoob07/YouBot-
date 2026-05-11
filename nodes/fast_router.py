"""
Fast Router Node - OPTIMIZED FOR SPEED
Early routing for simple queries to skip heavy RAG processing
"""
from functools import lru_cache
from state import AgentState
from loguru import logger

# Pre-defined responses for common patterns. Kept business-agnostic so the
# same templates work for any tenant; the bot's identity (name, scope) is
# applied later by the RAG agent's system prompt.
GREETING_RESPONSES = {
    "English": "Hello! How can I help you today?",
    "Swedish": "Hej! Hur kan jag hjälpa dig idag?",
    "Spanish": "¡Hola! ¿En qué puedo ayudarte hoy?",
    "German": "Hallo! Wie kann ich Ihnen heute helfen?",
    "French": "Bonjour! Comment puis-je vous aider aujourd'hui?",
    "Urdu": "السلام علیکم! میں آپ کی کیسے مدد کر سکتا ہوں؟",
    "Arabic": "مرحباً! كيف يمكنني مساعدتك اليوم؟",
}

FAREWELL_RESPONSES = {
    "English": "Thanks for reaching out! Have a great day.",
    "Swedish": "Tack för att du kontaktade oss! Ha en bra dag.",
    "Spanish": "¡Gracias por contactarnos! Que tengas un buen día.",
    "German": "Vielen Dank! Einen schönen Tag noch.",
    "French": "Merci de nous avoir contactés! Bonne journée.",
    "Urdu": "شکریہ! آپ کا دن اچھا ہو۔",
    "Arabic": "شكراً للتواصل معنا! نتمنى لك يوماً سعيداً.",
}

# Fast pattern matching (pre-compiled for speed)
GREETING_PATTERNS = {
    'hi', 'hello', 'hey', 'hej', 'hola', 'bonjour', 'hallo', 'good morning', 
    'good afternoon', 'good evening', 'greetings', 'howdy'
}

FAREWELL_PATTERNS = {
    'bye', 'goodbye', 'thank you', 'thanks', 'tack', 'gracias', 'merci', 
    'danke', 'ciao', 'see you', 'farewell', 'take care'
}

ADMIN_REQUEST_PATTERNS = {
    'speak to human', 'talk to person', 'human help', 'agent please',
    'need help', 'customer service', 'support team', 'tala med människa',
    'hablar con persona', 'parler avec humain', 'mit mensch sprechen'
}

@lru_cache(maxsize=500)
def check_simple_query(message_lower: str) -> tuple[bool, str, str | None]:
    """
    Check if message is a simple query that can skip RAG
    
    Args:
        message_lower: Lowercase message
        
    Returns:
        Tuple of (is_simple, query_type, response_template)
        query_type: 'greeting', 'farewell', 'admin_request', 'complex'
    """
    # Early return for long messages (likely complex)
    if len(message_lower) > 100:
        return False, 'complex', None
    
    # Check greetings
    if any(pattern in message_lower for pattern in GREETING_PATTERNS):
        return True, 'greeting', None
    
    # Check farewells
    if any(pattern in message_lower for pattern in FAREWELL_PATTERNS):
        return True, 'farewell', None
    
    # Check admin requests
    if any(pattern in message_lower for pattern in ADMIN_REQUEST_PATTERNS):
        return True, 'admin_request', None
    
    # Complex query - needs RAG
    return False, 'complex', None


async def fast_router_node(state: AgentState) -> AgentState:
    """
    Fast routing node - determines if query can skip RAG processing
    
    Sets state["fast_path"] = True for simple queries
    Sets state["query_type"] = 'greeting' | 'farewell' | 'admin_request' | 'complex'
    """
    message = state.get("message", "").strip()
    detected_language = state.get("detected_language", "English")
    
    if not message:
        state["fast_path"] = False
        state["query_type"] = "complex"
        return state
    
    # Check for simple query
    message_lower = message.lower()
    is_simple, query_type, _ = check_simple_query(message_lower)
    
    state["query_type"] = query_type
    state["fast_path"] = is_simple
    
    # Generate response for simple queries
    if is_simple:
        if query_type == 'greeting':
            state["ai_response"] = GREETING_RESPONSES.get(detected_language, GREETING_RESPONSES["English"])
            logger.info(f"Fast path: Greeting detected - skipping RAG")
            
        elif query_type == 'farewell':
            state["ai_response"] = FAREWELL_RESPONSES.get(detected_language, FAREWELL_RESPONSES["English"])
            logger.info(f"Fast path: Farewell detected - skipping RAG")
            
        elif query_type == 'admin_request':
            state["requires_human"] = True
            state["user_wants_human"] = True
            state["handoff_reason"] = "user_requested"
            logger.info(f"Fast path: Admin request detected - routing to admin")
    
    return state
