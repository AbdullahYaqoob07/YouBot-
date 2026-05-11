"""Page-index retrieval helpers.

For `page_index` mode, the vector search returns chunk-level matches but the LLM
needs full-page context (legal documents, contracts, case files where
cross-paragraph context matters). This module joins the chunk hits back to the
`document_pages` table so the agent can feed the model whole pages rather than
isolated paragraphs.
"""

from __future__ import annotations

from typing import Optional, Sequence

from loguru import logger
from sqlalchemy import and_, or_, select

from database.models import DocumentPage, get_async_session


async def load_pages_for_match_refs(
    workspace_id: str,
    page_refs: Sequence[tuple[str, int]],
    tenant_id: Optional[str] = None,
    max_pages: int = 4,
    page_window: int = 0,
) -> list[dict]:
    """
    Fetch full page text for `(document_id, page_number)` refs.

    Args:
        workspace_id: Tenant workspace identifier (required for isolation).
        page_refs: Refs in relevance order (most relevant first). Duplicates and
            entries with empty doc_id / None page_number are skipped.
        tenant_id: Optional tenant filter for defence-in-depth.
        max_pages: Hard total cap on pages returned (primaries + neighbors).
            Bounds the LLM context payload size regardless of window.
        page_window: If > 0, also fetch neighboring pages (page ± 1, ± 2, …) for
            each primary ref. Useful when answers straddle page breaks. The top
            primary ref greedily fills its window first, so the most relevant
            chunk always has full surrounding context even if `max_pages` is
            tight.

    Returns:
        List of dicts with `document_id`, `page_number`, `page_text`,
        `section_headings`. Ordered: primary ref, then its ±1 neighbors, then
        its ±2, ..., before moving to the next primary.
    """
    if not page_refs:
        return []

    seen_primary: set[tuple[str, int]] = set()
    primary_refs: list[tuple[str, int]] = []
    for raw_doc_id, raw_page in page_refs:
        if not raw_doc_id or raw_page is None:
            continue
        try:
            key = (str(raw_doc_id), int(raw_page))
        except (TypeError, ValueError):
            continue
        if key in seen_primary:
            continue
        seen_primary.add(key)
        primary_refs.append(key)

    if not primary_refs:
        return []

    # Build expanded list with neighbors, capped at max_pages total.
    ordered_refs: list[tuple[str, int]] = []
    expanded_seen: set[tuple[str, int]] = set()
    for doc_id, page in primary_refs:
        if len(ordered_refs) >= max_pages:
            break
        # Order: primary, then ±1, ±2, ... so the closest neighbours are kept
        # if the cap clips this group.
        candidate_offsets = [0]
        for offset in range(1, page_window + 1):
            candidate_offsets.extend([-offset, offset])
        for delta in candidate_offsets:
            target_page = page + delta
            if target_page < 0:
                continue
            ref = (doc_id, target_page)
            if ref in expanded_seen:
                continue
            expanded_seen.add(ref)
            ordered_refs.append(ref)
            if len(ordered_refs) >= max_pages:
                break

    if not ordered_refs:
        return []

    predicates = [
        and_(
            DocumentPage.document_id == doc_id,
            DocumentPage.page_number == page_num,
        )
        for doc_id, page_num in ordered_refs
    ]
    where_clauses = [
        DocumentPage.workspace_id == str(workspace_id),
        or_(*predicates),
    ]
    if tenant_id:
        where_clauses.append(DocumentPage.tenant_id == str(tenant_id))

    try:
        async with get_async_session() as session:
            result = await session.execute(select(DocumentPage).where(*where_clauses))
            rows = result.scalars().all()
    except Exception as exc:
        logger.warning(
            "Page-index load failed for workspace {}: {}", workspace_id, exc
        )
        return []

    rows_by_key = {(str(r.document_id), int(r.page_number)): r for r in rows}

    pages: list[dict] = []
    for ref in ordered_refs:
        row = rows_by_key.get(ref)
        if row is None:
            continue
        text = (row.page_text or "").strip()
        if not text:
            continue
        pages.append(
            {
                "document_id": str(row.document_id),
                "page_number": int(row.page_number),
                "page_text": text,
                "section_headings": (
                    str(row.section_headings) if row.section_headings else None
                ),
            }
        )

    return pages
