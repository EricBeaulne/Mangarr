from app.providers.mangadex import MangaDexProvider
from app.providers.mangabaka import MangaBakaProvider
from app.providers.mangaupdates import MangaUpdatesProvider

PROVIDERS = {
    "mangadex": MangaDexProvider(),
    "mangabaka": MangaBakaProvider(),
    "mangaupdates": MangaUpdatesProvider(),
}

__all__ = ["PROVIDERS", "MangaDexProvider", "MangaBakaProvider", "MangaUpdatesProvider"]
