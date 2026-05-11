"""
Supabase client helper.

Keeps key handling centralized and environment-driven.
"""
from functools import lru_cache
import importlib
from typing import Optional

from loguru import logger

from config import settings


@lru_cache(maxsize=1)
def _build_client(url: str, key: str):
    """Create and cache a Supabase client instance."""
    try:
        supabase_module = importlib.import_module("supabase")
        create_client = getattr(supabase_module, "create_client")
    except Exception as exc:
        raise RuntimeError(
            "Supabase package is not available. Install dependencies from requirements.txt"
        ) from exc

    return create_client(url, key)


def get_supabase_client():
    """
    Return backend Supabase client using service-role key.

    Returns:
        Supabase client instance.

    Raises:
        RuntimeError: if configuration is incomplete.
    """
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")

    key: Optional[str] = settings.SUPABASE_SERVICE_ROLE_KEY
    key_name = "SUPABASE_SERVICE_ROLE_KEY"

    if not key:
        raise RuntimeError(f"{key_name} is not configured")

    client = _build_client(settings.SUPABASE_URL, key)
    logger.debug("Supabase service-role client initialized")
    return client


def get_supabase_public_client():
    """
    Return Supabase client using anon key.

    Use this only for explicitly public-scope operations.
    """
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")

    key = settings.SUPABASE_ANON_KEY
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is not configured")

    client = _build_client(settings.SUPABASE_URL, key)
    logger.debug("Supabase anon client initialized")
    return client
