import re
from typing import Optional


def sanitize_path_segment(s: str) -> str:
    """
    Strip characters not allowed in filesystem paths, collapse spaces,
    trim trailing dots/spaces, and cap at 200 characters.
    """
    # Strip forbidden characters: \ / : * ? " < > |
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    # Collapse multiple spaces into one
    s = re.sub(r" {2,}", " ", s)
    # Strip leading/trailing whitespace and trailing dots
    s = s.strip().rstrip(".")
    # Cap at 200 characters
    s = s[:200]
    return s


def _pad_number(value: Optional[str], width: int) -> str:
    """Zero-pad a numeric string. If it contains a decimal, pad only the integer part."""
    if value is None:
        return "0" * width
    # Handle decimal values like "1.5"
    if "." in value:
        parts = value.split(".", 1)
        return parts[0].zfill(width) + "." + parts[1]
    # Handle plain integers
    try:
        return str(int(value)).zfill(width)
    except ValueError:
        return value.zfill(width)


def build_series_folder_name(
    template: str,
    title: str,
    year: Optional[int] = None,
) -> str:
    """
    Render the series folder name from a template.
    Available tokens: {Series Title}, {Series TitleYear}, {Year}
    """
    sanitized_title = sanitize_path_segment(title)
    year_str = str(year) if year else ""

    if year:
        title_year = f"{sanitized_title} ({year_str})"
    else:
        title_year = sanitized_title

    result = template
    result = result.replace("{Series Title}", sanitized_title)
    result = result.replace("{Series TitleYear}", title_year)
    result = result.replace("{Year}", year_str)

    return sanitize_path_segment(result)


def build_file_name(
    template: str,
    series_title: str,
    extension: str,
    chapter_number: Optional[str] = None,
    volume_number: Optional[str] = None,
    chapter_title: Optional[str] = None,
    language: Optional[str] = None,
    year: Optional[int] = None,
) -> str:
    """
    Render the chapter file name from a template.

    Available tokens:
      {Series Title}      - sanitized series title
      {Series TitleYear}  - title + (year) if year set
      {Volume}            - zero-padded 2 digits
      {Chapter}           - zero-padded 3 digits (integer only)
      {Chapter Decimal}   - chapter with decimal (e.g. 001.5)
      {Chapter Title}     - chapter title if present
      {Language}          - ISO 639-1
      {Extension}         - file extension (including the dot)
    """
    sanitized_title = sanitize_path_segment(series_title)
    year_str = str(year) if year else ""

    if year:
        title_year = f"{sanitized_title} ({year_str})"
    else:
        title_year = sanitized_title

    vol_padded = _pad_number(volume_number, 2)
    has_chapter = chapter_number is not None and str(chapter_number).strip() != ""
    ch_padded = _pad_number(chapter_number, 3) if has_chapter else "???"

    # Chapter decimal: keep decimals if present, else use same as padded
    if has_chapter and "." in str(chapter_number):
        ch_decimal = _pad_number(chapter_number, 3)
    else:
        ch_decimal = ch_padded

    # Sanitize chapter title for use in filename
    safe_chapter_title = sanitize_path_segment(chapter_title) if chapter_title else ""

    # Ensure extension starts with a dot
    if extension and not extension.startswith("."):
        extension = "." + extension

    result = template
    result = result.replace("{Series Title}", sanitized_title)
    result = result.replace("{Series TitleYear}", title_year)
    result = result.replace("{Volume}", vol_padded)
    result = result.replace("{Chapter Decimal}", ch_decimal)
    result = result.replace("{Chapter}", ch_padded)
    result = result.replace("{Chapter Title}", safe_chapter_title)
    result = result.replace("{Language}", language or "")
    result = result.replace("{Extension}", extension or "")

    # Clean up double spaces or trailing dashes/spaces that may result from empty tokens
    result = re.sub(r"\s+-\s+-\s+", " - ", result)
    result = re.sub(r"\s+-\s*$", "", result)
    result = re.sub(r"^\s*-\s+", "", result)
    result = re.sub(r" {2,}", " ", result)
    result = result.strip()

    # Empty chapter title often leaves " - .cbz" before the extension
    if extension:
        ext_pat = re.escape(extension)
        result = re.sub(rf"\s+-\s+{ext_pat}$", extension, result)

    return result


def select_file_template(
    base_template: str,
    no_volume_template: str,
    volume_number: Optional[str],
) -> str:
    """Pick the right template based on whether volume info is available."""
    if volume_number:
        return base_template
    return no_volume_template
