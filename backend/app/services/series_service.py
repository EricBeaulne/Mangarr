import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.series import Series
from app.models.chapter import Chapter
from app.models.volume import Volume
from app.models.root_folder import RootFolder
from app.services import metadata_service
from app.utils.naming import build_series_folder_name
from app.config import get_settings


def _get_or_create_volume(
    db: Session, series_id: int, volume_number: Optional[str]
) -> Optional[Volume]:
    """Return existing Volume or create a new one."""
    if volume_number is None:
        return None

    volume = (
        db.query(Volume)
        .filter(Volume.series_id == series_id, Volume.volume_number == volume_number)
        .first()
    )
    if not volume:
        volume = Volume(series_id=series_id, volume_number=volume_number)
        db.add(volume)
        db.flush()
    return volume


def _upsert_chapters(
    db: Session,
    series_id: int,
    metadata_provider: str,
    chapters_data: list,
) -> None:
    """Add new chapters from provider data; skip ones already in DB."""
    existing_ids = {
        row[0]
        for row in db.query(Chapter.mangadex_id)
        .filter(Chapter.series_id == series_id, Chapter.mangadex_id.isnot(None))
        .all()
    }

    for ch in chapters_data:
        ch_id = ch.get("id")
        if ch_id in existing_ids:
            continue

        volume_number = ch.get("volume_number")
        volume = _get_or_create_volume(db, series_id, volume_number)

        # Parse publish_at
        publish_at = None
        if ch.get("publish_at"):
            try:
                publish_at = datetime.fromisoformat(
                    ch["publish_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        chapter = Chapter(
            series_id=series_id,
            volume_id=volume.id if volume else None,
            metadata_provider=metadata_provider,
            mangadex_id=ch_id if metadata_provider == "mangadex" else None,
            chapter_number=ch.get("chapter_number"),
            volume_number=volume_number,
            title=ch.get("title"),
            language=ch.get("language", "en"),
            pages=ch.get("pages"),
            publish_at=publish_at,
            is_downloaded=False,
        )
        db.add(chapter)

    db.flush()


async def add_series(
    db: Session,
    metadata_id: str,
    metadata_provider: str = "mangadex",
    root_folder_id: int = None,
    monitor_status: str = "all",
) -> Series:
    """
    Fetch manga metadata from the specified provider, persist the series, and trigger
    cover download. Returns the created Series ORM object.
    """
    settings = get_settings()

    # Check if already in library
    existing = (
        db.query(Series)
        .filter(
            Series.metadata_provider == metadata_provider,
            Series.metadata_id == metadata_id,
        )
        .first()
    )
    if existing:
        return existing

    # Verify root folder exists
    root_folder = db.query(RootFolder).filter(RootFolder.id == root_folder_id).first()
    if not root_folder:
        raise ValueError(f"Root folder {root_folder_id} not found")

    # Fetch metadata from specified provider
    manga_data = await metadata_service.get_manga(metadata_provider, metadata_id)
    if not manga_data:
        raise ValueError(f"Manga {metadata_id} not found on {metadata_provider}")

    # Compute the series folder name
    series_folder_name = build_series_folder_name(
        template=settings.SERIES_FOLDER_FORMAT,
        title=manga_data["title"],
        year=manga_data.get("year"),
    )

    series = Series(
        mangadex_id=manga_data["id"] if metadata_provider == "mangadex" else None,
        metadata_provider=metadata_provider,
        metadata_id=manga_data["id"],
        title=manga_data["title"],
        alt_titles_json=manga_data.get("alt_titles_json"),
        description=manga_data.get("description"),
        status=manga_data.get("status"),
        year=manga_data.get("year"),
        content_rating=manga_data.get("content_rating"),
        original_language=manga_data.get("original_language"),
        tags_json=manga_data.get("tags_json"),
        cover_filename=manga_data.get("cover_filename"),
        root_folder_id=root_folder_id,
        series_folder=series_folder_name,
        monitor_status=monitor_status,
        metadata_updated_at=datetime.now(timezone.utc),
    )
    db.add(series)
    db.flush()  # Get the series ID

    # Fetch and persist chapters
    try:
        chapters_data = await metadata_service.get_manga_chapters(
            metadata_provider, metadata_id, lang=settings.DEFAULT_LANGUAGE
        )
        _upsert_chapters(db, series.id, metadata_provider, chapters_data)
    except Exception:
        pass  # Chapter fetch failure is non-fatal for adding a series

    db.commit()
    db.refresh(series)

    # Download cover in background (non-blocking)
    if manga_data.get("cover_filename"):
        try:
            await metadata_service.download_cover(
                metadata_provider, manga_data["id"], manga_data.get("cover_filename") or manga_data.get("cover_url")
            )
        except Exception:
            pass

    # Retroactively match any already-scanned files that belong to this series
    try:
        from app.services.scanner_service import rematch_for_series
        rematch_for_series(db, series)
    except Exception:
        pass  # Non-fatal: files can be matched on next scan

    return series


async def refresh_series(db: Session, series_id: int) -> Series:
    """
    Re-fetch metadata for a series from its provider, add new chapters, update fields.
    """
    settings = get_settings()

    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise ValueError(f"Series {series_id} not found")

    # Use the provider stored with the series
    provider = series.metadata_provider
    provider_id = series.metadata_id

    manga_data = await metadata_service.get_manga(provider, provider_id)
    if not manga_data:
        raise ValueError(f"Manga {provider_id} not found on {provider}")

    # Update metadata fields
    series.title = manga_data["title"]
    series.alt_titles_json = manga_data.get("alt_titles_json")
    series.description = manga_data.get("description")
    series.status = manga_data.get("status")
    series.year = manga_data.get("year")
    series.content_rating = manga_data.get("content_rating")
    series.original_language = manga_data.get("original_language")
    series.tags_json = manga_data.get("tags_json")
    series.cover_filename = manga_data.get("cover_filename")
    series.metadata_updated_at = datetime.now(timezone.utc)

    # Fetch new chapters
    try:
        chapters_data = await metadata_service.get_manga_chapters(
            provider, provider_id, lang=settings.DEFAULT_LANGUAGE
        )
        _upsert_chapters(db, series.id, provider, chapters_data)
    except Exception:
        pass

    db.commit()
    db.refresh(series)

    # Refresh cover
    if manga_data.get("cover_filename"):
        try:
            await metadata_service.download_cover(
                provider, manga_data["id"], manga_data.get("cover_filename") or manga_data.get("cover_url")
            )
        except Exception:
            pass

    return series


async def migrate_series_to_provider(
    db: Session,
    series_id: int,
    target_provider: str,
    target_id: str,
) -> Series:
    """
    Switch a series to a different metadata provider.
    Updates all metadata fields and re-downloads the cover.
    Existing chapters are preserved (only new ones would be added via upsert).
    """
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise ValueError(f"Series {series_id} not found")

    manga_data = await metadata_service.get_manga(target_provider, target_id)
    if not manga_data:
        raise ValueError(f"Manga {target_id} not found on {target_provider}")

    # Update provider identity
    series.metadata_provider = target_provider
    series.metadata_id = target_id
    if target_provider == "mangadex":
        series.mangadex_id = target_id
    else:
        series.mangadex_id = None

    # Update metadata fields
    series.title = manga_data["title"]
    series.alt_titles_json = manga_data.get("alt_titles_json")
    series.description = manga_data.get("description")
    series.status = manga_data.get("status")
    series.year = manga_data.get("year")
    series.content_rating = manga_data.get("content_rating")
    series.original_language = manga_data.get("original_language")
    series.tags_json = manga_data.get("tags_json")
    series.cover_filename = manga_data.get("cover_filename")
    series.metadata_updated_at = datetime.now(timezone.utc)

    # Upsert any chapters the new provider knows about (MangaBaka returns [])
    try:
        settings = get_settings()
        chapters_data = await metadata_service.get_manga_chapters(
            target_provider, target_id, lang=settings.DEFAULT_LANGUAGE
        )
        _upsert_chapters(db, series.id, target_provider, chapters_data)
    except Exception:
        pass

    db.commit()
    db.refresh(series)

    # Re-download cover from new provider
    if manga_data.get("cover_url") or manga_data.get("cover_filename"):
        try:
            await metadata_service.download_cover(
                target_provider,
                target_id,
                manga_data.get("cover_url") or manga_data.get("cover_filename"),
            )
        except Exception:
            pass

    return series


def delete_series(db: Session, series_id: int) -> bool:
    """
    Remove a series and all related records from the DB.
    Does NOT touch the filesystem.
    Returns True if deleted, False if not found.
    """
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        return False

    db.delete(series)
    db.commit()
    return True


def get_series_with_stats(db: Session, series_id: int) -> Optional[dict]:
    """
    Return series data with chapter_count, downloaded_count, missing_count.
    """
    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        return None

    all_chapters = db.query(Chapter).filter(Chapter.series_id == series_id).all()
    chapter_count = len(all_chapters)
    downloaded_count = sum(1 for c in all_chapters if c.is_downloaded)
    missing_count = chapter_count - downloaded_count

    return {
        "series": series,
        "chapter_count": chapter_count,
        "downloaded_count": downloaded_count,
        "missing_count": missing_count,
    }
