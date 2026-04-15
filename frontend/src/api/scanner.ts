import { api } from './client';
import type { ImportedFile, ScanStatus } from '../types';

export interface ScanOptions {
  folder_id?: number;
  force?: boolean;
}

export interface MatchFilePayload {
  imported_file_id: number;
  chapter_id?: number;
  series_id?: number;
}

export const scannerApi = {
  getStatus: (): Promise<ScanStatus> =>
    api.get<ScanStatus>('/scanner/status'),

  startScan: (options?: ScanOptions): Promise<ScanStatus> =>
    api.post<ScanStatus>('/scanner/scan', options),

  cancelScan: (): Promise<{ message: string }> =>
    api.post<{ message: string }>('/scanner/cancel'),

  getUnmatchedFiles: (): Promise<ImportedFile[]> =>
    api.get<ImportedFile[]>('/scanner/unmatched'),

  matchFile: (payload: MatchFilePayload): Promise<ImportedFile> =>
    api.post<ImportedFile>('/scanner/match', payload),

  matchBulk: (payload: BulkMatchPayload): Promise<BulkMatchResponse> =>
    api.post<BulkMatchResponse>('/scanner/match-bulk', payload),
};

export interface BulkMatchPayload {
  file_ids: number[];
  series_id: number;
}

export interface BulkMatchResponse {
  matched: number;
  failed: number;
  errors: string[];
}
