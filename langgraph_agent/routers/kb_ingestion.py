from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from typing import List, Optional
from loguru import logger
from datetime import datetime

from tenant_context import TenantContext, resolve_tenant_context, resolve_workspace_alias
from app import verify_admin_key

from database.models import get_async_session, IngestionJob, KnowledgeSource
from database.ingestion_jobs import (
    list_knowledge_sources,
    list_ingestion_jobs,
    create_knowledge_source,
    create_ingestion_job,
    run_ingestion_job,
    delete_knowledge_source,
)
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter(tags=["Knowledge sources & Ingestion"])

class IngestionJobCreateRequest(BaseModel):
    sourceId: int
    triggerType: str = "manual"
    createdBy: Optional[str] = None
    runNow: bool = True

@router.get("/admin/workspaces/{workspace_id}/knowledge-sources")
async def get_knowledge_sources(
    workspace_id: str,
    limit: int = 100,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """List knowledge sources for a workspace module."""
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    
    try:
        sources = await list_knowledge_sources(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            limit=limit
        )
        return {"sources": sources, "status": "success", "count": len(sources)}
    except Exception as e:
        logger.opt(exception=True).error("Error listing knowledge sources: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to list knowledge sources")


@router.delete("/admin/workspaces/{workspace_id}/knowledge-sources/{source_id}")
async def delete_knowledge_source_endpoint(
    workspace_id: str,
    source_id: int,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    """Delete a knowledge source and associated page/index ingestion artifacts."""
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    try:
        result = await delete_knowledge_source(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            source_id=source_id,
        )
        return {"status": "success", **result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.opt(exception=True).error("Error deleting knowledge source {source_id}: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to delete knowledge source")

@router.get("/admin/workspaces/{workspace_id}/ingestion-jobs")
async def get_ingestion_jobs(
    workspace_id: str,
    limit: int = 100,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """List ingestion jobs for a workspace."""
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
        
    try:
        jobs = await list_ingestion_jobs(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            limit=limit
        )
        return {"jobs": jobs, "status": "success", "count": len(jobs)}
    except Exception as e:
        logger.opt(exception=True).error("Error listing ingestion jobs: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to list ingestion jobs")

@router.get("/admin/ingestion-jobs/{job_id}")
async def get_ingestion_job_endpoint(
    job_id: int,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    """Get single ingestion job detail."""
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(IngestionJob).where(
                    IngestionJob.id == job_id,
                    IngestionJob.tenant_id == tenant_context.tenant_id,
                    IngestionJob.workspace_id == tenant_context.workspace_id,
                )
            )
            row = result.scalar_one_or_none()

        if not row:
            raise HTTPException(status_code=404, detail="Ingestion job not found")

        return {
            "status": "success",
            "job": {
                "id": row.id,
                "source_id": row.source_id,
                "source_type": row.source_type,
                "trigger_type": row.trigger_type,
                "status": row.status,
                "total_records": row.total_records,
                "processed_records": row.processed_records,
                "success_records": row.success_records,
                "failed_records": row.failed_records,
                "error_summary": row.error_summary,
                "details_json": row.details_json,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.opt(exception=True).error("Error getting ingestion job: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to get ingestion job")

@router.post("/admin/workspaces/{workspace_id}/knowledge-sources/upload")
async def upload_knowledge_source(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_name: str = Form(...),
    category: str = Form("document"),
    language: str = Form("English"),
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key)
):
    """Upload a PDF or DOCX file as a knowledge source and kick off ingestion job."""
    resolved_path_workspace_id = await resolve_workspace_alias(workspace_id)
    if resolved_path_workspace_id != tenant_context.workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
        
    try:
        import base64
        
        filename = file.filename.lower()
        if filename.endswith(".pdf"):
            source_type = "pdf"
        elif filename.endswith(".docx"):
            source_type = "docx"
        else:
            raise HTTPException(status_code=400, detail="Only .pdf and .docx files are supported")
            
        file_bytes = await file.read()
        file_content_b64 = base64.b64encode(file_bytes).decode("utf-8")
        
        source = await create_knowledge_source(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            source_name=source_name,
            source_type=source_type,
            source_uri=f"file://{file.filename}",
            source_config={
                "file_content": file_content_b64,
                "category": category,
                "language": language,
            },
            created_by="admin_upload"
        )
        
        job = await create_ingestion_job(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            source_id=source["id"],
            created_by="admin_upload"
        )
        
        async def run_job_bg(job_id: int):
            try:
                await run_ingestion_job(job_id)
            except Exception as e:
                logger.opt(exception=True).error("Background ingestion failed: {}")
                
        background_tasks.add_task(run_job_bg, job["id"])
        
        return {
            "status": "queued",
            "source": source,
            "job": job
        }
            
    except Exception as e:
        logger.error(f"Error uploading knowledge source: {e}", e)
        raise HTTPException(status_code=500, detail="Failed to upload and queue knowledge source")

@router.post("/admin/ingestion-jobs")
async def create_ingestion_job_endpoint(
    request: IngestionJobCreateRequest,
    background_tasks: BackgroundTasks,
    tenant_context: TenantContext = Depends(resolve_tenant_context),
    admin_key: str = Depends(verify_admin_key),
):
    """Create Phase 3 ingestion job and optionally start immediately."""
    try:
        job = await create_ingestion_job(
            tenant_id=tenant_context.tenant_id,
            workspace_id=tenant_context.workspace_id,
            source_id=request.sourceId,
            created_by=request.createdBy or "admin_api",
            trigger_type=request.triggerType,
        )

        if request.runNow:
            background_tasks.add_task(run_ingestion_job, job["id"])

        return {
            "status": "success",
            "job": job,
            "started": bool(request.runNow),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.opt(exception=True).error("Error creating ingestion job: {}", str(e))
        raise HTTPException(status_code=500, detail="Failed to create ingestion job")
