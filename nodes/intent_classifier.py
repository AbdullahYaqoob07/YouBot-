"""
Intent Classification Node
Classifies user intent using LLM to determine if human handoff is needed
"""
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from state import AgentState
from config import settings
from loguru import logger


class IntentClassification(BaseModel):
    """Intent classification output schema"""
    user_wants_human: bool = Field(description="User explicitly wants to speak with human")
    is_genuine_relocation_question: bool = Field(description="Question is about genuine relocation needs")
    ai_lacks_knowledge: bool = Field(description="AI doesn't have sufficient knowledge to answer")
    confidence: float = Field(description="Confidence score 0-1")
    reasoning: str = Field(description="Brief explanation of classification")


async def classify_intent(
    user_message: str,
    ai_response: str,
    knowledge_base_used: bool
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
    llm = ChatGroq(
        model="openai/gpt-oss-20b",  # Faster model for classification (8b vs 70b)
        temperature=0.1,
        max_tokens=400,  # Classification only needs short output
        api_key=settings.GROQ_API_KEY
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an intent classifier. Analyze the conversation and classify user intent.
        
Respond ONLY with valid JSON matching this schema:
{{
  "user_wants_human": boolean,
  "is_genuine_relocation_question": boolean,
  "ai_lacks_knowledge": boolean,
  "confidence": float (0-1),
  "reasoning": "brief explanation"
}}

Classification Rules:
1. user_wants_human = true if user explicitly requests human/admin/agent/support/representative

2. is_genuine_relocation_question = true if asking about visa, relocation, immigration, housing, jobs, Sweden
   - FALSE if question is completely off-topic (cooking, sports, entertainment, unrelated topics)

3. ai_lacks_knowledge = true if the AI response indicates ANY of these (in ANY language):
   - Says it doesn't have information
   - Says team/expert will help/reach out/assist
   - Admits the topic is outside its knowledge
   - Apologizes for not being able to help with the specific request
   - Suggests contacting someone else for help
   - The question is NOT about Sweden relocation (off-topic)
   - AI provided information unrelated to relocation services
   
   IMPORTANT: Set ai_lacks_knowledge=true if:
   - The AI's response sounds like it's deflecting or can't fully answer
   - The question is about cooking, food, sports, entertainment, or other non-relocation topics
   - The AI answered an off-topic question instead of redirecting to relocation

IMPORTANT: If ai_lacks_knowledge=true OR user_wants_human=true → this conversation needs human admin"""),
        ("human", """User Message: {user_message}

AI Response: {ai_response}

Knowledge Base Used: {knowledge_base_used}

Classify the intent:""")
    ])
    
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
                is_genuine_relocation_question=True,
                ai_lacks_knowledge=True,
                confidence=0.5,
                reasoning="Empty classifier response - defaulting to human handoff"
            )
        
        # Ensure all required fields have defaults
        result.setdefault("user_wants_human", False)
        result.setdefault("is_genuine_relocation_question", True)
        result.setdefault("ai_lacks_knowledge", True)
        result.setdefault("confidence", 0.5)
        result.setdefault("reasoning", "Classification completed")
        
        return IntentClassification(**result)
        
    except Exception as e:
        logger.error(f"Intent classification error: {str(e)}")
        # Default to requiring human if classification fails
        return IntentClassification(
            user_wants_human=False,
            is_genuine_relocation_question=True,
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
            state["user_wants_human"] = True # Simplified assumption
            state["is_genuine_relocation_question"] = True # Safe default
            state["ai_lacks_knowledge"] = True 
            state["classification_confidence"] = 1.0
            return state

        # SLOW PATH: Use LLM if not obvious
        # Classify intent
        classification = await classify_intent(
            user_message=state["message"],
            ai_response=state["ai_response"],
            knowledge_base_used=state.get("knowledge_base_used", False)
        )
        
        # Update state
        state["user_wants_human"] = classification.user_wants_human
        state["is_genuine_relocation_question"] = classification.is_genuine_relocation_question
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
