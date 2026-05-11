"""
Intent Classification Node
Classifies user intent using LLM to determine if human handoff is needed
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from state import AgentState
from database.assistant_profile import get_assistant_profile
from database.llm_provider_config_runtime import get_workspace_llm_runtime_config
from llm.factory import create_chat_model
from config import settings
from loguru import logger


class IntentClassification(BaseModel):
    """Intent classification output schema"""
    user_wants_human: bool = Field(description="User explicitly wants to speak with a human")
    is_in_scope: bool = Field(description="Question is within the workspace's supported scope")
    ai_lacks_knowledge: bool = Field(description="AI did not give a real answer (deflected or said it can't help)")
    confidence: float = Field(description="Confidence score 0-1")
    reasoning: str = Field(description="Brief explanation of classification")


async def classify_intent(
    user_message: str,
    ai_response: str,
    knowledge_base_used: bool,
    tenant_id: str,
    workspace_id: str,
) -> IntentClassification:
    """
    Classify user intent using LLM
    
    Args:
        user_message: User's message
        ai_response: AI's response
        knowledge_base_used: Whether knowledge base was used
        
    Returns:
        IntentClassification object
    """
    runtime_llm = await get_workspace_llm_runtime_config(tenant_id, workspace_id)
    llm = create_chat_model(
        runtime=runtime_llm,
        temperature=0.1,
        max_tokens=400,
        timeout_seconds=settings.GROQ_REQUEST_TIMEOUT,
    )

    profile = await get_assistant_profile(tenant_id=tenant_id, workspace_id=workspace_id) or {}
    business_name = (profile.get("business_name") or "this business").strip()
    business_description = (profile.get("business_description") or "").strip()
    service_topics = list(profile.get("service_topics") or [])
    scope_line = (
        f"Supported topics: {', '.join(service_topics[:15])}."
        if service_topics
        else "Supported topics: anything the bot's knowledge base covers."
    )
    business_line = (
        f"Business: {business_name}"
        + (f" — {business_description}" if business_description else "")
        + "."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an intent classifier for a customer-support bot. Decide whether the
conversation needs to be handed off to a human admin.

WORKSPACE CONTEXT
{business_line}
{scope_line}

Respond ONLY with valid JSON matching this schema:
{{{{
  "user_wants_human": boolean,
  "is_in_scope": boolean,
  "ai_lacks_knowledge": boolean,
  "confidence": float (0-1),
  "reasoning": "brief explanation"
}}}}

CLASSIFICATION RULES

1. user_wants_human = true ONLY if the user explicitly asks for a human/agent/support/admin/representative
   in any language.

2. is_in_scope = true if the user's question relates to the supported topics above OR to anything a
   reasonable customer of this business would ask. It is FALSE only when the question is clearly
   unrelated to the business (e.g. asking a relocation bot to write code, or asking a SaaS support
   bot about cooking recipes).
   - Customer-support adjacencies (pricing, fees, appointments, billing, timelines, returns,
     contact info, account help, status checks) ARE in scope by default for any business.

3. ai_lacks_knowledge = true ONLY if the AI's response is a deflection or admission, e.g.:
   - "I don't have that information"
   - "I'll connect you with the team"
   - "That's outside what I can help with"
   - Apologetic with no concrete answer
   FALSE if the AI gave a direct factual answer (even short).

A handoff is needed when user_wants_human=true OR ai_lacks_knowledge=true.
is_in_scope is informational and should NOT by itself drive a handoff — the bot will hand off
when KB has nothing useful, regardless of scope label."""),
        ("human", """User Message: {user_message}

AI Response: {ai_response}

Knowledge Base Used: {knowledge_base_used}

Classify the intent:""")
    ]).partial(business_line=business_line, scope_line=scope_line)
    
    parser = JsonOutputParser(pydantic_object=IntentClassification)
    chain = prompt | llm | parser
    
    try:
        result = await chain.ainvoke({
            "user_message": user_message,
            "ai_response": ai_response,
            "knowledge_base_used": str(knowledge_base_used)
        })
        
        # Handle empty or incomplete response
        if not result or not isinstance(result, dict):
            logger.warning("Empty or invalid response from classifier, using defaults")
            return IntentClassification(
                user_wants_human=False,
                is_in_scope=True,
                ai_lacks_knowledge=True,
                confidence=0.5,
                reasoning="Empty classifier response - defaulting to human handoff"
            )

        # Backwards compatibility: older models may still emit the legacy field.
        if "is_genuine_relocation_question" in result and "is_in_scope" not in result:
            result["is_in_scope"] = result.pop("is_genuine_relocation_question")

        # Ensure all required fields have defaults
        result.setdefault("user_wants_human", False)
        result.setdefault("is_in_scope", True)
        result.setdefault("ai_lacks_knowledge", True)
        result.setdefault("confidence", 0.5)
        result.setdefault("reasoning", "Classification completed")

        return IntentClassification(**result)

    except Exception as e:
        logger.error(f"Intent classification error: {str(e)}")
        # Default to requiring human if classification fails
        return IntentClassification(
            user_wants_human=False,
            is_in_scope=True,
            ai_lacks_knowledge=True,
            confidence=0.5,
            reasoning="Classification error - defaulting to human handoff"
        )


