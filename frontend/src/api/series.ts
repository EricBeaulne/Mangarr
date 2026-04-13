import { api } from './client';
import type { Series, Volume, Chapter } from '../types';

export interface OrganizeProposal {
  file_id: number;
  series_id: number;
  source: string;
  destination: string;
  would_conflict: boolean;
  moved?: boolean;
  error?: string | null;
  note?: string | null;
}

export interface SeriesListParams {
  status?: string;
  sort?: string;
}

export interface AddSeriesPayload {
  mangadex_id: string;
  root_folder_id: number;
  monitor_status: 'all' | 'future' | 'none';
}

export interface UpdateSeriesPayload {
  monitor_status?: 'all' | 'future' | 'none';
  root_folder_id?: number;
}

export interface SeriesWithVolumes extends Series {
  volumes: Volume[];
  chapters: Chapter[];
}

interface SeriesListResponse {
  items: Series[];
  total: number;
}

export const seriesApi = {
  list: async (params?: SeriesListParams): Promise<Series[]> => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.sort) query.set('sort', params.sort);
    const qs = query.toString();
    const response = await api.get<Series[] | SeriesListResponse>(`/series${qs ? `?${qs}` : ''}`);
    return Array.isArray(response) ? response : response.items;
  },

  get: (id: number): Promise<SeriesWithVolumes> =>
    api.get<SeriesWithVolumes>(`/series/${id}`),

  add: (payload: AddSeriesPayload): Promise<Series> =>
    api.post<Series>('/series', payload),

  update: (id: number, payload: UpdateSeriesPayload): Promise<Series> =>
    api.put<Series>(`/series/${id}`, payload),

  delete: (id: number): Promise<void> =>
    api.delete<void>(`/series/${id}`),

  refreshMetadata: (id: number): Promise<Series> =>
    api.post<Series>(`/series/${id}/refresh`),

  previewOrganize: (id: number): Promise<OrganizeProposal[]> =>
    api.post<OrganizeProposal[]>('/organizer/preview', { series_id: id }),

  organizeFiles: (id: number): Promise<OrganizeProposal[]> =>
    api.post<OrganizeProposal[]>(`/organizer/organize/${id}`),

  getChapters: (id: number): Promise<Chapter[]> =>
    api.get<Chapter[]>(`/series/${id}/chapters`),
};
