"""
Language Detection Node - LLM-POWERED AGENT
Uses Groq LLM to accurately detect any language including Urdu
"""
from functools import lru_cache
from state import AgentState
from langchain_groq import ChatGroq
from config import settings
from loguru import logger
from pydantic import SecretStr

# Non-Roman script languages for script type detection
NON_ROMAN_SCRIPTS = {
    'Arabic', 'Hindi', 'Chinese', 'Japanese', 'Korean', 'Russian',
    'Greek', 'Hebrew', 'Thai', 'Bengali', 'Tamil', 'Telugu', 'Marathi',
    'Gujarati', 'Kannada', 'Malayalam', 'Punjabi', 'Sinhala', 'Burmese',
    'Khmer', 'Lao', 'Georgian', 'Armenian', 'Amharic', 'Persian', 'Urdu',
    'Ukrainian', 'Bulgarian', 'Serbian', 'Macedonian', 'Belarusian',
    'Pashto', 'Sindhi', 'Kashmiri', 'Uyghur'
}

# Initialize Groq LLM for language detection
llm = ChatGroq(
    api_key=SecretStr(settings.GROQ_API_KEY),
    model=settings.GROQ_MODEL,
    temperature=0.0,
    max_tokens=30
)

# Enhanced Unicode-based fallback detection with Urdu support
def quick_script_detection(text: str) -> tuple[str, bool]:
    """Fast fallback detection using Unicode ranges with Urdu differentiation"""
    if not text:
        return "English", True
    
    sample = text[:100]  # Check more chars for accuracy
    
    # Count different script types
    arabic_chars = 0
    urdu_specific_chars = 0
    persian_chars = 0
    devanagari_chars = 0
    
    for char in sample:
        code = ord(char)
        
        # Urdu-specific characters (not in Arabic)
        if code in [0x0679, 0x067E, 0x0686, 0x0688, 0x0691, 0x0698, 0x06A9, 0x06AF, 0x06BA, 0x06BE, 0x06C1, 0x06C3, 0x06D2]:
            urdu_specific_chars += 1
        
        # General Arabic/Urdu/Persian script
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F or 0xFB50 <= code <= 0xFDFF or 0xFE70 <= code <= 0xFEFF:
            arabic_chars += 1
        
        # Persian-specific characters
        elif code in [0x067E, 0x0686, 0x0698, 0x06AF]:
            persian_chars += 1
        
        # Devanagari (Hindi)
        elif 0x0900 <= code <= 0x097F:
            devanagari_chars += 1
            
        # Chinese
        elif 0x4E00 <= code <= 0x9FFF:
            return "Chinese", False
        
        # Japanese
        elif 0x3040 <= code <= 0x30FF:
            return "Japanese", False
        
        # Korean
        elif 0xAC00 <= code <= 0xD7AF:
            return "Korean", False
        
        # Russian/Cyrillic
        elif 0x0400 <= code <= 0x04FF:
            return "Russian", False
        
        # Thai
        elif 0x0E00 <= code <= 0x0E7F:
            return "Thai", False
        
        # Hebrew
        elif 0x0590 <= code <= 0x05FF:
            return "Hebrew", False
        
        # Greek
        elif 0x0370 <= code <= 0x03FF:
            return "Greek", False
        
        # Bengali
        elif 0x0980 <= code <= 0x09FF:
            return "Bengali", False
        
        # Tamil
        elif 0x0B80 <= code <= 0x0BFF:
            return "Tamil", False
    
    # Determine if it's Urdu, Arabic, or Persian based on character frequency
    if arabic_chars > 0:
        if urdu_specific_chars > 0:
            return "Urdu", False
        elif persian_chars > urdu_specific_chars:
            return "Persian", False
        else:
            # Default to Urdu if we can't differentiate (common in Pakistan)
            return "Urdu", False
    
    if devanagari_chars > 0:
        return "Hindi", False
    
    return "English", True


