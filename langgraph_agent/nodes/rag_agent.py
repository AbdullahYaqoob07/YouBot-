"""
RAG Agent Node
Main AI agent with knowledge base RAG tool
"""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from state import AgentState
from tools.knowledge_base import create_knowledge_base_tool, build_kb_namespace
from database.assistant_profile import get_assistant_profile
from database.conversation import get_conversation_history
from database.llm_provider_config_runtime import get_workspace_llm_runtime_config
from database.retrieval_modes import select_retrieval_mode
from llm.factory import create_chat_model
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


_TONE_DESCRIPTORS = {
    "warm": (
        "Warm, friendly, and empathetic. Use phrases like \"Great question!\", "
        "\"Happy to help!\", \"Absolutely!\". Sound human, not robotic."
    ),
    "professional": (
        "Polished and respectful. Direct and confident without slang. Avoid "
        "exclamation marks; prefer concise factual sentences."
    ),
    "casual": (
        "Conversational and approachable. Contractions OK. Light, helpful, "
        "but never sloppy or overly chatty."
    ),
    "formal": (
        "Formal and precise. Full sentences, no contractions, no slang. "
        "Treat the user with deference."
    ),
}

_DEFAULT_HANDOFF = (
    "Thanks for reaching out! I don't have specific details about that yet, "
    "but I'll connect you with the team so they can help directly."
)


async def build_system_prompt(state: AgentState, conversation_history: list) -> str:
    """
    Build a STRICT RAG-only system prompt parameterised by the workspace's
    assistant profile, so the same backend serves any company without code
    changes. The KB still grounds the facts; this prompt only controls the
    persona, scope, and tone.
    """
    channel = state.get("channel", "").lower()
    is_social_media = any(s in channel for s in ["instagram", "facebook", "whatsapp", "twitter", "linkedin"])
    user_language = state.get("detected_language") or "English"

    # Resolve workspace identity. Falls back to a sane generic persona if the
    # admin hasn't run setup yet, so a fresh workspace still works.
    profile = await get_assistant_profile(
        tenant_id=state.get("tenant_id") or "",
        workspace_id=state.get("workspace_id") or "",
    ) or {}

    business_name = (profile.get("business_name") or "our team").strip()
    business_description = (profile.get("business_description") or "").strip()
    service_topics: list[str] = list(profile.get("service_topics") or [])
    tone = (profile.get("tone") or "warm").strip().lower()
    website_url = (profile.get("website_url") or "").strip()
    contact_email = (profile.get("contact_email") or "").strip()
    custom_handoff = (profile.get("handoff_message") or "").strip()
    forbidden_topics: list[str] = list(profile.get("forbidden_topics") or [])

    tone_directive = _TONE_DESCRIPTORS.get(tone, _TONE_DESCRIPTORS["warm"])
    history_context = ""
    if conversation_history:
        last = conversation_history[-1]
        history_context = (
            f"Recent context: the user previously asked about "
            f"'{last['user_message'][:60]}...'\n\n"
        )

    business_blurb = business_description or f"questions about {business_name}'s services"

    if service_topics:
        topics_line = (
            "Topics you support: "
            + ", ".join(service_topics[:15])
            + "."
        )
    else:
        topics_line = (
            "Topics you support: anything covered in the knowledge base below. "
            "If a question is clearly outside that, hand it off."
        )

    forbidden_line = ""
    if forbidden_topics:
        forbidden_line = (
            "\nYou must NEVER engage with or claim to handle: "
            + ", ".join(forbidden_topics[:10])
            + ". Politely redirect those requests to the team."
        )

    if user_language.lower() != "english":
        language_instruction = (
            f"Respond in {user_language}. The user is writing in {user_language}, "
            f"so reply in {user_language}."
        )
    else:
        language_instruction = "Respond in the same language as the user's message."

    handoff_text = custom_handoff or _DEFAULT_HANDOFF

    contact_suffix_parts: list[str] = []
    if is_social_media and website_url:
        contact_suffix_parts.append(f"End the message with the link: {website_url}")
    if contact_email:
        contact_suffix_parts.append(
            f"If the user asks how to reach a human, you may share: {contact_email}"
        )
    contact_suffix = ("\n" + "\n".join(contact_suffix_parts)) if contact_suffix_parts else ""

    return f"""{history_context}You are a customer support assistant for {business_name}.
You help with: {business_blurb}.

LANGUAGE
{language_instruction}

TONE
{tone_directive}

SCOPE
{topics_line}{forbidden_line}

STRICT GROUNDING RULES
1. Only use information from the "KB:" section below. Never use your own training knowledge.
2. If the KB does not contain the answer, do NOT guess. Hand off to the team using the message under HANDOFF below.
3. If the question is clearly off-topic for {business_name}, hand off rather than answering.
4. Never invent prices, deadlines, names, processes, or guarantees.
5. Reply in the user's language ({user_language}).

ALLOWED
- Rephrase KB content naturally in the configured tone.
- End with one helpful follow-up question when appropriate.
- Keep formatting clean (no markdown headers, no emojis).

NOT ALLOWED
- Adding facts that are not in the KB.
- Switching language away from {user_language}.
- Promising outcomes the KB does not promise.

HANDOFF (use verbatim or translated when KB cannot answer)
"{handoff_text}"
{contact_suffix}"""


