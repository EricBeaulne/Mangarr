import { api } from './client';
import type { SearchResult } from '../types';

export interface SearchParams {
  q: string;
  provider?: string;
  limit?: number;
  offset?: number;
}

interface MangaSearchResultApi {
  id: string;
  title: string;
  alt_titles: Record<string, string>[] | Record<string, string>;
  description: string | null;
  status: string | null;
  year: number | null;
  content_rating: string | null;
  original_language: string | null;
  tags: string[];
  cover_url: string | null;
  cover_filename: string | null;
  provider?: string;
}

interface MangaSearchResponseApi {
  results: MangaSearchResultApi[];
  total: number;
  limit: number;
  offset: number;
}

function normalizeAltTitles(alt: MangaSearchResultApi['alt_titles']): Record<string, string> {
  if (Array.isArray(alt)) {
    const merged: Record<string, string> = {};
    for (const entry of alt) {
      if (entry && typeof entry === 'object') {
        Object.assign(merged, entry);
      }
    }
    return merged;
  }
  return alt ?? {};
}

function mapMangaSearchResult(m: MangaSearchResultApi): SearchResult {
  return {
    mangadex_id: m.id,
    title: m.title,
    alt_titles: normalizeAltTitles(m.alt_titles),
    description: m.description,
    status: m.status as SearchResult['status'],
    year: m.year,
    content_rating: m.content_rating,
    cover_url: m.cover_url,
    cover_filename: m.cover_filename,
    tags: m.tags ?? [],
    metadata_provider: m.provider,
  };
}

export const searchApi = {
  searchManga: async (params: SearchParams): Promise<SearchResult[]> => {
    const query = new URLSearchParams();
    query.set('q', params.q);
    query.set('provider', params.provider ?? 'mangadex');
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    if (params.offset !== undefined) query.set('offset', String(params.offset));
    const response = await api.get<MangaSearchResponseApi | SearchResult[]>(
      `/search/manga?${query.toString()}`,
    );
    if (Array.isArray(response)) {
      return response;
    }
    return (response.results ?? []).map(mapMangaSearchResult);
  },

  getMangaById: async (mangaId: string, provider: string = 'mangadex'): Promise<SearchResult> => {
    const m = await api.get<MangaSearchResultApi>(`/search/manga/${mangaId}?provider=${provider}`);
    return mapMangaSearchResult(m);
  },
};
