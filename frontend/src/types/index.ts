export interface RootFolder {
  id: number;
  path: string;
  label: string;
  free_space: number | null;
}

export interface Series {
  id: number;
  metadata_provider: string;
  metadata_id: string;
  mangadex_id: string | null;
  title: string;
  alt_titles_json: string | null;
  description: string | null;
  status: 'ongoing' | 'completed' | 'hiatus' | 'cancelled' | null;
  year: number | null;
  content_rating: string | null;
  original_language: string | null;
  tags_json: string | null;
  cover_filename: string | null;
  root_folder_id: number | null;
  series_folder: string | null;
  monitor_status: 'all' | 'future' | 'none';
  metadata_updated_at: string | null;
  created_at: string;
  chapter_count?: number;
  downloaded_count?: number;
  missing_count?: number;
}

export interface Volume {
  id: number;
  series_id: number;
  volume_number: string | null;
  cover_filename: string | null;
  chapters: Chapter[];
}

export interface Chapter {
  id: number;
  series_id: number;
  volume_id: number | null;
  mangadex_id: string | null;
  chapter_number: string | null;
  volume_number: string | null;
  title: string | null;
  language: string;
  pages: number | null;
  publish_at: string | null;
  is_downloaded: boolean;
  imported_file_id: number | null;
}

export interface SearchResult {
  mangadex_id: string;
  title: string;
  alt_titles: Record<string, string>;
  description: string | null;
  status: string | null;
  year: number | null;
  content_rating: string | null;
  /** Direct MangaDex CDN URL (works before local cache download). */
  cover_url: string | null;
  cover_filename: string | null;
  tags: string[];
  metadata_provider?: string;
}

export interface ScanStatus {
  status: 'idle' | 'running' | 'completed' | 'cancelled' | 'error';
  total_files: number;
  processed_files: number;
  matched: number;
  unmatched: number;
  started_at: string | null;
  finished_at?: string | null;
  error: string | null;
}

export interface ImportedFile {
  id: number;
  series_id: number | null;
  chapter_id: number | null;
  file_path: string;
  file_name: string;
  file_size: number;
  extension: string;
  parsed_series_title: string | null;
  parsed_chapter_number: string | null;
  parsed_volume_number: string | null;
  scan_state: string;
  imported_at: string;
}

export interface AppSettings {
  default_language: string;
  series_folder_format: string;
  file_format: string;
  file_format_no_volume: string;
  manga_extensions: string[];
}

export interface PathValidationResult {
  valid: boolean;
  exists: boolean;
  writable: boolean;
  free_space: number | null;
  error: string | null;
}

export interface MissingChapter {
  id: number;
  chapter_number: string | null;
  volume_number: string | null;
  title: string | null;
  publish_at: string | null;
}

export interface WantedSeriesEntry {
  series_id: number;
  title: string;
  cover_filename: string | null;
  metadata_provider: string;
  metadata_id: string;
  monitor_status: string;
  total_chapters: number;
  missing_count: number;
  missing: MissingChapter[];
}
