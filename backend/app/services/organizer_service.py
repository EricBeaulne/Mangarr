import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.imported_file import ImportedFile
from app.models.chapter import Chapter
from app.models.series import Series
from app.utils.naming import (
    build_file_name,
    select_file_template,
    build_series_folder_name,
)
from app.utils.file_helpers import safe_move
from app.config import get_settings


def _build_target_path(
    imported: ImportedFile,
    series: Series,
    chapter: Optional[Chapter] = None,
) -> Optional[str]:
    """
    Compute the target path for an imported file.
    Returns full destination path string, or None if series has no root folder.
    """
    settings = get_settings()

    if not series.root_folder or not series.root_folder.path:
        return None

    # Determine series folder
    series_folder = series.series_folder
    if not series_folder:
        series_folder = build_series_folder_name(
            template=settings.SERIES_FOLDER_FORMAT,
            title=series.title,
            year=series.year,
        )

    # Pick file naming template
    volume_number = chapter.volume_number if chapter else imported.parsed_volume_number
    template = select_file_template(
        base_template=settings.FILE_FORMAT,
        no_volume_template=settings.FILE_FORMAT_NO_VOLUME,
        volume_number=volume_number,
    )

    chapter_number = chapter.chapter_number if chapter else imported.parsed_chapter_number
    chapter_title = chapter.title if chapter else None

    file_name = build_file_name(
        template=template,
        series_title=series.title,
        extension=imported.extension,
        chapter_number=chapter_number,
        volume_number=volume_number,
        chapter_title=chapter_title,
        year=series.year,
    )

    target_path = os.path.join(
        series.root_folder.path,
        series_folder,
        file_name,
    )
    return target_path


