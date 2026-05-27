from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.document_analysis.extraction import save_upload
from app.document_analysis.pipeline import run_document_analysis
from app.document_analysis.schemas import (
    DocumentAnalyzeRequest,
    DocumentAnalyzeResponse,
    DocumentUploadResponse,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    meta = await save_upload(file)
    return DocumentUploadResponse(
        document_id=meta["document_id"],
        filename=meta["filename"],
        detected_type=meta["detected_type"],
        size_bytes=meta["size_bytes"],
    )


@router.post("/analyze", response_model=DocumentAnalyzeResponse)
async def analyze_document(
    body: DocumentAnalyzeRequest,
    session: AsyncSession = Depends(get_session),
):
    return await run_document_analysis(
        session,
        document_id=body.document_id,
        user_id=body.user_id,
        action=body.action,
        athlete_name=body.athlete_name,
    )
