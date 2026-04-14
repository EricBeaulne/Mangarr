import asyncio
import unicodedata
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.services import metadata_service
from app.schemas.search import MangaSearchResult, MangaSearchResponse, ChapterSearchResult
from app.models.series import Series

router = APIRouter(prefix="/search", tags=["search"])


def _cover_url_for(m: dict, provider: str) -> Optional[str]:
    """Build a usable cover URL for a search result dict."""
    if provider == "mangadex" and m.get("cover_filename") and m.get("id"):
        from app.providers.mangadex import MangaDexProvider
        return MangaDexProvider()._get_cover_url(m["id"], m["cover_filename"])
    if provider == "mangabaka":
        return m.get("cover_url")
    return None


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/accents — used to deduplicate across providers."""
    t = unicodedata.normalize("NFKD", title.lower())
    t = re.sub(r"[^\w\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _build_result(m: dict, provider: str) -> MangaSearchResult:
    return MangaSearchResult(
        id=m["id"],
        title=m["title"],
        alt_titles=[],
        description=m.get("description"),
        status=m.get("status"),
        year=m.get("year"),
        content_rating=m.get("content_rating"),
        original_language=m.get("original_language"),
        tags=[],
        cover_url=_cover_url_for(m, provider),
        cover_filename=m.get("cover_filename"),
        provider=provider,
    )


@router.get("/manga", response_model=MangaSearchResponse)
async def search_manga(
    q: str = Query(..., min_length=1, description="Search query"),
    provider: str = Query("auto", description="Metadata provider ('mangadex', 'mangabaka', or 'auto')"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Search for manga by title.

    When provider='auto', searches MangaDex first (full chapter data) then
    fills in any gaps with MangaBaka results not already found on MangaDex.
    """
    if provider == "auto":
        # Search both providers in parallel
        try:
            (mdex_results, _), (baka_results, _) = await asyncio.gather(
                metadata_service.search_manga(q, provider="mangadex", limit=limit, offset=offset),
                metadata_service.search_manga(q, provider="mangabaka", limit=limit, offset=offset),
                return_exceptions=False,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Metadata provider error: {exc}")

        # Build result list: MangaDex entries first, then MangaBaka-only entries
        seen_titles: set[str] = set()
        manga_results: list[MangaSearchResult] = []

        for m in mdex_results:
            manga_results.append(_build_result(m, "mangadex"))
            seen_titles.add(_normalize_title(m["title"]))

        for m in baka_results:
            if _normalize_title(m["title"]) not in seen_titles:
                manga_results.append(_build_result(m, "mangabaka"))

        return MangaSearchResponse(
            results=manga_results,
            total=len(manga_results),
            limit=limit,
            offset=offset,
        )

    # Single provider
    try:
        results, total = await metadata_service.search_manga(
            q, provider=provider, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Metadata provider error: {exc}")

    return MangaSearchResponse(
        results=[_build_result(m, provider) for m in results],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/manga/{manga_id}", response_model=MangaSearchResult)
async def get_manga_detail(
    manga_id: str,
    provider: str = Query("mangadex", description="Metadata provider"),
):
    """Get full details for a single manga from the specified metadata provider."""
    try:
        manga_data = await metadata_service.get_manga(provider, manga_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Metadata provider error: {exc}")

    if not manga_data:
        raise HTTPException(status_code=404, detail=f"Manga {manga_id} not found on {provider}")

    cover_url = None
    if manga_data.get("cover_filename") and manga_data.get("id"):
        if provider == "mangadex":
            from app.providers.mangadex import MangaDexProvider
            provider_instance = MangaDexProvider()
            cover_url = provider_instance._get_cover_url(
                manga_data["id"], manga_data["cover_filename"]
            )
        elif provider == "mangabaka" and manga_data.get("cover_url"):
            cover_url = manga_data.get("cover_url")

    import json

    alt_titles = []
    if manga_data.get("alt_titles_json"):
        try:
            alt_titles = json.loads(manga_data["alt_titles_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    tags = []
    if manga_data.get("tags_json"):
        try:
            tags = json.loads(manga_data["tags_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    return MangaSearchResult(
        id=manga_data["id"],
        title=manga_data["title"],
        alt_titles=alt_titles,
        description=manga_data.get("description"),
        status=manga_data.get("status"),
        year=manga_data.get("year"),
        content_rating=manga_data.get("content_rating"),
        original_language=manga_data.get("original_language"),
        tags=tags,
        cover_url=cover_url,
        cover_filename=manga_data.get("cover_filename"),
    )


@router.get("/manga/{manga_id}/chapters", response_model=List[ChapterSearchResult])
async def get_manga_chapters(
    manga_id: str,
    provider: str = Query("mangadex", description="Metadata provider"),
    lang: str = Query("en", description="Language code"),
):
    """Fetch all chapters for a manga from the specified metadata provider."""
    try:
        chapters = await metadata_service.get_manga_chapters(provider, manga_id, lang=lang)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Metadata provider error: {exc}")

    return [
        ChapterSearchResult(
            id=ch["id"],
            chapter_number=ch.get("chapter_number"),
            volume_number=ch.get("volume_number"),
            title=ch.get("title"),
            language=ch.get("language", lang),
            pages=ch.get("pages"),
            publish_at=ch.get("publish_at"),
        )
        for ch in chapters
    ]
