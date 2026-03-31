"""
RAG Agent Node
Main AI agent with knowledge base RAG tool
"""
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from state import AgentState
from tools.knowledge_base import create_knowledge_base_tool
from database.conversation import get_conversation_history
from config import settings
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils.faq_cache import faq_cache
import asyncio

# Retry configuration for external API calls
RETRY_CONFIG = {
    "stop": stop_after_attempt(2),  # Reduced from 3
    "wait": wait_exponential(multiplier=0.5, min=1, max=4),  # Faster retries
    "retry": retry_if_exception_type((Exception,)),
    "reraise": True
}


async def build_system_prompt(state: AgentState, conversation_history: list) -> str:
    """
    Build concise system prompt focused on engaging, accurate responses
    
    Args:
        state: Current agent state
        conversation_history: List of previous messages
        
    Returns:
        System prompt string
    """
    # Check if social media channel
    channel = state.get("channel", "").lower()
    social_media_channels = ["instagram", "facebook", "whatsapp", "twitter", "linkedin", "tiktok"]
    is_social_media = any(social in channel for social in social_media_channels)
    
    # Build history section
    if conversation_history:
        history_text = "\n".join([
            f"User: {msg['user_message']}\nAssistant: {msg['assistant_response']}"
            for msg in conversation_history[-3:]  # Last 3 messages for context
        ])
        history_section = f"\n\n📜 Recent Conversation:\n{history_text}\n\n"
    else:
        history_section = "\n\n📜 New conversation.\n\n"
    
    # Add social media instruction if applicable
    social_media_instruction = ""
    if is_social_media:
        social_media_instruction = """

6. **For social media channels** (Instagram, Facebook, WhatsApp, etc.):
   - ALWAYS end your response with a website link
   - Translate naturally: "Visit our website for more information and to submit your application: https://swedenrelocators.se"
   - Format: Put it on a new line with 🌐 emoji
   - Example in French: "🌐 Visitez notre site web pour plus d'informations et soumettre votre demande: https://swedenrelocators.se"
"""
    
    prompt = f"""{history_section}You are an AI assistant for Sweden Relocators - helping people relocate to Sweden.

🎯 YOUR INSTRUCTIONS:

1. **ALWAYS respond in the user's language** - Match their language exactly (English, Swedish, Urdu, etc.)

2. **TOPIC POLICY:**
   - ✅ If the knowledge base returned results → **ALWAYS answer using those results**, even if the topic is not about Sweden. KB content is admin-approved — trust it completely.
   - ❌ Only redirect if there are NO KB results AND the question is completely unrelated to relocation (cooking, sports, entertainment, etc.)
   - If question is off-topic AND no KB results: "I specialize in helping with relocation to Sweden. How can I assist you with your move?"
   - **NEVER reject a question that the knowledge base has answered.**

3. **For greetings/casual messages** (hi, hello, thanks, bye, etc.):
   - Respond warmly and naturally in their language
   - Keep it brief (1-2 lines)
   - Ask how you can help with Sweden relocation
   - Example: "Hi! 👋 How can I help you with your move to Sweden today?"

4. **For relocation questions**:
   - Search knowledge base FIRST using the knowledge_base_search tool
   - Use KB results as a GUIDE - you can paraphrase and adapt the information
   - Answer SIMILAR questions using related KB information (be flexible!)
   - Keep responses SHORT but well-formatted
   - Always end with a relevant counter-question
   - **CRITICAL**: If KB has related info, USE IT to answer. Don't be overly strict about exact matches.

5. **For appointment/booking requests**:
   - You CANNOT book appointments or schedule meetings
   - NEVER say "I've booked" or "appointment confirmed"
   - Tell them: "I'll connect you with our team to schedule your appointment. They'll reach out shortly."

6. **If no KB results found**:
   - Don't make up information
   - Inform naturally that the team will assist
   - Example: "The expert team will reach out to assist you with this specific case shortly."
{social_media_instruction}
💬 RESPONSE FORMAT (IMPORTANT - use proper formatting!):

**[Topic Header]**

• **Point 1**: Brief explanation
• **Point 2**: Brief explanation  
• **Point 3**: Brief explanation

[Counter question to keep conversation going]

📝 FORMATTING RULES:
- Use **bold** for key terms and headers
- Use bullet points (• or -) on SEPARATE LINES for lists
- Add line breaks between sections for readability
- Keep each bullet point concise (1 line max)
- Maximum 4-5 bullet points per response

🚫 NEVER:
- Write long paragraphs (max 5-6 lines for questions!)
- Use training data - ONLY knowledge base results
- End without engaging the user
- Respond in wrong language
- Claim you can book appointments or confirm bookings (you cannot!)
- Reject or redirect a question that the KB has an answer for

✅ ALWAYS:
- Answer questions the KB has information about — KB content = admin-approved, always use it
- Match user's language exactly
- Search knowledge base for questions
- Be warm and helpful for greetings
- Keep responses concise
- Ask engaging counter questions about relocation
- Politely redirect off-topic questions **only when the KB has no relevant results**
"""
    
    return prompt


