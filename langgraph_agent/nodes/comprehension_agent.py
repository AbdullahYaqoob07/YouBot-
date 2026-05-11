"""
Comprehension Agent
Provides grammar/clarity suggestions and optional rewrites using the configured workspace LLM.
This is invoked only when an admin requests a preview before sending a message.
"""
from typing import Optional

from database.llm_provider_config_runtime import get_workspace_llm_runtime_config
from llm.factory import create_chat_model
from langchain_core.messages import HumanMessage
from config import settings
from loguru import logger


def _resolve_scope(
    tenant_id: Optional[str],
    workspace_id: Optional[str],
) -> tuple[str, str]:
    resolved_tenant = tenant_id or settings.DEFAULT_TENANT_ID
    resolved_workspace = workspace_id or settings.DEFAULT_WORKSPACE_ID
    return resolved_tenant, resolved_workspace


async def _call_llm(
    prompt: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 500,
) -> str:
    """Call the tenant/workspace configured chat model and return text content."""
    resolved_tenant, resolved_workspace = _resolve_scope(tenant_id, workspace_id)
    runtime_llm = await get_workspace_llm_runtime_config(resolved_tenant, resolved_workspace)
    llm = create_chat_model(
        runtime=runtime_llm,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=settings.GROQ_REQUEST_TIMEOUT,
    )

    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    if hasattr(resp, "content"):
        content = resp.content
        return content if isinstance(content, str) else str(content)
    return str(resp)


async def check_message(
    message: str,
    language: str = "English",
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    """Return a dict with `corrected` and `suggestions` keys.

    Uses the configured workspace LLM runtime.
    """
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

    raw = await _call_llm(
        prompt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        temperature=0.0,
        max_tokens=450,
    )

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


ACTION_PROMPTS = {
    "shorten": "Make the following message shorter and more concise while keeping the core meaning. Return only the shortened message.",
    "extend": "Expand the following message with more helpful detail and context. Return only the expanded message.",
    "summarize": "Write a brief, clear summary of the following message in 1-2 sentences. Return only the summary.",
    "rephrase": "Rephrase the following message to improve clarity and flow while keeping the same meaning. Return only the rephrased message.",
    "formal": "Rewrite the following message in a professional and formal tone suitable for customer support. Return only the rewritten message.",
    "friendly": "Rewrite the following message in a warm, friendly, and approachable tone while staying professional. Return only the rewritten message.",
    "bullets": "Convert the following message into a clear, easy-to-read bullet point list. Return only the bullet points.",
    "grammar": "Fix any grammar, spelling, and punctuation errors in the following message. Return only the corrected message.",
}

async def enhance_message(
    message: str,
    action: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    """Apply an AI enhancement action to a message.

    Supported actions: shorten, extend, summarize, rephrase, formal, friendly, bullets, grammar.
    Returns a dict with `enhanced` (the transformed text) key.
    """

    instruction = ACTION_PROMPTS.get(action)
    if not instruction:
        raise ValueError(f"Unknown enhance action: {action}")

    prompt = f"""{instruction}

Message:
{message}

Respond with only the transformed text, no extra explanation."""

    raw = await _call_llm(
        prompt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        temperature=0.0,
        max_tokens=400,
    )

    import re
    enhanced = raw.strip()
    enhanced = re.sub(r"```[\s\S]*?```", "", enhanced)
    enhanced = enhanced.replace('`', '').strip()

    return {"enhanced": enhanced, "action": action, "original": message}


async def translate_to_english(
    text: str,
    source_language: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> str:
    """Translate text from any language to English.

    Returns the original text unchanged if source is already English or text is empty.
    Supports "auto" for auto-detection.
    """
    if not text or not text.strip():
        return text
    if source_language.lower() in ("english", "en"):
        return text

    if source_language.lower() == "auto":
        prompt = f"""If the following text is NOT in English, translate it to English.
If it's already in English, return it unchanged.
Return ONLY the English text with no explanation.

Text:
{text}"""
    else:
        prompt = f"""Translate the following {source_language} text to English.
Return ONLY the translated text with no extra explanation or formatting.

Text:
{text}"""

    raw = await _call_llm(
        prompt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        temperature=0.0,
        max_tokens=450,
    )
    return raw.strip()


async def translate_from_english(
    text: str,
    target_language: str,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> str:
    """Translate English text to the target language.

    Returns the original text unchanged if target is English or text is empty.
    """
    if not text or not text.strip():
        return text
    if target_language.lower() in ("english", "en"):
        return text

    prompt = f"""Translate the following English text to {target_language}.
Return ONLY the translated text with no extra explanation or formatting.

Text:
{text}"""

    raw = await _call_llm(
        prompt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        temperature=0.0,
        max_tokens=450,
    )
    return raw.strip()
