from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.series import Series
from app.models.chapter import Chapter
from app.models.volume import Volume
from app.models.imported_file import ImportedFile
from app.schemas.series import (
    SeriesCreate,
    SeriesUpdate,
    SeriesResponse,
    SeriesWithStats,
    SeriesListResponse,
    VolumeResponse,
)
from app.schemas.chapter import ChapterResponse
from app.services import series_service, metadata_service

router = APIRouter(prefix="/series", tags=["series"])


# ── Search result schema ────────────────────────────────────────────────────

class SearchResult(BaseModel):
    """Search result from metadata provider."""
    id: str
    title: str
    year: Optional[int] = None
    description: Optional[str] = None
    cover_filename: Optional[str] = None

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    """Response from series search endpoint."""
    results: List[SearchResult]
    total: int
    provider: str


# ── File-mapping schemas ────────────────────────────────────────────────────

class LinkedChapter(BaseModel):
    id: int
    chapter_number: Optional[str] = None
    volume_number: Optional[str] = None
    title: Optional[str] = None

    model_config = {"from_attributes": True}


class SeriesFileResponse(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_size: int
    extension: str
    parsed_series_title: Optional[str] = None
    parsed_volume_number: Optional[str] = None
    parsed_chapter_number: Optional[str] = None
    scan_state: str
    chapter_id: Optional[int] = None
    linked_chapter: Optional[LinkedChapter] = None

    model_config = {"from_attributes": True}


class FileRemapRequest(BaseModel):
    """Update the volume/chapter mapping for a single file and re-link."""
    parsed_volume_number: Optional[str] = None
    parsed_chapter_number: Optional[str] = None


@router.get("/search", response_model=SearchResponse)
async def search_series(
    q: str = Query(..., description="Search query"),
    provider: str = Query("mangadex", description="Metadata provider to search"),
    limit: int = Query(20, description="Maximum number of results"),
    offset: int = Query(0, description="Result offset for pagination"),
):
    """Search for manga from the specified metadata provider."""
    try:
        results, total = await metadata_service.search_manga(
            q, provider=provider, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}")

    search_results = [
        SearchResult(
            id=r.get("id"),
            title=r.get("title"),
            year=r.get("year"),
            description=r.get("description"),
            cover_filename=r.get("cover_filename"),
        )
        for r in results
    ]
    return SearchResponse(results=search_results, total=total, provider=provider)


@router.get("", response_model=SeriesListResponse)
def list_series(
    status: Optional[str] = Query(None, description="Filter by status"),
    monitor_status: Optional[str] = Query(None, description="Filter by monitor status"),
    db: Session = Depends(get_db),
):
    """List all series in the library."""
    query = db.query(Series)

    if status:
        query = query.filter(Series.status == status)
    if monitor_status:
        query = query.filter(Series.monitor_status == monitor_status)

    series_list = query.order_by(Series.title).all()
    return SeriesListResponse(
        items=[SeriesResponse.model_validate(s) for s in series_list],
        total=len(series_list),
    )


@router.post("", response_model=SeriesResponse, status_code=201)
async def add_series(
    payload: SeriesCreate,
    db: Session = Depends(get_db),
):
    """Add a manga to the library from the specified metadata provider."""
    try:
        series = await series_service.add_series(
            db,
            metadata_id=payload.metadata_id,
            metadata_provider=payload.metadata_provider,
            root_folder_id=payload.root_folder_id,
            monitor_status=payload.monitor_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to add series: {exc}")

    return SeriesResponse.model_validate(series)


@router.get("/{series_id}", response_model=SeriesWithStats)
def get_series(series_id: int, db: Session = Depends(get_db)):
    """Get a single series with volumes, chapters, and stats."""
    result = series_service.get_series_with_stats(db, series_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found")

    series: Series = result["series"]

    # Load volumes with their chapters
    volumes = db.query(Volume).filter(Volume.series_id == series_id).all()
    volumes_response = []
    for vol in volumes:
        vol_chapters = (
            db.query(Chapter)
            .filter(Chapter.volume_id == vol.id)
            .order_by(Chapter.chapter_number)
            .all()
        )
        volumes_response.append(
            VolumeResponse(
                id=vol.id,
                series_id=vol.series_id,
                volume_number=vol.volume_number,
                cover_filename=vol.cover_filename,
                chapters=[ChapterResponse.model_validate(c) for c in vol_chapters],
            )
        )

    # Chapters without a volume
    all_chapters = (
        db.query(Chapter)
        .filter(Chapter.series_id == series_id)
        .order_by(Chapter.chapter_number)
        .all()
    )

    response = SeriesWithStats(
        **SeriesResponse.model_validate(series).model_dump(),
        chapter_count=result["chapter_count"],
        downloaded_count=result["downloaded_count"],
        missing_count=result["missing_count"],
        volumes=volumes_response,
        chapters=[ChapterResponse.model_validate(c) for c in all_chapters],
    )
    return response


@router.put("/{series_id}", response_model=SeriesResponse)
def update_series(
    series_id: int,
    payload: SeriesUpdate,
    db: Session = Depends(get_db),
):
    """Update monitor status or root folder for a series."""
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found")

    if payload.monitor_status is not None:
        valid_statuses = {"all", "future", "none"}
        if payload.monitor_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid monitor_status. Must be one of: {valid_statuses}",
            )
        series.monitor_status = payload.monitor_status

    if payload.root_folder_id is not None:
        from app.models.root_folder import RootFolder
        folder = db.query(RootFolder).filter(RootFolder.id == payload.root_folder_id).first()
        if not folder:
            raise HTTPException(
                status_code=400,
                detail=f"Root folder {payload.root_folder_id} not found",
            )
        series.root_folder_id = payload.root_folder_id

    db.commit()
    db.refresh(series)
    return SeriesResponse.model_validate(series)


@router.delete("/{series_id}", status_code=204)
def delete_series(series_id: int, db: Session = Depends(get_db)):
    """Remove a series from the library (does NOT delete files)."""
    deleted = series_service.delete_series(db, series_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Series {series_id} not found")


@router.post("/{series_id}/refresh", response_model=SeriesResponse)
async def refresh_series(series_id: int, db: Session = Depends(get_db)):
    """Re-fetch metadata and chapters from MangaDex."""
    try:
        series = await series_service.refresh_series(db, series_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}")

    return SeriesResponse.model_validate(series)


@router.get("/{series_id}/files", response_model=List[SeriesFileResponse])
def list_series_files(series_id: int, db: Session = Depends(get_db)):
    """List all physical files matched to this series, with their chapter mapping."""
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    files = (
        db.query(ImportedFile)
        .filter(ImportedFile.series_id == series_id)
        .order_by(ImportedFile.parsed_volume_number, ImportedFile.parsed_chapter_number, ImportedFile.file_name)
        .all()
    )

    result = []
    for f in files:
        linked = None
        if f.chapter_id:
            ch = db.query(Chapter).filter(Chapter.id == f.chapter_id).first()
            if ch:
                linked = LinkedChapter(
                    id=ch.id,
                    chapter_number=ch.chapter_number,
                    volume_number=ch.volume_number,
                    title=ch.title,
                )
        result.append(
            SeriesFileResponse(
                id=f.id,
                file_name=f.file_name,
                file_path=f.file_path,
                file_size=f.file_size,
                extension=f.extension,
                parsed_series_title=f.parsed_series_title,
                parsed_volume_number=f.parsed_volume_number,
                parsed_chapter_number=f.parsed_chapter_number,
                scan_state=f.scan_state,
                chapter_id=f.chapter_id,
                linked_chapter=linked,
            )
        )
    return result


@router.put("/{series_id}/files/{file_id}", response_model=SeriesFileResponse)
def remap_series_file(
    series_id: int,
    file_id: int,
    payload: FileRemapRequest,
    db: Session = Depends(get_db),
):
    """
    Update the volume/chapter numbers for a file and re-run chapter linking.
    Use this to correct a wrong auto-detection.
    """
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    f = db.query(ImportedFile).filter(
        ImportedFile.id == file_id,
        ImportedFile.series_id == series_id,
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    # Clear old chapter link
    if f.chapter_id:
        old_ch = db.query(Chapter).filter(Chapter.id == f.chapter_id).first()
        if old_ch:
            old_ch.is_downloaded = False
            old_ch.imported_file_id = None
        f.chapter_id = None

    # Apply new mapping values
    f.parsed_volume_number = payload.parsed_volume_number
    f.parsed_chapter_number = payload.parsed_chapter_number
    f.scan_state = "matched"
    db.flush()

    # Re-run chapter linking with the new values
    from app.services.scanner_service import _try_link_chapters
    _try_link_chapters(db, f, series, {
        "volume": payload.parsed_volume_number,
        "chapter": payload.parsed_chapter_number,
    })

    db.commit()
    db.refresh(f)

    linked = None
    if f.chapter_id:
        ch = db.query(Chapter).filter(Chapter.id == f.chapter_id).first()
        if ch:
            linked = LinkedChapter(
                id=ch.id,
                chapter_number=ch.chapter_number,
                volume_number=ch.volume_number,
                title=ch.title,
            )

    return SeriesFileResponse(
        id=f.id,
        file_name=f.file_name,
        file_path=f.file_path,
        file_size=f.file_size,
        extension=f.extension,
        parsed_series_title=f.parsed_series_title,
        parsed_volume_number=f.parsed_volume_number,
        parsed_chapter_number=f.parsed_chapter_number,
        scan_state=f.scan_state,
        chapter_id=f.chapter_id,
        linked_chapter=linked,
    )


@router.delete("/{series_id}/files/{file_id}", status_code=204)
def delete_series_file(
    series_id: int,
    file_id: int,
    delete_from_disk: bool = Query(default=False, description="Also delete the physical file"),
    db: Session = Depends(get_db),
):
    """
    Remove a tracked file from the library.
    Unlinks any matched chapter and optionally deletes the file from disk.
    """
    import os

    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    f = db.query(ImportedFile).filter(
        ImportedFile.id == file_id,
        ImportedFile.series_id == series_id,
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = f.file_path

    # Unlink chapter
    if f.chapter_id:
        ch = db.query(Chapter).filter(Chapter.id == f.chapter_id).first()
        if ch:
            ch.is_downloaded = False
            ch.imported_file_id = None

    db.delete(f)
    db.commit()

    if delete_from_disk:
        try:
            os.remove(file_path)
        except OSError:
            pass  # File already gone — not an error


# ── Migration ───────────────────────────────────────────────────────────────

class MigrateSeriesRequest(BaseModel):
    target_provider: str
    target_id: str


class MigrateResult(BaseModel):
    series_id: int
    title: str
    status: str          # "migrated" | "skipped" | "no_match" | "error"
    new_provider: Optional[str] = None
    new_provider_id: Optional[str] = None
    error: Optional[str] = None


class BulkMigrateRequest(BaseModel):
    target_provider: str = "mangabaka"
    series_ids: Optional[List[int]] = None  # None = all series not already on target


@router.post("/{series_id}/migrate", response_model=MigrateResult)
async def migrate_series(
    series_id: int,
    payload: MigrateSeriesRequest,
    db: Session = Depends(get_db),
):
    """Migrate a single series to a different metadata provider."""
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    try:
        updated = await series_service.migrate_series_to_provider(
            db, series_id, payload.target_provider, payload.target_id
        )
        return MigrateResult(
            series_id=updated.id,
            title=updated.title,
            status="migrated",
            new_provider=updated.metadata_provider,
            new_provider_id=updated.metadata_id,
        )
    except Exception as exc:
        return MigrateResult(
            series_id=series_id,
            title=series.title,
            status="error",
            error=str(exc),
        )


@router.post("/bulk-migrate", response_model=List[MigrateResult])
async def bulk_migrate_to_provider(
    payload: BulkMigrateRequest,
    db: Session = Depends(get_db),
):
    """
    Bulk-migrate library series to a different provider.

    For each series not already on the target provider, searches by title and
    migrates if a match is found. Existing chapters are preserved.
    """
    from app.services import metadata_service as meta_svc

    if payload.series_ids:
        candidates = db.query(Series).filter(Series.id.in_(payload.series_ids)).all()
    else:
        candidates = (
            db.query(Series)
            .filter(Series.metadata_provider != payload.target_provider)
            .all()
        )

    results: List[MigrateResult] = []

    for series in candidates:
        try:
            search_results, _ = await meta_svc.search_manga(
                series.title, provider=payload.target_provider, limit=5
            )
        except Exception as exc:
            results.append(MigrateResult(
                series_id=series.id,
                title=series.title,
                status="error",
                error=f"Search failed: {exc}",
            ))
            continue

        if not search_results:
            results.append(MigrateResult(
                series_id=series.id,
                title=series.title,
                status="no_match",
            ))
            continue

        # Pick the best title match
        series_title_lower = series.title.lower()
        best = search_results[0]
        for r in search_results:
            if r.get("title", "").lower() == series_title_lower:
                best = r
                break

        target_id = str(best["id"])
        try:
            updated = await series_service.migrate_series_to_provider(
                db, series.id, payload.target_provider, target_id
            )
            results.append(MigrateResult(
                series_id=updated.id,
                title=updated.title,
                status="migrated",
                new_provider=updated.metadata_provider,
                new_provider_id=updated.metadata_id,
            ))
        except Exception as exc:
            results.append(MigrateResult(
                series_id=series.id,
                title=series.title,
                status="error",
                error=str(exc),
            ))

    return results
