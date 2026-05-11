"""
Phase 3 ingestion sources and job pipeline operations.
CSV and web connectors (V1).
"""
from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy import delete, desc, select, update

from config import settings
from database.models import (
    DocumentPage,
    IngestionJob,
    KnowledgeSource,
    PageIndexEntry,
    get_async_session,
)
from database.workspace_provisioning import ensure_workspace_provisioned
from loguru import logger
from tools.knowledge_base import (
    build_kb_namespace,
    create_knowledge_base_tool,
    get_cached_embeddings,
    get_cached_vector_store,
)
from utils.mcp_transport import http_get


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _safe_rowcount(result: Any) -> int:
    rowcount = getattr(result, "rowcount", None)
    return int(rowcount or 0)


def _extract_html_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")
        return _clean_text(soup.get_text(" "))
    except Exception:
        # Fallback if bs4 is unavailable.
        return _clean_text(re.sub(r"<[^>]+>", " ", html))


def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def _adaptive_chunk_text(text: str, chunk_size_tokens: int = 500, overlap_tokens: int = 50) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        # Fallback to character chunking
        return _chunk_text(cleaned, chunk_size=chunk_size_tokens * 4, overlap=overlap_tokens * 4)
    
    tokens = encoding.encode(cleaned)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + chunk_size_tokens)
        chunk_tokens = tokens[start:end]
        chunks.append(encoding.decode(chunk_tokens))
        if end >= len(tokens):
            break
        start = max(0, end - overlap_tokens)
    return chunks


def _extract_pdf_pages(file_bytes: bytes) -> list[str]:
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(_clean_text(str(page.get_text())))
        doc.close()
        return pages
    except Exception as e:
        logger.opt(exception=True).error("PDF extraction failed: {}")
        return []


def _extract_docx(file_bytes: bytes) -> list[str]:
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = []
        for p in doc.paragraphs:
            text = _clean_text(p.text)
            if text:
                paragraphs.append(text)
        return ["\n".join(paragraphs)]
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return []

async def create_knowledge_source(
    tenant_id: str,
    workspace_id: str,
    source_name: str,
    source_type: str,
    source_uri: Optional[str] = None,
    source_config: Optional[dict[str, Any]] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    source_type_clean = (source_type or "").strip().lower()
    if source_type_clean not in {"csv", "web", "pdf", "docx"}:
        raise ValueError("source_type must be one of: csv, web, pdf, docx")

    now = datetime.utcnow()
    async with get_async_session() as session:
        await ensure_workspace_provisioned(session, tenant_id, workspace_id)
        source = KnowledgeSource(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            source_name=source_name.strip(),
            source_type=source_type_clean,
            source_uri=(source_uri or "").strip() or None,
            source_config=source_config or {},
            status="active",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)

    source_any = cast(Any, source)

    return {
        "id": source_any.id,
        "tenant_id": source_any.tenant_id,
        "workspace_id": source_any.workspace_id,
        "source_name": source_any.source_name,
        "source_type": source_any.source_type,
        "source_uri": source_any.source_uri,
        "status": source_any.status,
        "created_at": source_any.created_at.isoformat() if source_any.created_at is not None else None,
    }


async def list_knowledge_sources(tenant_id: str, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        result = await session.execute(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.workspace_id == workspace_id,
            )
            .order_by(desc(KnowledgeSource.created_at))
            .limit(limit)
        )
        rows = result.scalars().all()

    return [
        {
            "id": cast(Any, row).id,
            "source_name": cast(Any, row).source_name,
            "source_type": cast(Any, row).source_type,
            "source_uri": cast(Any, row).source_uri,
            "status": cast(Any, row).status,
            "last_sync_at": cast(Any, row).last_sync_at.isoformat() if cast(Any, row).last_sync_at is not None else None,
            "created_at": cast(Any, row).created_at.isoformat() if cast(Any, row).created_at is not None else None,
        }
        for row in rows
    ]


async def delete_knowledge_source(
    tenant_id: str,
    workspace_id: str,
    source_id: int,
) -> dict[str, Any]:
    namespace = build_kb_namespace(tenant_id, workspace_id)
    vector_cleanup_attempted = False
    vector_cleanup_succeeded = False

    vector_store = get_cached_vector_store()
    if vector_store is not None:
        vector_cleanup_attempted = True
        try:
            vector_store_any = cast(Any, vector_store)
            await asyncio.to_thread(
                vector_store_any.index.delete,
                filter={"source_id": {"$eq": str(source_id)}},
                namespace=namespace,
            )
            vector_cleanup_succeeded = True
        except Exception as exc:
            logger.warning(
                "Vector cleanup skipped for source {} in namespace {}: {}",
                source_id,
                namespace,
                exc,
            )

    now = datetime.utcnow()
    async with get_async_session() as session:
        source_result = await session.execute(
            select(KnowledgeSource).where(
                KnowledgeSource.id == source_id,
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.workspace_id == workspace_id,
            )
        )
        source = cast(Any, source_result.scalar_one_or_none())
        if not source:
            raise ValueError("Knowledge source not found for this tenant/workspace")

        page_delete = await session.execute(
            delete(DocumentPage).where(
                DocumentPage.source_id == source_id,
                DocumentPage.tenant_id == tenant_id,
                DocumentPage.workspace_id == workspace_id,
            )
        )
        index_delete = await session.execute(
            delete(PageIndexEntry).where(
                PageIndexEntry.source_id == source_id,
                PageIndexEntry.tenant_id == tenant_id,
                PageIndexEntry.workspace_id == workspace_id,
            )
        )
        jobs_update = await session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.source_id == source_id,
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.workspace_id == workspace_id,
            )
            .values(source_id=None, updated_at=now)
        )

        await session.delete(source)
        await session.commit()

    return {
        "deleted_source_id": source_id,
        "detached_jobs": _safe_rowcount(jobs_update),
        "removed_page_records": _safe_rowcount(page_delete),
        "removed_index_records": _safe_rowcount(index_delete),
        "vector_cleanup_attempted": vector_cleanup_attempted,
        "vector_cleanup_succeeded": vector_cleanup_succeeded,
    }


