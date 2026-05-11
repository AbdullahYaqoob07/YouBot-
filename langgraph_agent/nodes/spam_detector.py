"""
Spam Detection Node
Comprehensive spam detection using multiple patterns
"""
import re
from typing import List
from state import AgentState
from loguru import logger


def detect_spam(message: str) -> tuple[bool, float, List[str]]:
    """
    Detect spam using comprehensive pattern matching
    
    Args:
        message: User message
        
    Returns:
        Tuple of (is_spam, spam_score, spam_reasons)
    """
    spam_reasons = []
    spam_score = 0.0
    
    # Comprehensive spam patterns
    spam_patterns = [
        # Pharmaceutical & Adult Content
        (r'\b(viagra|cialis|pharmacy|pills|drugs|casino|poker|xxx|adult|sex)\b', 1.0, "Pharmaceutical/Adult content"),
        
        # Money & Prize Scams
        (r'\b(win|winner|prize|lottery|jackpot)\b', 1.0, "Prize scam indicators"),
        (r'\b(cash|money|reward|earn)\b', 0.8, "Money/reward keywords"),
        (r'\$\d+[,.]?\d*', 0.7, "Dollar amounts"),
        (r'\b(\d+k|\d+K|million|billion)\s*(dollars|USD|EUR|GBP)\b', 1.0, "Large amounts"),
        
        # Urgency & Action Words
        (r'\b(click here|click now|tap here|tap now)\b', 1.2, "Click here spam"),
        (r'\b(buy now|order now|limited time|act now)\b', 0.9, "Urgency spam"),
        (r'\b(urgent|hurry|expire|expires|last chance)\b', 0.7, "Urgency keywords"),
        (r'\b(free money|easy money|make money|work from home|get rich)\b', 1.0, "Money making spam"),
        
        # Suspicious Links
        (r'http[s]?://(bit\.ly|tinyurl|goo\.gl|short\.link|t\.co)', 0.9, "Shortened links"),
        
        # All Caps (screaming)
        (r'\b[A-Z]{5,}\b', 0.5, "All caps words"),
        
        # Repetitive Characters
        (r'(.{2,})\1{4,}', 0.6, "Repetitive patterns"),
        
        # Crypto & Investment Scams
        (r'\b(bitcoin|crypto|investment|trading|forex|binary|profit|roi)\b', 0.8, "Investment spam"),
        
        # Gift Cards & Payment Methods
        (r'\b(gift card|paypal|venmo|cashapp|zelle|wire transfer)\b', 0.7, "Payment method spam"),
        
        # Common spam combinations
        (r'\b(click|tap)\s+(here|now|this|link)\b', 1.0, "Action + link spam"),
        (r'\b(win|won|winner)\s+(money|cash|prize|lottery)\b', 1.2, "Win money spam"),
    ]
    
    # Check each pattern
    for pattern, score, reason in spam_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            spam_score += score
            spam_reasons.append(reason)
    
    # Additional checks
    
    # Message length
    if len(message) > 500:
        spam_score += 0.5
        spam_reasons.append("Excessively long message")
    
    # Excessive exclamation marks
    exclamation_count = message.count('!')
    if exclamation_count > 5:
        spam_score += 0.5
        spam_reasons.append(f"Too many exclamation marks ({exclamation_count})")
    
    # Suspicious long words
    words = message.split()
    long_words = [w for w in words if len(w) > 20]
    if len(long_words) > 3:
        spam_score += 0.5
        spam_reasons.append("Suspiciously long words")
    
    # Excessive emojis
    emoji_pattern = r'[\U0001F300-\U0001F9FF]'
    emoji_count = len(re.findall(emoji_pattern, message))
    if emoji_count > 10:
        spam_score += 0.5
        spam_reasons.append(f"Excessive emojis ({emoji_count})")
    
    # Determine if spam (threshold: 1.0)
    is_spam = spam_score >= 1.0
    
    return is_spam, spam_score, spam_reasons


async def spam_detection_node(state: AgentState) -> AgentState:
    """
    Spam detection node
    
    Detects spam messages and marks them for blocking
    """
    message = state["message"]
    
    logger.info(f"Checking spam for user {state['user_id']}")
    
    # Detect spam
    is_spam, spam_score, spam_reasons = detect_spam(message)
    
    # Update state
    state["is_spam"] = is_spam
    state["spam_score"] = spam_score
    state["spam_reasons"] = spam_reasons
    
    if is_spam:
        logger.warning(
            f"Spam detected for user {state['user_id']}: "
            f"score={spam_score:.2f}, reasons={spam_reasons}"
        )
        state["ai_response"] = "This message was identified as spam and has been blocked."
        state["should_end"] = True
    else:
        logger.info(f"Message passed spam check for user {state['user_id']}")
    
    return state