def _normalize_dest(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _path_blocked_by_db(
    db: Session,
    path: str,
    exclude_file_id: int,
    proposals: List[Dict[str, Any]],
) -> bool:
    """
    True if another imported_files row already uses ``path``.

    If that row is in ``proposals`` and is moving away from ``path`` in this
    batch, the path is treated as free (not blocked).
    """
    other = (
        db.query(ImportedFile)
        .filter(ImportedFile.file_path == path, ImportedFile.id != exclude_file_id)
        .first()
    )
    if other is None:
        return False
    for p in proposals:
        if p["file_id"] != other.id:
            continue
        if _normalize_dest(p["source"]) == _normalize_dest(path) and _normalize_dest(
            p["destination"]
        ) != _normalize_dest(path):
            return False
    return True


def _reconcile_would_conflict(db: Session, proposals: List[Dict[str, Any]]) -> None:
    for p in proposals:
        dst, src = p["destination"], p["source"]
        blocked = bool(p.get("would_conflict")) or (
            os.path.exists(dst) and _normalize_dest(dst) != _normalize_dest(src)
        ) or _path_blocked_by_db(db, dst, p["file_id"], proposals)
        p["would_conflict"] = blocked


def _disambiguate_batch_destinations(db: Session, proposals: List[Dict[str, Any]]) -> None:
    """
    Ensure no two proposals share the same destination path (avoids UNIQUE on
    imported_files.file_path when several files map to the same chapter/volume).
    Losers get ``name (2).ext``, ``name (3).ext``, etc.
    """
    for _ in range(len(proposals) + 10):
        by_dest: Dict[str, List[int]] = defaultdict(list)
        for i, p in enumerate(proposals):
            by_dest[_normalize_dest(p["destination"])].append(i)

        changed = False
        for indices in by_dest.values():
            if len(indices) <= 1:
                continue
            indices.sort(
                key=lambda i: (
                    0 if proposals[i]["source"] == proposals[i]["destination"] else 1,
                    proposals[i]["file_id"],
                )
            )
            taken: Set[str] = {_normalize_dest(proposals[indices[0]]["destination"])}
            for i in indices[1:]:
                stem, ext = os.path.splitext(proposals[i]["destination"])
                n = 2
                while n < 5000:
                    candidate = f"{stem} ({n}){ext}"
                    cn = _normalize_dest(candidate)
                    if cn in taken:
                        n += 1
                        continue
                    if os.path.exists(candidate) and candidate != proposals[i]["source"]:
                        n += 1
                        continue
                    if _path_blocked_by_db(db, candidate, proposals[i]["file_id"], proposals):
                        n += 1
                        continue
                    proposals[i]["destination"] = candidate
                    taken.add(cn)
                    changed = True
                    break
                else:
                    proposals[i]["would_conflict"] = True
        if not changed:
            break


def preview_organize(
    db: Session,
    series_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Dry-run: compute proposed renames for all matched/organized files.
    Returns a list of dicts: {source, destination, would_conflict, series_id, file_id}.
    """
    query = db.query(ImportedFile).filter(
        ImportedFile.scan_state.in_(["matched", "organized"])
    )
    if series_id is not None:
        query = query.filter(ImportedFile.series_id == series_id)

    files = query.all()
    proposals = []

    # Pre-load series with eager root_folder
    series_cache: Dict[int, Series] = {}

    for imported in files:
        if not imported.series_id:
            continue

        if imported.series_id not in series_cache:
            s = (
                db.query(Series)
                .filter(Series.id == imported.series_id)
                .first()
            )
            if s:
                series_cache[imported.series_id] = s

        series = series_cache.get(imported.series_id)
        if not series:
            continue

        # Load associated chapter if any
        chapter = None
        if imported.chapter_id:
            chapter = db.query(Chapter).filter(Chapter.id == imported.chapter_id).first()

        target_path = _build_target_path(imported, series, chapter)
        if not target_path:
            continue

        proposals.append(
            {
                "file_id": imported.id,
                "series_id": imported.series_id,
                "source": imported.file_path,
                "destination": target_path,
                "would_conflict": False,
            }
        )

    _reconcile_would_conflict(db, proposals)
    _disambiguate_batch_destinations(db, proposals)
    _reconcile_would_conflict(db, proposals)

    return proposals


def organize_series(
    db: Session,
    series_id: int,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Rename/move files for a single series.
    Returns list of operation results.
    """
    proposals = preview_organize(db, series_id=series_id)
    results = []

    for proposal in proposals:
        result = dict(proposal)
        result["moved"] = False
        result["error"] = None

        if dry_run:
            results.append(result)
            continue

        src = proposal["source"]
        dst = proposal["destination"]

        if src == dst:
            result["moved"] = False
            result["note"] = "already at destination"
            results.append(result)
            continue

        if proposal["would_conflict"]:
            result["error"] = f"Destination already exists: {dst}"
            results.append(result)
            continue

        try:
            safe_move(src, dst)

            # Update DB record
            imported = (
                db.query(ImportedFile).filter(ImportedFile.id == proposal["file_id"]).first()
            )
            if imported:
                imported.file_path = dst
                imported.file_name = os.path.basename(dst)
                imported.scan_state = "organized"
            db.commit()

            result["moved"] = True
        except Exception as exc:
            db.rollback()
            result["error"] = str(exc)

        results.append(result)

    return results


def organize_all(db: Session, dry_run: bool = False) -> List[Dict[str, Any]]:
    """Rename/move files for all series in the library."""
    proposals = preview_organize(db, series_id=None)
    results = []

    for proposal in proposals:
        result = dict(proposal)
        result["moved"] = False
        result["error"] = None

        if dry_run:
            results.append(result)
            continue

        src = proposal["source"]
        dst = proposal["destination"]

        if src == dst:
            result["moved"] = False
            result["note"] = "already at destination"
            results.append(result)
            continue

        if proposal["would_conflict"]:
            result["error"] = f"Destination already exists: {dst}"
            results.append(result)
            continue

        try:
            safe_move(src, dst)

            imported = (
                db.query(ImportedFile).filter(ImportedFile.id == proposal["file_id"]).first()
            )
            if imported:
                imported.file_path = dst
                imported.file_name = os.path.basename(dst)
                imported.scan_state = "organized"

            db.commit()
            result["moved"] = True
        except Exception as exc:
            db.rollback()
            result["error"] = str(exc)

        results.append(result)

    return results
