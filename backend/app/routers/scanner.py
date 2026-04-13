from typing import List, Optional
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.imported_file import ImportedFile
from app.services import scanner_service
from app.services.scanner_service import ScanJob

router = APIRouter(prefix="/scanner", tags=["scanner"])


class ScanJobResponse(BaseModel):
    status: str
    total_files: int
    processed_files: int
    matched: int
    unmatched: int
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    auto_add_status: str = "idle"
    auto_add_total: int = 0
    auto_add_done: int = 0
    auto_added: int = 0


class ManualMatchRequest(BaseModel):
    imported_file_id: int
    chapter_id: Optional[int] = None
    series_id: Optional[int] = None


class ImportedFileResponse(BaseModel):
    id: int
    series_id: Optional[int] = None
    chapter_id: Optional[int] = None
    file_path: str
    file_name: str
    file_size: int
    extension: str
    parsed_series_title: Optional[str] = None
    parsed_chapter_number: Optional[str] = None
    parsed_volume_number: Optional[str] = None
    scan_state: str

    model_config = {"from_attributes": True}


def _job_to_response(job: ScanJob) -> ScanJobResponse:
    return ScanJobResponse(
        status=job.status,
        total_files=job.total_files,
        processed_files=job.processed_files,
        matched=job.matched,
        unmatched=job.unmatched,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        error=job.error,
        auto_add_status=job.auto_add_status,
        auto_add_total=job.auto_add_total,
        auto_add_done=job.auto_add_done,
        auto_added=job.auto_added,
    )


@router.post("/scan", response_model=ScanJobResponse, status_code=202)
async def trigger_full_scan():
    """Trigger a full scan of all root folders."""
    job = await scanner_service.trigger_scan()
    return _job_to_response(job)


@router.post("/scan/{root_folder_id}", response_model=ScanJobResponse, status_code=202)
async def trigger_folder_scan(root_folder_id: int):
    """Trigger a scan of a specific root folder."""
    job = await scanner_service.trigger_scan(root_folder_id=root_folder_id)
    return _job_to_response(job)


@router.get("/status", response_model=ScanJobResponse)
def get_scan_status():
    """Return the current scan job state."""
    job = scanner_service.get_scan_job()
    return _job_to_response(job)


@router.get("/unmatched", response_model=List[ImportedFileResponse])
def list_unmatched(db: Session = Depends(get_db)):
    """List all imported files that could not be matched to a series."""
    files = (
        db.query(ImportedFile)
        .filter(ImportedFile.scan_state == "unmatched")
        .order_by(ImportedFile.file_name)
        .all()
    )
    return [ImportedFileResponse.model_validate(f) for f in files]


@router.post("/match", response_model=ImportedFileResponse)
def manual_match(payload: ManualMatchRequest, db: Session = Depends(get_db)):
    """Manually classify an imported file to a chapter or series."""
    try:
        if payload.chapter_id is not None:
            imported = scanner_service.manual_match(
                db,
                imported_file_id=payload.imported_file_id,
                chapter_id=payload.chapter_id,
            )
        elif payload.series_id is not None:
            imported = scanner_service.manual_assign_series(
                db,
                imported_file_id=payload.imported_file_id,
                series_id=payload.series_id,
            )
        else:
            raise HTTPException(
                status_code=422,
                detail="Either chapter_id or series_id is required",
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Match failed: {exc}")

    return ImportedFileResponse.model_validate(imported)


@router.post("/cancel")
def cancel_scan():
    """Request cancellation of the active scan job."""
    if scanner_service.cancel_scan():
        return {"message": "Scan cancellation requested"}
    return {"message": "No running scan to cancel"}