async def detect_language_with_llm(message: str) -> tuple[str, bool]:
    """
    Use Groq LLM to detect language - NOW SECONDARY FALLBACK
    """
    # Early return for empty messages
    if not message or len(message.strip()) < 2:
        return "English", True
    
    try:
        # Use first 200 chars for better context
        sample = message[:200].strip()
        
        # Enhanced prompt
        prompt = f"""You are a language detection expert. Identify the EXACT language of this text.
IMPORTANT: 
- Distinguish between Urdu, Arabic, and Persian carefully
- Urdu uses Nastaliq script and has unique letters like ٹ، پ، ڈ، ڑ
- If you see Perso-Arabic script, check for Urdu-specific characters
Text: "{sample}"
Respond with ONLY ONE language name (e.g., Urdu, Arabic, Persian, English, Hindi, Chinese):"""
        
        # Call LLM ASYNC
        response = await llm.ainvoke(prompt)
        
        # Extract and validate response
        if not response or not response.content:
            logger.warning("LLM returned empty response")
            return quick_script_detection(message)
        
        detected_language = response.content.strip()
        
        # Clean up response
        for prefix in ["The language is", "Language:", "Answer:", "This is", "It is", "The text is in"]:
            if detected_language.lower().startswith(prefix.lower()):
                detected_language = detected_language[len(prefix):].strip()
        
        detected_language = detected_language.strip('.,!?:\"\'').split()[0] if detected_language.split() else ""
        
        if not detected_language:
            return quick_script_detection(message)
            
        detected_language = detected_language.capitalize()
        
        if not detected_language.replace('-', '').isalpha():
            return quick_script_detection(message)
            
        # Arabic vs Urdu check
        if detected_language == "Arabic":
            unicode_lang, _ = quick_script_detection(message)
            if unicode_lang == "Urdu":
                detected_language = "Urdu"
        
        is_roman_script = detected_language not in NON_ROMAN_SCRIPTS
        
        logger.info(f"✓ LLM detected: {detected_language} ({'Roman' if is_roman_script else 'Native'})")
        return detected_language, is_roman_script
        
    except Exception as e:
        logger.error(f"LLM language detection failed: {e}")
        return quick_script_detection(message)

async def language_detection_node(state: AgentState) -> AgentState:
    """
    Language detection node - OPTIMIZED
    
    Strategy:
    1. Try fast Unicode/Regex detection first (taking < 1ms)
    2. Only use LLM if confidence is low or text is very short/ambiguous
    3. Maintain high accuracy for Urdu/Hindi differentiation
    """
    message = state.get("message", "")
    
    if not message:
        state.update({"detected_language": "English", "is_roman_script": True})
        return state
        
    logger.info(f"🔍 Detecting language for: {message[:50]}...")
    
    # FAST PATH: Try Regex/Unicode first
    lang, is_roman = quick_script_detection(message)
    
    # Criteria to accept fast result without LLM:
    # 1. Not English (Unicode detection is usually reliable for non-Latin scripts like Arabic/Chinese)
    # 2. If English, text is long enough to be confident
    # 3. If Urdu/Hindi, we trust our specific char checks
    
    confident = False
    
    if lang in ["Urdu", "Arabic", "Persian", "Hindi", "Chinese", "Japanese", "Russian"]:
        confident = True
    elif lang == "English" and len(message) > 20:
        # If it looks like English and is reasonably long, it's likely English (or at least Roman script)
        confident = True
        
    if confident:
        logger.info(f"⚡ Fast detection used: {lang}")
        state.update({
             "detected_language": lang,
             "is_roman_script": is_roman,
             "language": lang
        })
        return state

    # SLOW PATH: Fallback to LLM for short/ambiguous text
    try:
        # We need to run sync LLM call in threadpool or make it async if client allows
        # For now, we'll keep it simple but log the perf hit
        logger.info("⚠️ Falling back to LLM for language detection")
        detected_language, is_roman_script = detect_language_with_llm(message)
        
        state.update({
             "detected_language": detected_language,
             "is_roman_script": is_roman_script,
             "language": detected_language
        })
    except Exception as e:
        logger.error(f"LLM fallback failed: {e}")
        state.update({
             "detected_language": lang,
             "is_roman_script": is_roman,
             "language": lang
        })
    
    return state