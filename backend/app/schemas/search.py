from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MangaSearchResult(BaseModel):
    """Represents a manga result from a metadata provider search."""
    id: str
    title: str
    alt_titles: List[Dict[str, str]] = []
    description: Optional[str] = None
    status: Optional[str] = None
    year: Optional[int] = None
    content_rating: Optional[str] = None
    original_language: Optional[str] = None
    tags: List[str] = []
    cover_url: Optional[str] = None
    cover_filename: Optional[str] = None
    in_library: bool = False
    provider: str = "mangadex"


class MangaSearchResponse(BaseModel):
    results: List[MangaSearchResult]
    total: int
    limit: int
    offset: int


class ChapterSearchResult(BaseModel):
    id: str
    chapter_number: Optional[str] = None
    volume_number: Optional[str] = None
    title: Optional[str] = None
    language: str
    pages: Optional[int] = None
    publish_at: Optional[str] = None