async def intent_classification_node(state: AgentState) -> AgentState:
    """
    Intent Classification Node
    
    Classifies whether human handoff is needed
    """
    logger.info(f"Classifying intent for user {state['user_id']}")
    
    # Ensure critical keys exist to prevent LangGraph KeyErrors
    if "error" not in state or state["error"] is None:
        state["error"] = ""
    if "ai_response" not in state or state["ai_response"] is None:
        state["ai_response"] = ""
    if "detected_language" not in state:
        state["detected_language"] = None
        
    try:
        # FAST PATH -1: Cache hit without handoff - skip classification
        if state.get("cache_hit") and not state.get("requires_human"):
            logger.info(f"⚡ Cache hit - skipping classification")
            state["user_wants_human"] = False
            state["is_genuine_relocation_question"] = True
            state["ai_lacks_knowledge"] = False
            state["classification_confidence"] = 1.0
            return state
        
        # FAST PATH 0: Already marked for handoff by RAG agent (KB error or no results)
        if state.get("requires_human"):
            logger.info(f"⚡ Already marked for handoff: {state.get('handoff_reason', 'Unknown')}")
            return state
        
        # FAST PATH: Heuristic / Keyword Classification
        kw_requires_human = False
        kw_reason = None
        
        message_lower = state["message"].lower()
        
        # 1. User explicitly asking for human
        human_triggers = ["human", "agent", "support", "person", "representative", "admin", "talk to someone"]
        if any(trigger in message_lower for trigger in human_triggers):
            kw_requires_human = True
            kw_reason = "Keyword match: User requested human"
            
        # 2. Skip keyword matching for AI responses - let LLM classify (works for ALL languages)
        # The LLM intent classifier will analyze the AI response and detect lack of knowledge
        # in any language automatically
                
        # If fast path triggered, return valid dummy result
        if kw_requires_human:
            logger.info(f"⚡ Fast intent classification used: {kw_reason}")
            state["requires_human"] = True
            state["handoff_reason"] = kw_reason
            state["user_wants_human"] = True  # Simplified assumption
            state["is_genuine_relocation_question"] = True  # Legacy state key, kept for graph schema
            state["ai_lacks_knowledge"] = True
            state["classification_confidence"] = 1.0
            return state

        # SLOW PATH: Use LLM if not obvious
        # Classify intent
        classification = await classify_intent(
            user_message=state["message"],
            ai_response=state["ai_response"],
            knowledge_base_used=state.get("knowledge_base_used", False),
            tenant_id=state.get("tenant_id"),
            workspace_id=state.get("workspace_id"),
        )
        
        # Update state. The legacy `is_genuine_relocation_question` key is kept
        # in the graph state schema for now; we mirror `is_in_scope` into it so
        # downstream code (and old checkpoints) keep working.
        state["user_wants_human"] = classification.user_wants_human
        state["is_genuine_relocation_question"] = classification.is_in_scope
        state["ai_lacks_knowledge"] = classification.ai_lacks_knowledge
        state["classification_confidence"] = classification.confidence
        
        # Determine if human handoff is required
        requires_human = (
            classification.user_wants_human or
            classification.ai_lacks_knowledge
        )
        
        state["requires_human"] = requires_human
        
        # Set handoff reason
        if requires_human:
            if classification.user_wants_human:
                state["handoff_reason"] = "User requested human assistance"
            elif classification.ai_lacks_knowledge:
                state["handoff_reason"] = "AI lacks sufficient knowledge"
        
        logger.info(
            f"Intent classified for user {state['user_id']}: "
            f"requires_human={requires_human}, "
            f"confidence={classification.confidence:.2f}, "
            f"reason={classification.reasoning}"
        )
        
    except Exception as e:
        logger.error(f"Error in intent classification: {str(e)}")
        state["error"] = str(e)
        # Default to human handoff on error
        state["requires_human"] = True
        state["handoff_reason"] = "Classification error"
    
    return state
