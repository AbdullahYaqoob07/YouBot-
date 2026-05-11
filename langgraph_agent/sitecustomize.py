"""Interpreter startup customizations for local development.

This module is auto-imported by Python (via ``site``) when present on
``sys.path``. We use it to ensure Windows uses a selector event loop policy,
which is required by psycopg async connections.
"""

import asyncio
import sys


if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        # Keep startup resilient even if policy cannot be set in rare contexts.
        pass
