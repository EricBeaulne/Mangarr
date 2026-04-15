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


# ── Wanted / missing-chapters schemas ──────────────────────────────────────────

class MissingChapter(BaseModel):
    id: int
    chapter_number: Optional[str] = None
    volume_number: Optional[str] = None
    title: Optional[str] = None
    publish_at: Optional[str] = None


class WantedSeriesEntry(BaseModel):
    series_id: int
    title: str
    cover_filename: Optional[str] = None
    metadata_provider: str
    metadata_id: str
    monitor_status: str
    total_chapters: int
    missing_count: int
    missing: List[MissingChapter]


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


@router.get("/wanted", response_model=List[WantedSeriesEntry])
def get_wanted(db: Session = Depends(get_db)):
    """Return all series that are being monitored and have at least one missing chapter."""

    # All non-downloaded, non-synthetic chapters for monitored series
    missing_chapters = (
        db.query(Chapter)
        .join(Series, Series.id == Chapter.series_id)
        .filter(
            Chapter.is_downloaded == False,  # noqa: E712
            Chapter.metadata_provider != "synthetic",
            Series.monitor_status != "none",
        )
        .all()
    )

    # Group by series_id
    from collections import defaultdict
    by_series: dict = defaultdict(list)
    for ch in missing_chapters:
        by_series[ch.series_id].append(ch)

    if not by_series:
        return []

    # Fetch all relevant series in one query
    series_map = {
        s.id: s
        for s in db.query(Series).filter(Series.id.in_(list(by_series.keys()))).all()
    }

    def _safe_float(val: Optional[str]) -> float:
        try:
            return float(val) if val else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _sort_missing(chapters: list) -> list:
        with_ch = sorted(
            [c for c in chapters if c.chapter_number],
            key=lambda c: _safe_float(c.chapter_number),
        )
        vol_only = sorted(
            [c for c in chapters if not c.chapter_number],
            key=lambda c: _safe_float(c.volume_number),
        )
        return with_ch + vol_only

    # Also need total chapter count per series (all chapters, not just missing)
    total_counts = {
        series_id: db.query(Chapter)
        .filter(
            Chapter.series_id == series_id,
            Chapter.metadata_provider != "synthetic",
        )
        .count()
        for series_id in by_series
    }

    entries: List[WantedSeriesEntry] = []
    for series_id, chapters in by_series.items():
        s = series_map.get(series_id)
        if not s:
            continue

        sorted_missing = _sort_missing(chapters)
        missing_items = [
            MissingChapter(
                id=ch.id,
                chapter_number=ch.chapter_number,
                volume_number=ch.volume_number,
                title=ch.title,
                publish_at=ch.publish_at.isoformat() if ch.publish_at else None,
            )
            for ch in sorted_missing
        ]

        entries.append(
            WantedSeriesEntry(
                series_id=s.id,
                title=s.title,
                cover_filename=s.cover_filename,
                metadata_provider=s.metadata_provider,
                metadata_id=s.metadata_id,
                monitor_status=s.monitor_status,
                total_chapters=total_counts.get(series_id, 0),
                missing_count=len(missing_items),
                missing=missing_items,
            )
        )

    # Sort by missing_count descending
    entries.sort(key=lambda e: e.missing_count, reverse=True)
    return entries


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


@router.post("/{series_id}/refresh-anilist")
async def refresh_anilist(series_id: int, db: Session = Depends(get_db)):
    """Manually trigger an AniList lookup and save volumes/chapters totals."""
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    from app.providers.anilist import search_anilist
    data = await search_anilist(series.title)
    if not data:
        raise HTTPException(status_code=404, detail="No AniList match found")
    series.anilist_id = data.get("id")
    series.anilist_volumes = data.get("volumes")
    series.anilist_chapters = data.get("chapters")
    db.commit()
    db.refresh(series)
    return {
        "anilist_id": series.anilist_id,
        "anilist_volumes": series.anilist_volumes,
        "anilist_chapters": series.anilist_chapters,
    }


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


class FileReassignRequest(BaseModel):
    new_series_id: int