async def rag_agent_node(state: AgentState) -> AgentState:
    """
    RAG Agent Node
    
    Main AI agent with knowledge base tool for answering queries.
    Checks for admin takeover before processing.
    """
    logger.info(f"RAG agent processing for user {state['user_id']}")
    
    # Import supervision functions
    from database.supervision import (
        start_conversation, 
        update_conversation, 
        is_admin_takeover
    )
    
    # Register/update conversation for supervision
    await start_conversation(
        session_id=state["session_id"],
        user_id=state["user_id"],
        channel=state.get("channel", "webhook"),
        language=state.get("detected_language")
    )
    
    # Check if admin has taken over this conversation
    takeover, admin_id = await is_admin_takeover(state["session_id"])
    if takeover:
        logger.info(f"🛑 Admin {admin_id} has taken over - skipping AI response")
        # SILENT MODE: Empty response so frontend displays nothing
        state["ai_response"] = ""
        state["requires_human"] = True
        state["handoff_reason"] = f"Admin takeover by {admin_id}"
        state["knowledge_base_used"] = False
        state["cache_hit"] = False
        return state
    
    try:
        # Get conversation history from database
        history = await get_conversation_history(
            state["user_id"],
            limit=settings.MAX_CONVERSATION_HISTORY
        )
        # Store conversation history
        state["conversation_history"] = history
        state["history_count"] = len(history)
        
        # Build system prompt
        system_prompt = await build_system_prompt(state, history)
        state["system_prompt"] = system_prompt
        
        # Create LLM
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            temperature=settings.GROQ_TEMPERATURE,
            max_tokens=settings.GROQ_MAX_TOKENS,
            api_key=settings.GROQ_API_KEY
        )
        
        # ⚡ STEP 0: Detect greetings/salutations (skip KB for speed)
        kb_query = state["message"]
        query_lower = kb_query.lower().strip()
        
        # Quick language detection from script/characters
        def detect_language_simple(text: str) -> str:
            """Simple language detection based on character sets"""
            import re
            # Check for Arabic/Urdu script
            if re.search(r'[\u0600-\u06FF]', text):
                return "Urdu"
            # Check for Swedish characters
            elif re.search(r'[åäöÅÄÖ]', text):
                return "Swedish"
            # Default to English
            else:
                return "English"
        
        detected_lang = detect_language_simple(kb_query)
        state["detected_language"] = detected_lang
        logger.info(f"Detected language: {detected_lang}")
        
        # ⚡ FAST CONTEXT: Simple keyword extraction (no LLM call - saves 2-3 seconds!)
        def add_context_keywords(query: str, history: list) -> str:
            """Add context from last exchange without LLM call"""
            if not history or len(query) > 50:  # Skip if query is already detailed
                return query
            
            # Short queries like "yes", "ok", "tell me more" need context
            short_triggers = ['yes', 'ok', 'sure', 'please', 'more', 'how', 'what', 'why', 'when']
            if len(query.split()) <= 3 or query.lower().strip() in short_triggers:
                last = history[-1]
                # Extract key topic from last exchange
                last_msg = last.get('user_message', '')
                if last_msg:
                    return f"{query} (context: {last_msg[:100]})"
            return query
        
        # Add context without LLM call
        state["original_message"] = kb_query
        kb_query = add_context_keywords(kb_query, history)
        state["reformulated_query"] = kb_query if kb_query != state["original_message"] else None
        
        # ⚡ STEP 1: CHECK CACHE FIRST (Lightning fast!)
        search_query = kb_query  # This is already reformulated if needed
        cached_result = faq_cache.get(search_query, detected_lang)
        
        if cached_result:
            # Cache hit! Use cached answer directly
            kb_results = cached_result['result']
            state["knowledge_base_used"] = True
            state["cache_hit"] = True
            state["knowledge_base_results"] = [{"query": search_query, "result": kb_results, "from_cache": True}]
            
            # Restore requires_human flag from cache
            if cached_result.get('requires_human'):
                state["requires_human"] = True
                state["handoff_reason"] = "Cached query requires admin"
                logger.info(f"⚡ CACHE HIT! (requires admin): {search_query[:50]}...")
            else:
                logger.info(f"⚡ CACHE HIT! Instant response for: {search_query[:50]}...")
        else:
            # Cache miss - search knowledge base
            logger.info(f"Cache miss - searching knowledge base for: {search_query[:50]}...")
            
            # Create knowledge base tool
            kb_tool = await create_knowledge_base_tool()
            
            # Helper with retry for KB search
            @retry(**RETRY_CONFIG)
            async def search_kb_with_retry(query, lang):
                return await kb_tool.ainvoke({
                    "query": query,
                    "language": lang
                })

            # Search knowledge base with reformulated query
            kb_results = None
            try:
                # Call the tool - use the same detected_lang for cache consistency!
                kb_results = await search_kb_with_retry(search_query, detected_lang)
                
                state["knowledge_base_used"] = True
                state["cache_hit"] = False
                state["knowledge_base_results"] = [{"query": search_query, "result": kb_results, "from_cache": False}]
                logger.info(f"Knowledge base search completed: {len(kb_results) if kb_results else 0} chars")
            except Exception as kb_error:
                logger.error(f"Knowledge base search failed after retries: {str(kb_error)}", exc_info=True)
                state["knowledge_base_used"] = False
                state["cache_hit"] = False
                state["requires_human"] = True
                state["handoff_reason"] = "Knowledge base search error"
                kb_results = None
        
        # Build chat history
        chat_history = []
        for msg in history[-5:]:  # Last 5 messages
            chat_history.append(HumanMessage(content=msg["user_message"]))
            chat_history.append(AIMessage(content=msg["assistant_response"]))
        
        # Create prompt with KB context
        if kb_results and not any(err in kb_results for err in ["No relevant information", "could not extract content", "Error searching"]):
            kb_context = f"\n\n📚 KNOWLEDGE BASE RESULTS:\n{kb_results}\n\n"
        else:
            # No KB results - assign to admin automatically
            logger.info(f"No KB results found - skipping LLM generation and assigning to admin")
            state["requires_human"] = True
            state["handoff_reason"] = "No relevant information in knowledge base"
            state["ai_response"] = ""  # Let admin_handler set the response
            state["knowledge_base_used"] = False
            return state
        
        # Build final prompt
        messages = [
            ("system", system_prompt + kb_context),
        ]
        
        # Add chat history
        if chat_history:
            messages.append(MessagesPlaceholder(variable_name="chat_history"))
        
        messages.append(("human", "{input}"))
        
        prompt = ChatPromptTemplate.from_messages(messages)
        
        # Create chain
        chain = prompt | llm
        
        # Helper with retry for LLM generation
        @retry(**RETRY_CONFIG)
        async def generate_response_with_retry(inputs):
            return await chain.ainvoke(inputs)

        # Invoke LLM
        if chat_history:
            result = await generate_response_with_retry({
                "input": state["message"],
                "chat_history": chat_history
            })
        else:
            result = await generate_response_with_retry({
                "input": state["message"]
            })
        
        # Extract response
        ai_response = result.content if hasattr(result, 'content') else str(result)
        state["ai_response"] = ai_response
        
        # Update supervision system with conversation
        await update_conversation(
            session_id=state["session_id"],
            user_message=state["message"],
            ai_response=ai_response,
            language=state.get("detected_language"),
            ai_triggered_handoff=state.get("requires_human", False),
            handoff_reason=state.get("handoff_reason")
        )
        
        logger.info(
            f"RAG agent completed for user {state['user_id']}: "
            f"KB used: {state['knowledge_base_used']}"
        )
        
    except Exception as e:
        logger.error(f"Error in RAG agent: {str(e)}", exc_info=True)
        state["error"] = str(e)
        state["ai_response"] = (
            "I apologize, but I encountered an error. "
            "Let me connect you with our expert team."
        )
        state["requires_human"] = True
    
    return state