def trim_kb_results(kb_results: str, max_chars: int = 1200) -> str:
    """
    Trim KB results to reduce token usage while preserving structure.
    Keeps the most relevant content within token budget.
    
    Args:
        kb_results: Full KB search results
        max_chars: Maximum characters to keep (default ~300 tokens)
        
    Returns:
        Trimmed KB results string
    """
    if not kb_results or len(kb_results) <= max_chars:
        return kb_results
    
    # Try to preserve complete first result, trim rest
    parts = kb_results.split("---")
    
    if len(parts) > 1:
        # Keep first result fully if it fits
        first_result = parts[0]
        if len(first_result) <= max_chars * 0.7:
            remaining = max_chars - len(first_result) - 20
            trimmed_rest = "---".join(parts[1:])[:remaining]
            return first_result + "---" + trimmed_rest + "..."
    
    # Simple truncation with word boundary
    truncated = kb_results[:max_chars]
    # Find last space to avoid cutting words
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]
    
    return truncated + "..."


async def rag_agent_node(state: AgentState) -> AgentState:
    """
    RAG Agent Node
    
    Main AI agent with knowledge base tool for answering queries.
    Checks for admin takeover before processing.
    """
    logger.opt(exception=True).info("RAG agent processing for user {state['user_id']}")
    
    # Ensure critical keys exist to prevent LangGraph KeyErrors on all return paths
    if "error" not in state or state["error"] is None:
        state["error"] = ""
    if "ai_response" not in state or state["ai_response"] is None:
        state["ai_response"] = ""
    if "detected_language" not in state:
        state["detected_language"] = None
        
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
        language=state.get("detected_language"),
        tenant_id=state.get("tenant_id"),
        workspace_id=state.get("workspace_id"),
    )
    
    # Check if admin has taken over this conversation
    takeover, admin_id = await is_admin_takeover(
        state["session_id"],
        tenant_id=state.get("tenant_id"),
        workspace_id=state.get("workspace_id"),
    )
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
            limit=settings.MAX_CONVERSATION_HISTORY,
            tenant_id=state.get("tenant_id"),
            workspace_id=state.get("workspace_id"),
        )
        # Store conversation history
        state["conversation_history"] = history
        state["history_count"] = len(history)
        
        # Build system prompt
        system_prompt = await build_system_prompt(state, history)
        state["system_prompt"] = system_prompt
        
        # Resolve workspace LLM configuration and create provider-specific client
        runtime_llm = await get_workspace_llm_runtime_config(
            state.get("tenant_id"),
            state.get("workspace_id"),
        )
        llm = create_chat_model(
            runtime=runtime_llm,
            temperature=settings.GROQ_TEMPERATURE,
            max_tokens=settings.GROQ_MAX_TOKENS,
            timeout_seconds=settings.GROQ_REQUEST_TIMEOUT,
        )
        state["model_used"] = f"{runtime_llm.provider}:{runtime_llm.model}"
        
        # ⚡ STEP 0: Detect greetings/salutations (skip KB for speed)
        kb_query = state["message"]
        query_lower = kb_query.lower().strip()
        
        # Language detection based on character sets and common words
        def detect_language_simple(text: str) -> str:
            """Detect language based on character sets and common words"""
            import re
            text_lower = text.lower()
            
            # Check for Arabic/Urdu script (RTL languages)
            if re.search(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]', text):
                return "Urdu"
            
            # Check for Chinese characters
            if re.search(r'[\u4e00-\u9fff]', text):
                return "Chinese"
            
            # Check for Japanese (Hiragana/Katakana)
            if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):
                return "Japanese"
            
            # Check for Korean (Hangul)
            if re.search(r'[\uAC00-\uD7AF]', text):
                return "Korean"
            
            # Swedish (å/ä/ö OR distinctive common words). "jag" / "och" /
            # "är" / "för" almost never appear in English text, so they're
            # safe fallbacks for short sentences without diacritics.
            if re.search(r'[åäöÅÄÖ]', text) or re.search(
                r'\b(jag|och|att|är|för|inte|inom|kan|min|mitt|mina|hej|tack|vill|kommer|tid|boka|här|där|när|varför|hur|vad)\b',
                text_lower,
            ):
                return "Swedish"

            # Norwegian (Bokmål) — æ/ø + common words (jeg/ikke/og/på).
            if re.search(r'[æøÆØ]', text) or re.search(
                r'\b(jeg|ikke|takk|hvordan|hvorfor|kommer|været|være|fordi)\b',
                text_lower,
            ):
                return "Norwegian"

            # Danish — æ/ø + common words (jeg/ikke/også/hvad). Overlaps a lot
            # with Norwegian; we keep them separate so the LLM gets the right
            # name in its prompt.
            if re.search(
                r'\b(også|hvad|nogle|nogen|ikke|tak|hvordan|hvorfor)\b',
                text_lower,
            ):
                return "Danish"

            # Dutch — ij/aa/oo digraphs + distinctive words. Catches "Kan ik
            # mijn afspraak verzetten?" style queries even without ï/ë.
            if re.search(
                r'\b(ik|niet|een|het|maar|waarom|hoeveel|bedankt|alsjeblieft|graag|kunnen)\b',
                text_lower,
            ):
                return "Dutch"

            # German-specific: ß, ü, common words
            if 'ß' in text or re.search(
                r'\b(ich|und|ist|das|die|der|nicht|wie|kann|möchte|bitte|danke)\b',
                text_lower,
            ):
                return "German"

            # Spanish indicators: ¿, ¡, ñ, common words
            if re.search(r'[¿¡ñÑ]', text) or re.search(
                r'\b(qué|cómo|para|está|cuál|cuánto|puedo|hola|gracias|reservar|cita)\b',
                text_lower,
            ):
                return "Spanish"

            # French indicators: œ, ç (not at start), common words
            if 'œ' in text or re.search(
                r'\b(je|vous|est|les|des|pour|que|une|bonjour|merci|comment|rendez-vous)\b',
                text_lower,
            ):
                return "French"

            # Portuguese indicators
            if re.search(r'[ãõ]', text) or re.search(
                r'\b(você|como|para|está|não|obrigado|agendar|consulta)\b',
                text_lower,
            ):
                return "Portuguese"

            # Italian indicators
            if re.search(
                r'\b(come|sono|per|che|grazie|buongiorno|ciao|prenotare|appuntamento)\b',
                text_lower,
            ):
                return "Italian"

            # Default to English
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

        # Phase 3 retrieval mode routing (with recommendation event logging).
        retrieval_mode = "rag"
        recommendation_mode = "rag"
        page_window_limit = 4
        # Pages ± window are pulled around each primary hit so answers that
        # straddle page breaks are captured. Only consumed when retrieval_mode
        # ends up being "page_index". Override per-deploy via env if needed.
        try:
            page_neighbor_window = max(0, int(getattr(settings, "PAGE_INDEX_NEIGHBOR_WINDOW", 1)))
        except (TypeError, ValueError):
            page_neighbor_window = 1
        try:
            retrieval_selection = await select_retrieval_mode(
                tenant_id=state.get("tenant_id") or settings.DEFAULT_TENANT_ID,
                workspace_id=state.get("workspace_id") or settings.DEFAULT_WORKSPACE_ID,
                query_text=kb_query,
                selected_mode_override=state.get("retrieval_mode_override"),
            )
            retrieval_mode = retrieval_selection.get("selected_mode", "rag")
            recommendation_mode = retrieval_selection.get("recommended_mode", retrieval_mode)
            profile = retrieval_selection.get("profile") or {}
            try:
                page_window_limit = max(1, int(profile.get("page_window_limit") or 4))
            except (TypeError, ValueError):
                page_window_limit = 4
            state["retrieval_mode_selected"] = retrieval_mode
            state["retrieval_mode_recommended"] = recommendation_mode
            state["retrieval_mode_reason"] = retrieval_selection.get("reason_summary")
        except Exception as routing_error:
            logger.warning(f"Retrieval mode routing fallback to rag: {routing_error}")
            state["retrieval_mode_selected"] = "rag"
            state["retrieval_mode_recommended"] = "rag"
            state["retrieval_mode_reason"] = "Routing unavailable - defaulted to rag"
        
        # ⚡ STEP 1: CHECK CACHE FIRST (Lightning fast!)
        search_query = kb_query  # This is already reformulated if needed
        tenant_for_search = state.get("tenant_id") or settings.DEFAULT_TENANT_ID
        workspace_for_search = state.get("workspace_id") or settings.DEFAULT_WORKSPACE_ID
        search_namespace = build_kb_namespace(tenant_for_search, workspace_for_search)
        # Scope partitions the cache by (mode, namespace, version). Two different
        # questions in the same scope still need to match on actual question
        # semantics — we no longer embed the scope into the query string, which
        # used to inflate similarity for unrelated short queries and serve the
        # wrong cached answer.
        # v=5: scope-based partitioning + plain-query embeddings; previous v=4
        # entries used the embedded-scope format, so a bump invalidates them.
        cache_scope = f"mode={retrieval_mode}|ns={search_namespace}|v=5"
        cached_result = faq_cache.get(search_query, detected_lang, scope=cache_scope)

        # Resolve the cache hit (with translation if needed). If translation
        # fails we fall through to a fresh KB search so the user still gets
        # an answer in their language.
        cache_served = False
        if cached_result:
            cached_response = cached_result['result']

            hit_type = "EXACT"
            if cached_result.get('semantic_similarity'):
                hit_type = f"SEMANTIC ({cached_result['semantic_similarity']:.1%})"
            elif cached_result.get('needs_translation'):
                hit_type = "CROSS-LANGUAGE"

            if cached_result.get('requires_human'):
                state["knowledge_base_used"] = True
                state["cache_hit"] = True
                state["knowledge_base_results"] = [{"query": search_query, "from_cache": True}]
                state["requires_human"] = True
                state["handoff_reason"] = "Cached query requires admin"
                logger.info(f"⚡ CACHE HIT [{hit_type}] (requires admin): {search_query[:50]}...")
                return state

            # Translate cached response into the user's language if needed
            cached_lang = (cached_result.get('cached_language') or "English")
            different_lang = cached_lang.strip().lower() != (detected_lang or "English").strip().lower()
            needs_translation = bool(cached_result.get('needs_translation')) or different_lang
            translation_ok = True

            if needs_translation and detected_lang and detected_lang.strip().lower() not in ("english", "en"):
                try:
                    from nodes.comprehension_agent import translate_from_english
                    translated = await translate_from_english(
                        cached_response,
                        detected_lang,
                        tenant_id=state.get("tenant_id"),
                        workspace_id=state.get("workspace_id"),
                    )
                    if translated and translated.strip():
                        cached_response = translated
                        # Persist the translated answer under the user's
                        # language so subsequent same-language queries hit
                        # exact-match instead of re-running translation.
                        try:
                            faq_cache.set(
                                search_query,
                                cached_response,
                                detected_lang,
                                requires_human=False,
                                scope=cache_scope,
                            )
                        except Exception as set_err:
                            logger.warning(f"Failed to persist translated cache entry: {set_err}")
                        hit_type = f"{hit_type} → translated to {detected_lang}"
                    else:
                        translation_ok = False
                except Exception as tr_err:
                    logger.warning(
                        f"Cache hit translation to {detected_lang} failed; falling through to fresh "
                        f"generation: {tr_err}"
                    )
                    translation_ok = False

            if translation_ok:
                state["knowledge_base_used"] = True
                state["cache_hit"] = True
                state["knowledge_base_results"] = [{"query": search_query, "from_cache": True}]
                state["ai_response"] = cached_response
                logger.info(f"⚡ CACHE HIT [{hit_type}] Instant response for: {search_query[:50]}...")
                cache_served = True

        if cache_served:
            return state

        # Cache miss or unrecoverable cache hit (e.g. translation failed) —
        # run a fresh KB search so the user gets an answer in their language.
        logger.info(f"Cache miss - searching knowledge base for: {search_query[:50]}...")

        # Create knowledge base tool
        kb_tool = await create_knowledge_base_tool()

        # Helper with retry for KB search
        @retry(**RETRY_CONFIG)
        async def search_kb_with_retry(query, lang):
            return await kb_tool.ainvoke({
                "query": query,
                "language": lang,
                "retrieval_mode": retrieval_mode,
                "tenant_id": tenant_for_search,
                "workspace_id": workspace_for_search,
                "page_window_limit": page_window_limit,
                "page_neighbor_window": page_neighbor_window,
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
            logger.error("Knowledge base search failed after retries: {}", kb_error)
            state["knowledge_base_used"] = False
            state["cache_hit"] = False
            state["requires_human"] = True
            state["handoff_reason"] = "Knowledge base search error"
            kb_results = None
        
        # Build chat history (reduced for efficiency)
        chat_history = []
        for msg in history[-3:]:  # Last 3 messages (was 5)
            chat_history.append(HumanMessage(content=msg["user_message"]))
            chat_history.append(AIMessage(content=msg["assistant_response"]))
        
        # STRICT RAG: Only proceed if KB has relevant results above threshold
        no_result_indicators = [
            "No relevant information", 
            "could not extract content", 
            "Error searching",
            "Best match score:",  # Below threshold
            "may need re-indexing"
        ]
        
        has_relevant_kb = kb_results and not any(err in kb_results for err in no_result_indicators)
        
        if has_relevant_kb:
            # Mode-specific KB context budget. Page Index needs room for full
            # pages (legal/long-doc context), hybrid needs a bit more than rag.
            mode_char_budget = {"rag": 900, "hybrid": 1500, "page_index": 5000}
            max_chars = mode_char_budget.get(retrieval_mode, 900)
            trimmed_results = trim_kb_results(kb_results, max_chars=max_chars)
            kb_context = f"\n\n📚 KB (USE ONLY THIS INFORMATION):\n{trimmed_results}\n\n"
        else:
            # No relevant KB results - hand off to admin (NEVER use LLM knowledge)
            logger.info(f"No relevant KB results - handing off to admin (strict RAG policy)")
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
        
        # MCP Tool Integration Phase 4
        from tools.mcp_manager import mcp_pool
        mcp_tools = await mcp_pool.get_tools_for_tenant(
            tenant_id=state.get("tenant_id") or settings.DEFAULT_TENANT_ID,
            workspace_id=state.get("workspace_id") or settings.DEFAULT_WORKSPACE_ID
        )
        
        try:
            # Bind MCP tools to LLM if any exist
            if mcp_tools:
                llm = llm.bind_tools(mcp_tools)
                logger.info(f"Bound {len(mcp_tools)} MCP tools to agent execution.")

            # Create chain
            chain = prompt | llm
            
            # Helper with retry for LLM generation
            @retry(**RETRY_CONFIG)
            async def generate_response_with_retry(inputs):
                return await chain.ainvoke(inputs)

            # Prepare inputs
            chain_inputs = {"input": state["message"]}
            if chat_history:
                chain_inputs["chat_history"] = chat_history

            # Invoke LLM
            result = await generate_response_with_retry(chain_inputs)
            
            # --- ReAct Tool Execution Loop (Recursive) ---
            final_messages = await prompt.aformat_messages(**chain_inputs)
            iteration = 0
            
            while hasattr(result, "tool_calls") and result.tool_calls and iteration < 3:
                logger.info(f"LLM invoked {len(result.tool_calls)} external MCP tools (Iteration {iteration}). Processing...")
                
                final_messages.append(result) # The AIMessage containing `tool_calls`
                
                from langchain_core.messages import ToolMessage
                for tool_call in result.tool_calls:
                    target_tool = next((t for t in mcp_tools if t.name == tool_call["name"]), None)
                    if target_tool:
                        try:
                            # Invoke Custom Action Tool
                            tool_output = await target_tool.ainvoke(tool_call["args"])
                        except Exception as eval_err:
                            logger.opt(exception=True).error(f"Tool {tool_call['name']} failed")
                            tool_output = f"Error: {eval_err}"
                    else:
                        tool_output = f"Error: Tool {tool_call['name']} not found."
                        
                    final_messages.append(ToolMessage(content=str(tool_output), tool_call_id=tool_call["id"]))
                
                # Re-invoke LLM with the context payloads supplied by external MCPs
                @retry(**RETRY_CONFIG)
                async def generate_final_response():
                    return await llm.ainvoke(final_messages)
                
                result = await generate_final_response()
                iteration += 1

            # Extract response
            ai_response = result.content if hasattr(result, 'content') else str(result)
            state["ai_response"] = ai_response

            # Cache the synthesized customer-facing response (not the raw retrieval).
            # Only cache successful, non-handoff replies so we never serve a stale
            # "I'll connect you with the team" message in place of a real answer later.
            if ai_response and not state.get("requires_human"):
                try:
                    faq_cache.set(
                        search_query,
                        ai_response,
                        detected_lang,
                        requires_human=False,
                        scope=cache_scope,
                    )
                except Exception as cache_err:
                    logger.warning(f"Failed to cache synthesized response: {cache_err}")

        finally:
            # We no longer cleanup the pool here, as MCPClientPool is intended to cache
            # the persistent SSE connections across agent graph runs.
            pass
        
        # Update supervision system with conversation
        await update_conversation(
            session_id=state["session_id"],
            user_message=state["message"],
            ai_response=ai_response,
            language=state.get("detected_language"),
            ai_triggered_handoff=state.get("requires_human", False),
            handoff_reason=state.get("handoff_reason"),
            tenant_id=state.get("tenant_id"),
            workspace_id=state.get("workspace_id"),
        )
        
        logger.info(
            f"RAG agent completed for user {state['user_id']}: "
            f"KB used: {state['knowledge_base_used']}"
        )
        
    except Exception as e:
        # Use loguru positional args (not f-string) to avoid KeyError when exception
        # message contains dict-like curly braces e.g. from Groq API error responses.
        logger.opt(exception=True).error("Error in RAG agent: {}", str(e))
        state["error"] = str(e)[:500]  # Truncate to avoid storing huge error strings
        state["ai_response"] = (
            "I apologize, but I encountered an error. "
            "Let me connect you with our expert team."
        )
        state["requires_human"] = True
    
    # Ensure critical keys exist before LangGraph validation
    if "error" not in state or state["error"] is None:
        state["error"] = ""
    if "ai_response" not in state or state["ai_response"] is None:
        state["ai_response"] = ""
        
    return state
