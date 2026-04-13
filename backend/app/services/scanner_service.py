import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.imported_file import ImportedFile
from app.models.root_folder import RootFolder
from app.models.series import Series
from app.utils.file_helpers import MANGA_EXTENSIONS, get_file_size

try:
    from rapidfuzz import fuzz, process as rfuzz_process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

# ---------------------------------------------------------------------------
# Filename parsing patterns (in priority order)
# ---------------------------------------------------------------------------

# Strips parenthesized/bracketed noise groups: (2022), [Digital], (1r0n), etc.
_NOISE_RE = re.compile(r'\s*[\(\[][^\)\]]*[\)\]]')

def _strip_noise(s: str) -> str:
    return _NOISE_RE.sub('', s).strip()

_PATTERNS = [
    # ── Dash-separated ────────────────────────────────────────────────────────
    # "Series - Vol.01 Ch.001"
    re.compile(
        r"(?P<series>.+?)\s*[-–]\s*[Vv]ol\.?\s*(?P<vol>[\d.]+)\s*[Cc]h\.?\s*(?P<ch>[\d.]+)",
        re.IGNORECASE,
    ),
    # "Series - Ch.001"
    re.compile(
        r"(?P<series>.+?)\s*[-–]\s*[Cc]h(?:apter)?\.?\s*(?P<ch>[\d.]+)",
        re.IGNORECASE,
    ),
    # "Series - Vol.01"
    re.compile(
        r"(?P<series>.+?)\s*[-–]\s*[Vv]ol(?:ume)?\.?\s*(?P<vol>[\d.]+)",
        re.IGNORECASE,
    ),

    # ── No-dash: digital/scene release format ─────────────────────────────────
    # "Series v01c001" or "Series v01 c001" (vol + chapter, no dash)
    re.compile(
        r"(?P<series>.+?)\s+[Vv](?:ol(?:ume)?\.?)?\s*(?P<vol>\d+(?:\.\d+)?)\s*[Cc](?:h(?:apter)?\.?)?\s*(?P<ch>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    # "Series v01 (Year) (Quality) (Group)" — most common digital format
    re.compile(
        r"(?P<series>.+?)\s+[Vv](?:ol(?:ume)?\.?)?\s*(?P<vol>\d+(?:\.\d+)?)(?=\s|$|[\(\[])",
        re.IGNORECASE,
    ),
    # "Series c001 (noise)" or "Series ch001"
    re.compile(
        r"(?P<series>.+?)\s+[Cc](?:h(?:apter)?\.?)?\s*(?P<ch>\d+(?:\.\d+)?)(?=\s|$|[\(\[])",
        re.IGNORECASE,
    ),

    # ── Fallback: bare number at end ──────────────────────────────────────────
    re.compile(r"(?P<series>.+?)\s+(?P<ch>[\d.]+)$"),
]

FUZZY_THRESHOLD = 80


# ---------------------------------------------------------------------------
# Folder / path helpers
# ---------------------------------------------------------------------------

def _get_series_folder_name(file_path: Path, root_folder_path: Path) -> Optional[str]:
    """
    Return the first subdirectory under root_folder as the series folder name.

    /manga/Chainsaw Man/Chainsaw Man v01 (2022).cbz  →  "Chainsaw Man"
    /manga/file.cbz                                  →  None (directly in root)
    """
    try:
        relative = file_path.relative_to(root_folder_path)
        parts = relative.parts
        if len(parts) >= 2:          # at least one subdir + filename
            return parts[0]
    except ValueError:
        pass
    return None


# ---------------------------------------------------------------------------
# Scan job state
# ---------------------------------------------------------------------------
@dataclass
class ScanJob:
    status: str = "idle"  # idle | running | completed | error
    total_files: int = 0
    processed_files: int = 0
    matched: int = 0
    unmatched: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    cancel_requested: bool = False
    # Auto-add phase
    auto_add_status: str = "idle"   # idle | running | complete | error
    auto_add_total: int = 0
    auto_add_done: int = 0
    auto_added: int = 0


# Module-level singleton
_current_job: ScanJob = ScanJob()


def get_scan_job() -> ScanJob:
    return _current_job


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def parse_filename(stem: str) -> dict:
    """
    Try each pattern in priority order against both the raw stem and a
    noise-stripped version (removes groups like (2022), [Digital], (1r0n)).
    Returns dict with keys: series, chapter, volume (all may be None).
    """
    cleaned = _strip_noise(stem)

    for pattern in _PATTERNS:
        # Try raw first, then noise-stripped
        m = pattern.search(stem) or (pattern.search(cleaned) if cleaned != stem else None)
        if m:
            groups = m.groupdict()
            series = (groups.get("series") or "").strip() or None
            # Strip any trailing noise that crept into the series capture group
            if series:
                series = _strip_noise(series).strip() or series
            return {
                "series": series,
                "chapter": groups.get("ch") or None,
                "volume": groups.get("vol") or None,
            }
    return {"series": None, "chapter": None, "volume": None}


def _collect_alt_titles(series: Series) -> List[str]:
    """Return all known titles for a series (title + alt_titles)."""
    titles = [series.title]
    if series.alt_titles_json:
        try:
            alt_list = json.loads(series.alt_titles_json)
            for alt_dict in alt_list:
                if isinstance(alt_dict, dict):
                    titles.extend(alt_dict.values())
                elif isinstance(alt_dict, str):
                    titles.append(alt_dict)
        except (json.JSONDecodeError, TypeError):
            pass
    return [t for t in titles if t]


def fuzzy_match_series(
    parsed_title: str,
    all_series: List[Series],
    folder_hint: Optional[str] = None,
) -> Optional[Series]:
    """
    Find the best-matching Series using rapidfuzz.

    folder_hint (the immediate subdirectory under the root folder) is checked
    first and given a bonus — it is far more reliable than a parsed filename.
    Returns the Series if score >= FUZZY_THRESHOLD, else None.
    """
    candidates = [t for t in [folder_hint, parsed_title] if t]
    if not candidates or not all_series:
        return None

    if not RAPIDFUZZ_AVAILABLE:
        for candidate in candidates:
            lower = candidate.lower()
            for s in all_series:
                for title in _collect_alt_titles(s):
                    if title.lower() == lower:
                        return s
        return None

    best_series = None
    best_score = 0

    for series in all_series:
        for title in _collect_alt_titles(series):
            for candidate in candidates:
                score = fuzz.token_set_ratio(candidate, title)
                # Give folder hint a small bonus — it's more authoritative
                if candidate == folder_hint:
                    score = min(100, score + 5)
                if score > best_score:
                    best_score = score
                    best_series = series

    return best_series if best_score >= FUZZY_THRESHOLD else None


def _try_link_chapters(
    db: Session,
    imported: "ImportedFile",
    series: Series,
    parsed: dict,
) -> None:
    """
    After matching a file to a series, try to set Chapter.is_downloaded.

    - Volume + chapter number  → link exact chapter
    - Chapter number only      → link exact chapter
    - Volume number only       → mark ALL chapters in that volume downloaded
      (a volume CBZ contains every chapter in the volume)
    """
    from app.models.chapter import Chapter
    from app.models.volume import Volume

    ch_num = parsed.get("chapter")
    vol_num = parsed.get("volume")

    if ch_num:
        chapter = (
            db.query(Chapter)
            .filter(Chapter.series_id == series.id, Chapter.chapter_number == ch_num)
            .first()
        )
        if chapter:
            imported.chapter_id = chapter.id
            chapter.is_downloaded = True
            chapter.imported_file_id = imported.id

    elif vol_num:
        # Try matching via Volume record first
        volume = (
            db.query(Volume)
            .filter(Volume.series_id == series.id, Volume.volume_number == vol_num)
            .first()
        )
        if volume:
            chapters = db.query(Chapter).filter(Chapter.volume_id == volume.id).all()
        else:
            # Fallback: match on chapter.volume_number string
            chapters = (
                db.query(Chapter)
                .filter(Chapter.series_id == series.id, Chapter.volume_number == vol_num)
                .all()
            )
        for ch in chapters:
            ch.is_downloaded = True


# ---------------------------------------------------------------------------
# Core scan logic (runs in a thread via run_in_executor)
# ---------------------------------------------------------------------------
def _scan_root_folder(db: Session, root_folder: RootFolder, job: ScanJob) -> None:
    """Walk one root folder and upsert ImportedFile records."""
    base_path = Path(root_folder.path)
    if not base_path.exists():
        return

    try:
        from app.config import get_settings
        extensions = set(get_settings().MANGA_EXTENSIONS)
    except Exception:
        extensions = MANGA_EXTENSIONS

    all_series = db.query(Series).all()

    for file_path in base_path.rglob("*"):
        if job.cancel_requested:
            return
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in extensions:
            continue

        job.total_files += 1
        abs_path = str(file_path.resolve())
        stem = file_path.stem
        ext = file_path.suffix.lower()

        parsed = parse_filename(stem)

        # The folder name immediately under the root is the most reliable series hint.
        # e.g. /manga/Chainsaw Man/Chainsaw Man v01 (2022).cbz  →  "Chainsaw Man"
        raw_folder_hint = _get_series_folder_name(file_path, base_path)
        folder_hint = _strip_noise(raw_folder_hint) if raw_folder_hint else None

        # Store the better of folder_hint / parsed series as the display title
        display_title = folder_hint or parsed.get("series")

        # ── Already tracked ──────────────────────────────────────────────────
        existing = db.query(ImportedFile).filter(ImportedFile.file_path == abs_path).first()
        if existing:
            existing.last_seen_at = datetime.now(timezone.utc)
            existing.file_size = get_file_size(file_path)

            if existing.scan_state in ("organized", "ignored", "matched"):
                job.matched += 1
            elif existing.scan_state == "unmatched":
                # Re-attempt matching now that more series may be in the library
                matched_series = fuzzy_match_series(
                    parsed.get("series") or "", all_series, folder_hint=folder_hint
                )
                if matched_series:
                    existing.series_id = matched_series.id
                    existing.scan_state = "matched"
                    existing.parsed_series_title = display_title
                    existing.parsed_chapter_number = parsed.get("chapter")
                    existing.parsed_volume_number = parsed.get("volume")
                    _try_link_chapters(db, existing, matched_series, parsed)
                    job.matched += 1
                else:
                    # Update display title even if unmatched
                    if display_title:
                        existing.parsed_series_title = display_title
                    job.unmatched += 1
            else:
                job.unmatched += 1

            job.processed_files += 1
            continue

        # ── New file ─────────────────────────────────────────────────────────
        matched_series = fuzzy_match_series(
            parsed.get("series") or "", all_series, folder_hint=folder_hint
        )
        scan_state = "matched" if matched_series else "unmatched"

        imported = ImportedFile(
            series_id=matched_series.id if matched_series else None,
            file_path=abs_path,
            file_name=file_path.name,
            file_size=get_file_size(file_path),
            extension=ext,
            parsed_series_title=display_title,
            parsed_chapter_number=parsed.get("chapter"),
            parsed_volume_number=parsed.get("volume"),
            scan_state=scan_state,
        )
        db.add(imported)
        db.flush()  # get imported.id for chapter linking

        if matched_series:
            _try_link_chapters(db, imported, matched_series, parsed)
            job.matched += 1
        else:
            job.unmatched += 1

        job.processed_files += 1

    db.commit()


def _run_full_scan(root_folder_id: Optional[int] = None) -> None:
    """
    Synchronous scan function that runs in an executor thread.
    """
    global _current_job

    _current_job.status = "running"
    _current_job.started_at = datetime.now(timezone.utc)
    _current_job.total_files = 0
    _current_job.processed_files = 0
    _current_job.matched = 0
    _current_job.unmatched = 0
    _current_job.error = None

    db: Session = SessionLocal()
    try:
        if root_folder_id is not None:
            folders = db.query(RootFolder).filter(RootFolder.id == root_folder_id).all()
        else:
            folders = db.query(RootFolder).all()

        for folder in folders:
            _scan_root_folder(db, folder, _current_job)
            if _current_job.cancel_requested:
                break

        if _current_job.cancel_requested:
            _current_job.status = "cancelled"
        else:
            _current_job.status = "completed"
    except Exception as exc:
        _current_job.status = "error"
        _current_job.error = str(exc)
    finally:
        _current_job.finished_at = datetime.now(timezone.utc)
        db.close()


AUTO_ADD_CONFIDENCE = 88   # minimum rapidfuzz score to auto-add a series
AUTO_ADD_CONCURRENCY = 3  # max parallel MangaDex calls during auto-add


async def _auto_add_unmatched_series(root_folder_id: Optional[int] = None) -> None:
    """
    Phase 2 of a scan: for every unique folder name that is still unmatched,
    search MangaDex and auto-add any high-confidence hit.
    """
    global _current_job
    from app.models.root_folder import RootFolder
    from app.services import series_service

    db: Session = SessionLocal()
    try:
        # Collect unique (parsed_series_title, root_folder_id) pairs from unmatched files
        unmatched_files = (
            db.query(ImportedFile)
            .filter(ImportedFile.scan_state == "unmatched",
                    ImportedFile.parsed_series_title.isnot(None))
            .all()
        )
        if not unmatched_files:
            _current_job.auto_add_status = "complete"
            return

        # Determine which root folder each file lives under
        root_folders = db.query(RootFolder).all()

        def _root_for_file(fp: str) -> Optional[int]:
            p = Path(fp)
            for rf in root_folders:
                try:
                    p.relative_to(rf.path)
                    return rf.id
                except ValueError:
                    pass
            # Fallback: first root folder
            return root_folders[0].id if root_folders else None

        # Build {folder_title: root_folder_id} — one entry per unique title
        pending: dict[str, int] = {}
        for f in unmatched_files:
            title = f.parsed_series_title
            if title and title not in pending:
                rfid = _root_for_file(f.file_path)
                if rfid:
                    pending[title] = rfid

        # Skip titles that are already in the library (any title match)
        existing_series = db.query(Series).all()
        existing_titles = set()
        for s in existing_series:
            existing_titles.add(s.title.lower())
            if s.alt_titles_json:
                try:
                    import json
                    for a in json.loads(s.alt_titles_json):
                        if isinstance(a, dict):
                            existing_titles.update(v.lower() for v in a.values())
                except Exception:
                    pass

        # Remove titles already covered
        pending = {
            t: rid for t, rid in pending.items()
            if t.lower() not in existing_titles
        }

        _current_job.auto_add_status = "running"
        _current_job.auto_add_total = len(pending)
        _current_job.auto_add_done = 0
        _current_job.auto_added = 0

        sem = asyncio.Semaphore(AUTO_ADD_CONCURRENCY)

        async def _try_add(folder_title: str, rfid: int) -> None:
            async with sem:
                if _current_job.cancel_requested:
                    return
                try:
                    from app.services.metadata_service import search_manga
                    results, _ = await search_manga(folder_title, limit=5)
                    if not results:
                        return

                    # Score each result against the folder title
                    best_result = None
                    best_score = 0
                    for r in results:
                        candidates = [r["title"]]
                        if r.get("alt_titles_json"):
                            try:
                                import json
                                for a in json.loads(r["alt_titles_json"]):
                                    if isinstance(a, dict):
                                        candidates.extend(a.values())
                            except Exception:
                                pass
                        for c in candidates:
                            if RAPIDFUZZ_AVAILABLE:
                                s = fuzz.token_set_ratio(folder_title, c)
                            else:
                                s = 100 if folder_title.lower() == c.lower() else 0
                            if s > best_score:
                                best_score = s
                                best_result = r

                    if best_score < AUTO_ADD_CONFIDENCE or not best_result:
                        return

                    # Check not already in library (may have been added in parallel)
                    fresh_db: Session = SessionLocal()
                    try:
                        already = fresh_db.query(Series).filter(
                            Series.mangadex_id == best_result["id"]
                        ).first()
                        if already:
                            return
                        await series_service.add_series(
                            fresh_db,
                            mangadex_id=best_result["id"],
                            root_folder_id=rfid,
                            monitor_status="all",
                        )
                        _current_job.auto_added += 1
                    finally:
                        fresh_db.close()

                except Exception:
                    pass
                finally:
                    _current_job.auto_add_done += 1

        await asyncio.gather(*[_try_add(t, rid) for t, rid in pending.items()])
        _current_job.auto_add_status = "complete"

    except Exception as exc:
        _current_job.auto_add_status = "error"
        _current_job.error = (_current_job.error or "") + f" | auto-add: {exc}"
    finally:
        db.close()


async def trigger_scan(root_folder_id: Optional[int] = None) -> ScanJob:
    """
    Start a scan in a background thread, then auto-add unmatched series.
    Returns the current ScanJob immediately (runs in background).
    """
    global _current_job

    if _current_job.status == "running":
        return _current_job

    _current_job = ScanJob()

    async def _run_all():
        # Phase 1: sync file scan (in thread so it doesn't block the event loop)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _run_full_scan(root_folder_id))
        # Phase 2: async auto-add from MangaDex
        await _auto_add_unmatched_series(root_folder_id)

    asyncio.create_task(_run_all())
    return _current_job


def manual_match(db: Session, imported_file_id: int, chapter_id: int) -> ImportedFile:
    """Manually match an ImportedFile to a Chapter."""
    from app.models.chapter import Chapter

    imported = db.query(ImportedFile).filter(ImportedFile.id == imported_file_id).first()
    if not imported:
        raise ValueError(f"ImportedFile {imported_file_id} not found")

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise ValueError(f"Chapter {chapter_id} not found")

    imported.chapter_id = chapter_id
    imported.series_id = chapter.series_id
    imported.scan_state = "matched"

    chapter.is_downloaded = True
    chapter.imported_file_id = imported_file_id

    db.commit()
    db.refresh(imported)
    return imported


def manual_assign_series(db: Session, imported_file_id: int, series_id: int) -> ImportedFile:
    """Manually classify an ImportedFile to a Series without chapter linkage."""
    imported = db.query(ImportedFile).filter(ImportedFile.id == imported_file_id).first()
    if not imported:
        raise ValueError(f"ImportedFile {imported_file_id} not found")

    series = db.query(Series).filter(Series.id == series_id).first()
    if not series:
        raise ValueError(f"Series {series_id} not found")

    imported.series_id = series_id
    imported.scan_state = "matched"

    db.commit()
    db.refresh(imported)
    return imported


def cancel_scan() -> bool:
    """Request cancellation of the current scan job."""
    if _current_job.status != "running":
        return False
    _current_job.cancel_requested = True
    return True


def rematch_for_series(db: Session, series: Series) -> int:
    """
    After a series is added/refreshed, scan all existing unmatched ImportedFiles
    and retroactively link any that belong to this series.

    Uses both the file's stored parsed_series_title and the parent folder name
    (extracted from file_path) as match candidates.

    Returns the number of files newly matched.
    """
    unmatched = (
        db.query(ImportedFile)
        .filter(ImportedFile.scan_state == "unmatched")
        .all()
    )
    if not unmatched:
        return 0

    newly_matched = 0
    all_titles = _collect_alt_titles(series)

    def _best_score(candidate: Optional[str]) -> int:
        if not candidate:
            return 0
        if not RAPIDFUZZ_AVAILABLE:
            return 100 if any(t.lower() == candidate.lower() for t in all_titles) else 0
        return max((fuzz.token_set_ratio(candidate, t) for t in all_titles), default=0)

    for imported in unmatched:
        # Try the stored parsed title
        score_title = _best_score(imported.parsed_series_title)

        # Try the immediate parent folder name (stripped of noise)
        folder_hint: Optional[str] = None
        try:
            fp = Path(imported.file_path)
            folder_hint = _strip_noise(fp.parent.name) or None
        except Exception:
            pass
        score_folder = _best_score(folder_hint)

        best = max(score_title, score_folder)
        if best < FUZZY_THRESHOLD:
            continue

        # Re-parse file to get volume/chapter numbers if not stored
        parsed = {
            "series": imported.parsed_series_title,
            "chapter": imported.parsed_chapter_number,
            "volume": imported.parsed_volume_number,
        }
        if not parsed["chapter"] and not parsed["volume"]:
            try:
                reparsed = parse_filename(Path(imported.file_path).stem)
                parsed["chapter"] = reparsed.get("chapter")
                parsed["volume"] = reparsed.get("volume")
                if not imported.parsed_series_title and reparsed.get("series"):
                    parsed["series"] = reparsed["series"]
            except Exception:
                pass

        # Update stored display title to whichever candidate scored better
        if score_folder >= score_title and folder_hint:
            imported.parsed_series_title = folder_hint
        if parsed.get("chapter"):
            imported.parsed_chapter_number = parsed["chapter"]
        if parsed.get("volume"):
            imported.parsed_volume_number = parsed["volume"]

        imported.series_id = series.id
        imported.scan_state = "matched"
        _try_link_chapters(db, imported, series, parsed)
        newly_matched += 1

    if newly_matched:
        db.commit()

    return newly_matched
