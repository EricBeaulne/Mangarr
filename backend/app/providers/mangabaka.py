import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.providers.base import MetadataProvider

MANGABAKA_BASE_URL = "https://api.mangabaka.dev"
USER_AGENT = "Mangarr/1.0"

# Rate limiter: at most 5 concurrent requests (API limit: 30/min search, 120/min lookup)
_semaphore = asyncio.Semaphore(5)


class MangaBakaProvider(MetadataProvider):
    name = "mangabaka"

    @staticmethod
    def _parse_manga_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a MangaBaka series object to the standard provider dict.

        MangaBaka series response shape (relevant fields):
          id              int
          title           str
          native_title    str
          romanized_title str
          secondary_titles  { lang: [{ type, title, note }] }
          description     str
          status          str  ("releasing" | "completed" | "hiatus" | "cancelled")
          year            int
          content_rating  str  ("safe" | "suggestive" | "erotica" | "pornographic")
          genres          [str]
          cover           { raw: { url }, x350: { x1, x2, x3 }, ... }
        """
        # Alt titles: flatten secondary_titles into [{lang: title}, ...]
        alt_titles_list: List[Dict[str, str]] = []
        for lang, entries in (data.get("secondary_titles") or {}).items():
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and "title" in entry:
                        alt_titles_list.append({lang: entry["title"]})

        # Tags / genres — MangaBaka genres are plain strings
        tags = [g for g in (data.get("genres") or []) if isinstance(g, str)]

        # Cover: prefer the 350px CDN thumbnail for downloads; store raw URL as cover_url
        cover_obj = data.get("cover") or {}
        raw_cover_url = (cover_obj.get("raw") or {}).get("url")
        # Use x350@1 CDN URL for downloading if available, else fall back to raw
        cdn_350 = (cover_obj.get("x350") or {}).get("x1") or raw_cover_url

        # Derive a stable filename: mangabaka_{id}.{ext}
        cover_filename = None
        if raw_cover_url:
            ext = raw_cover_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
            cover_filename = f"mangabaka_{data['id']}.{ext}"

        # Map MangaBaka status strings to our internal values
        status_map = {
            "releasing": "ongoing",
            "completed": "completed",
            "hiatus": "hiatus",
            "cancelled": "cancelled",
            "on_hiatus": "hiatus",
        }
        raw_status = (data.get("status") or "").lower()
        status = status_map.get(raw_status, raw_status) or None

        description = data.get("description") or None

        return {
            "id": str(data.get("id")),
            "title": data.get("title") or "Unknown",
            "alt_titles_json": json.dumps(alt_titles_list),
            "description": description,
            "status": status,
            "year": data.get("year"),
            "content_rating": data.get("content_rating"),
            "original_language": "ja",
            "tags_json": json.dumps(tags),
            "cover_filename": cover_filename,
            "cover_url": cdn_350,  # Used by download_cover
        }

    async def search(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Search MangaBaka. Uses page-based pagination (offset → page number)."""
        page = (offset // limit) + 1

        async with _semaphore:
            async with httpx.AsyncClient(
                base_url=MANGABAKA_BASE_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
            ) as client:
                try:
                    resp = await client.get(
                        "/v1/series/search",
                        params={"q": query, "limit": limit, "page": page},
                    )
                    resp.raise_for_status()
                    body = resp.json()
                except Exception:
                    return [], 0

        items = body.get("data") or []
        total = (body.get("pagination") or {}).get("count", len(items))
        results = [self._parse_manga_data(m) for m in items]
        return results, total

    async def get_manga(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single series by MangaBaka integer ID."""
        async with _semaphore:
            async with httpx.AsyncClient(
                base_url=MANGABAKA_BASE_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
            ) as client:
                try:
                    resp = await client.get(f"/v1/series/{provider_id}")
                    if resp.status_code == 404:
                        return None
                    resp.raise_for_status()
                    body = resp.json()
                except Exception:
                    return None

        manga_data = body.get("data") if isinstance(body, dict) else body
        if not manga_data:
            return None
        return self._parse_manga_data(manga_data)

    async def get_chapters(
        self, provider_id: str, lang: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        MangaBaka does not expose a per-series chapters endpoint.
        Chapter tracking is handled entirely by the file scanner.
        """
        return []

    async def download_cover(self, provider_id: str, cover_info: Any) -> Optional[str]:
        """
        Download a cover from MangaBaka CDN.

        cover_info is the cover_url stored in the metadata dict (a CDN URL).
        The file is saved as mangabaka_{id}.{ext} in DATA_DIR/covers/.
        """
        if not cover_info:
            return None

        url = str(cover_info)

        settings = get_settings()
        covers_dir = os.path.join(settings.DATA_DIR, "covers")
        os.makedirs(covers_dir, exist_ok=True)

        ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        save_name = f"mangabaka_{provider_id}.{ext}"
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