async def create_ingestion_job(
    tenant_id: str,
    workspace_id: str,
    source_id: int,
    created_by: Optional[str] = None,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    now = datetime.utcnow()

    async with get_async_session() as session:
        await ensure_workspace_provisioned(session, tenant_id, workspace_id)
        source_result = await session.execute(
            select(KnowledgeSource).where(
                KnowledgeSource.id == source_id,
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.workspace_id == workspace_id,
            )
        )
        source = cast(Any, source_result.scalar_one_or_none())
        if not source:
            raise ValueError("Knowledge source not found for this tenant/workspace")

        job = IngestionJob(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            source_id=source.id,
            source_type=source.source_type,
            trigger_type=trigger_type,
            status="queued",
            created_by=created_by,
            created_at=now,
            updated_at=now,
            details_json={"source_name": source.source_name, "source_uri": source.source_uri},
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

    job_any = cast(Any, job)

    return {
        "id": job_any.id,
        "source_id": job_any.source_id,
        "source_type": job_any.source_type,
        "status": job_any.status,
        "created_at": job_any.created_at.isoformat() if job_any.created_at is not None else None,
    }


async def list_ingestion_jobs(tenant_id: str, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        result = await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.workspace_id == workspace_id,
            )
            .order_by(desc(IngestionJob.created_at))
            .limit(limit)
        )
        rows = result.scalars().all()

    return [
        {
            "id": cast(Any, row).id,
            "source_id": cast(Any, row).source_id,
            "source_type": cast(Any, row).source_type,
            "status": cast(Any, row).status,
            "total_records": cast(Any, row).total_records,
            "processed_records": cast(Any, row).processed_records,
            "success_records": cast(Any, row).success_records,
            "failed_records": cast(Any, row).failed_records,
            "error_summary": cast(Any, row).error_summary,
            "started_at": cast(Any, row).started_at.isoformat() if cast(Any, row).started_at is not None else None,
            "finished_at": cast(Any, row).finished_at.isoformat() if cast(Any, row).finished_at is not None else None,
            "created_at": cast(Any, row).created_at.isoformat() if cast(Any, row).created_at is not None else None,
        }
        for row in rows
    ]


async def _load_source_records(source: Any) -> list[dict[str, Any]]:
    source_config = source.source_config or {}

    if source.source_type == "csv":
        content = source_config.get("csv_content")
        if not content:
            raise ValueError("CSV source is missing csv_content in source_config")

        reader = csv.DictReader(io.StringIO(content))
        rows: list[dict[str, Any]] = []
        for row in reader:
            question = _clean_text(str(row.get("question") or ""))
            answer = _clean_text(str(row.get("answer") or ""))
            text = _clean_text(str(row.get("text") or ""))
            category = _clean_text(str(row.get("category") or "general")) or "general"

            if question and answer:
                rows.append(
                    {
                        "text": f"Q: {question}\nA: {answer}",
                        "question": question,
                        "answer": answer,
                        "category": category,
                        "language": _clean_text(str(row.get("language") or "English")) or "English",
                    }
                )
            elif text:
                rows.append(
                    {
                        "text": text,
                        "category": category,
                        "language": _clean_text(str(row.get("language") or "English")) or "English",
                    }
                )
        return rows

    if source.source_type == "web":
        if not source.source_uri:
            raise ValueError("Web source is missing source_uri")

        response = await asyncio.to_thread(
            http_get,
            source.source_uri,
            timeout_seconds=20,
            allow_fallback=bool(settings.MCP_FAIL_OPEN and not settings.MCP_AGENT_STRICT_MODE),
            require_mcp=bool(settings.MCP_AGENT_STRICT_MODE),
        )
        if not response.ok:
            raise RuntimeError(
                f"Web source fetch failed with status {response.status_code} for {source.source_uri}"
            )
        body_text = _extract_html_text(response.text)
        chunks = _chunk_text(body_text, chunk_size=900, overlap=120)
        return [
            {
                "text": chunk,
                "category": "web",
                "language": "unknown",
                "source_uri": source.source_uri,
            }
            for chunk in chunks
        ]

    if source.source_type == "pdf":
        file_content_b64 = source_config.get("file_content")
        if not file_content_b64:
            raise ValueError("PDF source is missing file_content in source_config")
        import base64
        file_bytes = base64.b64decode(file_content_b64)
        pages = await asyncio.to_thread(_extract_pdf_pages, file_bytes)
        
        records = []
        for idx, page_text in enumerate(pages):
            chunks = _adaptive_chunk_text(page_text, chunk_size_tokens=500, overlap_tokens=50)
            for chunk in chunks:
                records.append({
                    "text": chunk,
                    "full_page_text": page_text,
                    "category": source_config.get("category", "document"),
                    "language": source_config.get("language", "unknown"),
                    "page_number": idx + 1,
                })
        return records

    if source.source_type == "docx":
        file_content_b64 = source_config.get("file_content")
        if not file_content_b64:
            raise ValueError("DOCX source is missing file_content in source_config")
        import base64
        file_bytes = base64.b64decode(file_content_b64)
        text_blocks = await asyncio.to_thread(_extract_docx, file_bytes)
        
        records = []
        for text_block in text_blocks:
            chunks = _adaptive_chunk_text(text_block, chunk_size_tokens=500, overlap_tokens=50)
            for chunk in chunks:
                records.append({
                    "text": chunk,
                    "full_page_text": text_block,
                    "category": source_config.get("category", "document"),
                    "language": source_config.get("language", "unknown"),
                    "page_number": 1,
                })
        return records

    raise ValueError(f"Unsupported source type: {source.source_type}")


async def run_ingestion_job(job_id: int) -> dict[str, Any]:
    """Execute ingestion job now (used by background task)."""
    now = datetime.utcnow()

    async with get_async_session() as session:
        job_result = await session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = cast(Any, job_result.scalar_one_or_none())
        if not job:
            raise ValueError("Ingestion job not found")

        source_result = await session.execute(select(KnowledgeSource).where(KnowledgeSource.id == job.source_id))
        source = cast(Any, source_result.scalar_one_or_none())
        if not source:
            job.status = "failed"
            job.error_summary = "Knowledge source not found"
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            await session.commit()
            raise ValueError("Knowledge source not found")

        job.status = "running"
        job.started_at = now
        job.updated_at = now
        await session.commit()

    try:
        # Ensure embeddings/vector store are initialized.
        await create_knowledge_base_tool()
        embeddings = get_cached_embeddings()
        vector_store = get_cached_vector_store()
        if embeddings is None or vector_store is None:
            raise RuntimeError("Embeddings or vector store not initialized")

        records = await _load_source_records(source)
        namespace = build_kb_namespace(source.tenant_id, source.workspace_id)
        vector_store_any = cast(Any, vector_store)

        success = 0
        failed = 0
        total = len(records)

        async def _persist_progress(processed_count: int, success_count: int, failed_count: int) -> None:
            try:
                async with get_async_session() as progress_session:
                    progress_result = await progress_session.execute(
                        select(IngestionJob).where(IngestionJob.id == job_id)
                    )
                    progress_job = cast(Any, progress_result.scalar_one_or_none())
                    if not progress_job:
                        return

                    progress_job.total_records = total
                    progress_job.processed_records = processed_count
                    progress_job.success_records = success_count
                    progress_job.failed_records = failed_count
                    progress_job.updated_at = datetime.utcnow()
                    await progress_session.commit()
            except Exception as progress_exc:
                logger.debug("Skipping ingestion progress update for job {}: {}", job_id, progress_exc)

        await _persist_progress(0, 0, 0)

        # Track page-level records for page index mode.
        page_rows: list[DocumentPage] = []
        page_index_rows: list[PageIndexEntry] = []
        created_pages = set()

        for idx, record in enumerate(records, start=1):
            record_text = record.get("text") or ""
            if not record_text:
                failed += 1
                processed_count = success + failed
                if processed_count % 3 == 0 or processed_count == total:
                    await _persist_progress(processed_count, success, failed)
                continue

            page_number = record.get("page_number", idx)
            vector_id = f"src_{source.id}_job_{job_id}_{idx}_{int(datetime.utcnow().timestamp())}"
            metadata = {
                "source": "ingestion_job",
                "source_id": str(source.id),
                "source_name": source.source_name,
                "source_type": source.source_type,
                "tenant_id": source.tenant_id,
                "workspace_id": source.workspace_id,
                "document_id": f"src-{source.id}",
                "page_number": page_number,
                "text": record_text,
                "category": record.get("category") or "general",
                "language": record.get("language") or "unknown",
            }
            if record.get("question"):
                metadata["question"] = record["question"]
            if record.get("answer"):
                metadata["answer"] = record["answer"]
            if record.get("source_uri"):
                metadata["source_uri"] = record["source_uri"]

            embedding = await asyncio.to_thread(embeddings.embed_query, record_text)
            await asyncio.to_thread(
                vector_store_any.index.upsert,
                vectors=[{"id": vector_id, "values": embedding, "metadata": metadata}],
                namespace=namespace,
            )

            if page_number not in created_pages:
                page_rows.append(
                    DocumentPage(
                        tenant_id=source.tenant_id,
                        workspace_id=source.workspace_id,
                        source_id=source.id,
                        document_id=f"src-{source.id}",
                        page_number=page_number,
                        page_text=record.get("full_page_text", record_text),
                        section_headings=None,
                        metadata_json={"category": metadata["category"], "source_type": source.source_type},
                        created_at=datetime.utcnow(),
                    )
                )
                created_pages.add(page_number)

            page_index_rows.append(
                PageIndexEntry(
                    tenant_id=source.tenant_id,
                    workspace_id=source.workspace_id,
                    source_id=source.id,
                    document_id=f"src-{source.id}",
                    page_number=page_number,
                    embedding_vector_ref=vector_id,
                    keyword_vector_ref=None,
                    created_at=datetime.utcnow(),
                )
            )
            success += 1
            processed_count = success + failed
            if processed_count % 3 == 0 or processed_count == total:
                await _persist_progress(processed_count, success, failed)

        async with get_async_session() as session:
            for row in page_rows:
                session.add(row)
            for row in page_index_rows:
                session.add(row)

            job_result = await session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
            job = cast(Any, job_result.scalar_one_or_none())
            source_result = await session.execute(select(KnowledgeSource).where(KnowledgeSource.id == source.id))
            latest_source = cast(Any, source_result.scalar_one_or_none())
            if not job or not latest_source:
                raise RuntimeError("Job/source disappeared while finalizing ingestion")

            job.total_records = total
            job.processed_records = success + failed
            job.success_records = success
            job.failed_records = failed
            job.status = "completed" if failed == 0 else "completed_with_errors"
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            job.details_json = {
                "namespace": namespace,
                "source_name": latest_source.source_name,
                "source_type": latest_source.source_type,
            }

            latest_source.last_sync_at = datetime.utcnow()
            latest_source.updated_at = datetime.utcnow()

            await session.commit()

        logger.info(
            f"Ingestion job {job_id} completed: {success}/{total} records ingested for "
            f"tenant={source.tenant_id}, workspace={source.workspace_id}"
        )
        return {
            "job_id": job_id,
            "status": "completed" if failed == 0 else "completed_with_errors",
            "total_records": total,
            "success_records": success,
            "failed_records": failed,
            "namespace": namespace,
        }

    except Exception as exc:
        logger.error(f"Ingestion job {job_id} failed: {exc}", e)
        async with get_async_session() as session:
            job_result = await session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
            job = cast(Any, job_result.scalar_one_or_none())
            if job:
                job.status = "failed"
                job.error_summary = str(exc)[:1000]
                job.finished_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()
                await session.commit()
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc),
        }
