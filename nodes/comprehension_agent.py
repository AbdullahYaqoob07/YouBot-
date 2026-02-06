"""
Comprehension Agent
Provides grammar/clarity suggestions and an optional corrected message using the configured LLM (Groq).
This is invoked only when an admin requests a preview before sending a message.
"""
import asyncio
from config import settings
from loguru import logger


async def _call_llm_sync(prompt: str) -> str:
    """Call the ChatGroq client in a threadpool (the client is blocking)."""
    try:
        from langchain_groq import ChatGroq
    except Exception as e:
        logger.error(f"Missing ChatGroq library: {e}")
        raise

    def _invoke():
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0.0
        )
        # invoke returns an object with .content in parts of this repo
        resp = llm.invoke(prompt)
        # Some clients return a simple string
        if hasattr(resp, 'content'):
            return resp.content
        return str(resp)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _invoke)
    return result


async def check_message(message: str, language: str = "English") -> dict:
    """Return a dict with `corrected` and `suggestions` keys.

    Uses the configured GROQ LLM. Raises an exception if LLM is not configured.
    """
    if not settings.GROQ_API_KEY or not settings.GROQ_MODEL:
        raise RuntimeError("LLM not configured (GROQ_API_KEY / GROQ_MODEL missing)")

    prompt = f"""
You are an expert customer-support editor. Improve the following admin message for grammar, clarity, tone (professional, concise), and politeness.

Return a JSON object with the following fields:
- corrected: the rewritten message (single string)
- suggestions: a short bullet list (newline separated) of what changed or why

Input message:
""" + message + f"""

Language: {language}

If no changes are needed, set `corrected` to the original message and `suggestions` to an empty string.
Do not include any extra explanation outside the JSON.
"""

    raw = await _call_llm_sync(prompt)

    # Try to extract JSON from response; fallback to simple parsing
    import json
    try:
        # Sometimes models return code fences or text - try to find first { ... }
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_text = raw[start:end+1]
            parsed = json.loads(json_text)
            corrected = parsed.get('corrected', '') or ''
            suggestions = parsed.get('suggestions', '') or ''

            # Basic cleanup: remove markdown artifacts for UI
            def _clean(t: str) -> str:
                import re
                if not t:
                    return t
                # remove code fences and backticks
                t = re.sub(r"```[\s\S]*?```", "", t)
                t = t.replace('`', '')
                # strip common markdown markers
                t = t.replace('**', '').replace('__', '')
                # convert simple list markers to bullets
                t = re.sub(r'^(\s*[-\*]+)\s*', '• ', t, flags=re.M)
                # collapse multiple blank lines
                t = re.sub(r"\n\s*\n+", "\n\n", t)
                return t.strip()

            return {
                "corrected": _clean(corrected),
                "suggestions": _clean(suggestions),
                "raw": raw
            }
    except Exception:
        logger.debug("Failed to parse JSON from LLM response for comprehension preview")

    # Fallback: return the full raw response as 'corrected' and empty suggestions
    # Fallback with minimal cleaning
    fallback = raw.strip()
    import re
    fallback = re.sub(r"```[\s\S]*?```", "", fallback)
    fallback = fallback.replace('`', '')
    return {"corrected": fallback, "suggestions": "", "raw": raw}