@router.post("/{series_id}/files/{file_id}/reassign", response_model=SeriesFileResponse)
def reassign_series_file(
    series_id: int,
    file_id: int,
    payload: FileReassignRequest,
    db: Session = Depends(get_db),
):
    """
    Move a tracked file from its current series to a different series.
    Unlinks any chapter from the old series and re-runs chapter linking
    against the new series.
    """
    f = db.query(ImportedFile).filter(
        ImportedFile.id == file_id,
        ImportedFile.series_id == series_id,
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found in this series")

    new_series = db.query(Series).filter(Series.id == payload.new_series_id).first()
    if not new_series:
        raise HTTPException(status_code=404, detail="Target series not found")

    # Clear old chapter link — the old chapter shouldn't stay marked as downloaded
    if f.chapter_id:
        old_ch = db.query(Chapter).filter(Chapter.id == f.chapter_id).first()
        if old_ch:
            old_ch.is_downloaded = False
            old_ch.imported_file_id = None
        f.chapter_id = None

    # Move the file to the new series
    f.series_id = new_series.id
    f.scan_state = "matched"
    db.flush()

    # Re-run chapter linking against the new series
    from app.services.scanner_service import _try_link_chapters
    _try_link_chapters(db, f, new_series, {
        "volume": f.parsed_volume_number,
        "chapter": f.parsed_chapter_number,
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


class RawMetadataResponse(BaseModel):
    """Raw provider API payloads — useful for debugging mismatched or missing data."""
    series_id: int
    title: str
    metadata_provider: str
    metadata_id: Optional[str] = None
    mangadex_id: Optional[str] = None
    anilist_id: Optional[int] = None
    primary: Optional[Dict[str, Any]] = None
    primary_error: Optional[str] = None
    anilist: Optional[Dict[str, Any]] = None
    anilist_error: Optional[str] = None


@router.get("/{series_id}/raw-metadata", response_model=RawMetadataResponse)
async def get_series_raw_metadata(series_id: int, db: Session = Depends(get_db)):
    """
    Fetch the raw (un-normalized) JSON payloads from each provider this series
    uses. Returns the primary provider response and, if an anilist_id is set,
    the AniList GraphQL response as well.
    """
    import httpx

    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    provider = series.metadata_provider or "mangadex"
    provider_id = series.metadata_id or series.mangadex_id

    primary: Optional[Dict[str, Any]] = None
    primary_error: Optional[str] = None
    headers = {"User-Agent": "Mangarr/1.0"}

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            if provider == "mangadex" and provider_id:
                resp = await client.get(
                    f"https://api.mangadex.org/manga/{provider_id}",
                    params={"includes[]": ["cover_art", "author", "artist"]},
                )
                resp.raise_for_status()
                primary = resp.json()
            elif provider == "mangabaka" and provider_id:
                resp = await client.get(f"https://api.mangabaka.dev/v1/series/{provider_id}")
                resp.raise_for_status()
                primary = resp.json()
            elif provider == "mangaupdates" and provider_id:
                resp = await client.get(f"https://api.mangaupdates.com/v1/series/{provider_id}")
                resp.raise_for_status()
                primary = resp.json()
            else:
                primary_error = f"No raw fetcher implemented for provider '{provider}' or missing id"
    except httpx.HTTPStatusError as e:
        primary_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:  # noqa: BLE001
        primary_error = f"{type(e).__name__}: {e}"

    anilist_payload: Optional[Dict[str, Any]] = None
    anilist_error: Optional[str] = None
    if series.anilist_id:
        try:
            query = """
            query ($id: Int) {
              Media(id: $id, type: MANGA) {
                id
                idMal
                title { romaji english native }
                synonyms
                volumes
                chapters
                status
                format
                countryOfOrigin
                startDate { year month day }
                endDate { year month day }
                averageScore
                popularity
                siteUrl
                description
                genres
                tags { name rank }
                staff(perPage: 5) { edges { role node { name { full } } } }
              }
            }
            """
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await client.post(
                    "https://graphql.anilist.co",
                    json={"query": query, "variables": {"id": series.anilist_id}},
                )
                resp.raise_for_status()
                anilist_payload = resp.json()
        except Exception as e:  # noqa: BLE001
            anilist_error = f"{type(e).__name__}: {e}"

    return RawMetadataResponse(
        series_id=series.id,
        title=series.title,
        metadata_provider=provider,
        metadata_id=series.metadata_id,
        mangadex_id=series.mangadex_id,
        anilist_id=series.anilist_id,
        primary=primary,
        primary_error=primary_error,
        anilist=anilist_payload,
        anilist_error=anilist_error,
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
