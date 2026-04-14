import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.providers.base import MetadataProvider

MANGAUPDATES_BASE_URL = "https://api.mangaupdates.com"
USER_AGENT = "Mangarr/1.0"

# Polite rate limiter for MangaUpdates
_semaphore = asyncio.Semaphore(3)


class MangaUpdatesProvider(MetadataProvider):
    name = "mangaupdates"

    @staticmethod
    def _parse_series(data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a MangaUpdates series object to our standard dict."""
        # Alt titles from 'associated' list: [{"title": "..."}, ...]
        alt_titles_list: List[Dict[str, str]] = []
        for assoc in data.get("associated") or []:
            title = assoc.get("title")
            if title and title != data.get("title"):
                alt_titles_list.append({"en": title})

        # Genres: [{"genre": "Action"}, ...]
        tags = [
            g["genre"]
            for g in (data.get("genres") or [])
            if isinstance(g, dict) and g.get("genre")
        ]

        # Cover URL from image.url.original
        image = data.get("image") or {}
        cover_url = (image.get("url") or {}).get("original")

        cover_filename = None
        if cover_url:
            series_id = str(data.get("series_id", "unknown"))
            ext = cover_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
            cover_filename = f"mangaupdates_{series_id}.{ext}"

        # Year: may be a string like "2000"
        year_raw = data.get("year")
        try:
            year = int(year_raw) if year_raw else None
        except (ValueError, TypeError):
            year = None

        # Status: MangaUpdates returns strings like "Ongoing", "Complete", "Hiatus"
        status_map = {
            "ongoing": "ongoing",
            "complete": "completed",
            "completed": "completed",
            "hiatus": "hiatus",
            "cancelled": "cancelled",
            "discontinued": "cancelled",
        }
        raw_status = (data.get("status") or "").lower().strip()
        # MangaUpdates often embeds volume count in status, e.g. "Complete (12 vols)"
        for key in status_map:
            if key in raw_status:
                raw_status = status_map[key]
                break
        else:
            raw_status = raw_status or None

        return {
            "id": str(data.get("series_id")),
            "title": data.get("title") or "Unknown",
            "alt_titles_json": json.dumps(alt_titles_list),
            "description": data.get("description") or None,
            "status": raw_status,
            "year": year,
            "content_rating": None,  # MangaUpdates doesn't have a direct rating field
            "original_language": "ja",
            "tags_json": json.dumps(tags),
            "cover_filename": cover_filename,
            "cover_url": cover_url,
        }

    async def search(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Search MangaUpdates using the POST /v1/series/search endpoint."""
        page = (offset // limit) + 1

        payload = {
            "search": query,
            "perpage": limit,
            "page": page,
            "orderby": "score",
        }

        async with _semaphore:
            async with httpx.AsyncClient(
                base_url=MANGAUPDATES_BASE_URL,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
                timeout=30.0,
            ) as client:
                try:
                    resp = await client.post("/v1/series/search", json=payload)
                    resp.raise_for_status()
                    body = resp.json()
                except Exception:
                    return [], 0

        results_raw = (body.get("results") or [])
        total = (body.get("total_hits") or 0)

        results = []
        for item in results_raw:
            record = item.get("record") or item
            results.append(self._parse_series(record))

        return results, total

    async def get_manga(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single series by MangaUpdates series_id (integer string)."""
        async with _semaphore:
            async with httpx.AsyncClient(
                base_url=MANGAUPDATES_BASE_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
            ) as client:
                try:
                    resp = await client.get(f"/v1/series/{provider_id}")
                    if resp.status_code == 404:
                        return None
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    return None

        return self._parse_series(data)

    async def get_chapters(
        self, provider_id: str, lang: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Fetch chapter/volume list from MangaUpdates releases.

        MangaUpdates has no per-series chapters endpoint. We query
        POST /v1/releases/search by series title, filter results to
        exact title matches, and deduplicate by chapter number to build
        a unique chapter list with volume associations.
        """
        # First, fetch the series title so we can filter releases
        series_data = await self.get_manga(provider_id)
        if not series_data:
            return []

        series_title = series_data.get("title", "")
        if not series_title:
            return []

        # Collect all matching releases, paginating until exhausted
        all_releases: List[Dict[str, Any]] = []
        page = 1
        perpage = 100
        max_pages = 20  # safety cap (2000 releases ought to be enough for anyone)

        async with httpx.AsyncClient(
            base_url=MANGAUPDATES_BASE_URL,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=30.0,
        ) as client:
            while page <= max_pages:
                payload = {
                    "search": series_title,
                    "perpage": perpage,
                    "page": page,
                    "orderby": "chap",
                }
                try:
                    async with _semaphore:
                        resp = await client.post("/v1/releases/search", json=payload)
                        resp.raise_for_status()
                        body = resp.json()
                except Exception:
                    break

                page_results = body.get("results") or []
                if not page_results:
                    break

                # Filter to releases whose title exactly matches our series
                for item in page_results:
                    record = item.get("record") or item
                    if (record.get("title") or "").lower() == series_title.lower():
                        all_releases.append(record)

                # If fewer results than requested, we've reached the end
                if len(page_results) < perpage:
                    break

                page += 1

        if not all_releases:
            return []

        # Deduplicate by chapter number; track the best (highest-quality) entry per chapter
        # Key: chapter_number string (or None for volume-only entries)
        seen: Dict[str, Dict[str, Any]] = {}
        volume_only: List[Dict[str, Any]] = []  # releases with volume but no chapter

        for rel in all_releases:
            chapter_str = (rel.get("chapter") or "").strip()
            volume_str = (rel.get("volume") or "").strip()
            release_date = rel.get("release_date")

            if chapter_str:
                if chapter_str not in seen:
                    seen[chapter_str] = {
                        "id": f"mu_{provider_id}_ch_{chapter_str}",
                        "chapter_number": chapter_str,
                        "volume_number": volume_str or None,
                        "title": None,
                        "language": "en",
                        "pages": None,
                        "publish_at": release_date,
                    }
            elif volume_str:
                # Volume-only release — we'll add it only if no chapters claim this volume
                volume_only.append({
                    "id": f"mu_{provider_id}_vol_{volume_str}",
                    "chapter_number": None,
                    "volume_number": volume_str,
                    "title": f"Volume {volume_str}",
                    "language": "en",
                    "pages": None,
                    "publish_at": release_date,
                })

        # Build final chapter list from deduplicated chapter entries
        chapters = list(seen.values())

        # Add volume-only entries for volumes not already covered by chapter releases
        volumes_with_chapters = {
            ch["volume_number"]
            for ch in chapters
            if ch.get("volume_number")
        }
        seen_vol_only: set = set()
        for vol_entry in volume_only:
            vol = vol_entry["volume_number"]
            if vol not in volumes_with_chapters and vol not in seen_vol_only:
                chapters.append(vol_entry)
                seen_vol_only.add(vol)

        # Sort: chapters with numbers first (ascending), then volume-only entries
        def _sort_key(ch: Dict[str, Any]):
            ch_num = ch.get("chapter_number")
            vol_num = ch.get("volume_number")
            try:
                ch_f = float(ch_num) if ch_num else None
            except (ValueError, TypeError):
                ch_f = None
            try:
                vol_f = float(vol_num) if vol_num else None
            except (ValueError, TypeError):
                vol_f = None

            if ch_f is not None:
                return (0, ch_f, 0.0)
            if vol_f is not None:
                return (1, vol_f, 0.0)
            return (2, 0.0, 0.0)

        chapters.sort(key=_sort_key)
        return chapters

    async def download_cover(self, provider_id: str, cover_info: Any) -> Optional[str]:
        """Download cover image from MangaUpdates CDN URL."""
        if not cover_info:
            return None

        url = str(cover_info)

        settings = get_settings()
        covers_dir = os.path.join(settings.DATA_DIR, "covers")
        os.makedirs(covers_dir, exist_ok=True)

        ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        save_name = f"mangaupdates_{provider_id}.{ext}"
        save_path = os.path.join(covers_dir, save_name)

        if os.path.exists(save_path):
            return save_name

        try:
            async with _semaphore:
                async with httpx.AsyncClient(
                    headers={"User-Agent": USER_AGENT},
                    timeout=60.0,
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(url)
                    if resp.status_code == 404:
                        return None
                    resp.raise_for_status()
                    with open(save_path, "wb") as fh:
                        fh.write(resp.content)
            return save_name
        except Exception:
            return None
