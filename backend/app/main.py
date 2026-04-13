import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import run_migrations
from app.routers import series, library, search, scanner, organizer, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables and covers directory on startup."""
    config = get_settings()

    # Ensure DATA_DIR exists
    os.makedirs(config.DATA_DIR, exist_ok=True)

    # Ensure covers directory exists
    covers_dir = os.path.join(config.DATA_DIR, "covers")
    os.makedirs(covers_dir, exist_ok=True)

    run_migrations()

    yield
    # Shutdown: nothing to clean up for MVP


def create_app() -> FastAPI:
    config = get_settings()

    app = FastAPI(
        title="Mangarr",
        description="Manga library manager — like Sonarr/Radarr for manga.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    api_prefix = "/api/v1"
    app.include_router(search.router, prefix=api_prefix)
    app.include_router(series.router, prefix=api_prefix)
    app.include_router(library.router, prefix=api_prefix)
    app.include_router(scanner.router, prefix=api_prefix)
    app.include_router(organizer.router, prefix=api_prefix)
    app.include_router(settings_router.router, prefix=api_prefix)

    # Static files for cover images
    covers_dir = os.path.join(config.DATA_DIR, "covers")
    os.makedirs(covers_dir, exist_ok=True)
    app.mount("/covers", StaticFiles(directory=covers_dir), name="covers")

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok", "service": "Mangarr"}

    # Serve built frontend when running unified container image.
    web_root = Path(__file__).resolve().parent / "web"
    if web_root.exists():
        app.mount("/", StaticFiles(directory=web_root, html=True), name="web")

    return app


app = create_app()
