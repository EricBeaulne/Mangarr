import { useEffect, useMemo, useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Play,
  StopCircle,
  Search,
  CheckCircle2,
  XCircle,
  Clock,
  FileQuestion,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Plus,
} from 'lucide-react';
import { scannerApi } from '../api/scanner';
import { seriesApi } from '../api/series';
import { searchApi } from '../api/search';
import { libraryApi } from '../api/library';
import { TopBar } from '../components/layout/TopBar';
import { PageContainer } from '../components/layout/PageContainer';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { Modal } from '../components/ui/Modal';
import { StatusBadge, ContentRatingBadge } from '../components/ui/Badge';
import { useScanStore } from '../store/scanStore';
import { useNotificationStore } from '../store/notificationStore';
import type { ImportedFile, Series, SearchResult, RootFolder } from '../types';

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB'];
  let val = bytes;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
  return `${val.toFixed(1)} ${units[i]}`;
}

function pickCoverSrc(result: SearchResult): string | null {
  if (result.cover_filename) {
    return `${window.location.origin}/covers/${result.cover_filename}`;
  }
  return result.cover_url;
}

function CoverThumb({ result }: { result: SearchResult }) {
  const coverUrl = pickCoverSrc(result);
  const hue =
    result.title.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;

  if (!coverUrl) {
    return (
      <div
        className="w-full h-full flex items-center justify-center"
        style={{
          background: `linear-gradient(135deg, hsl(${hue},45%,18%) 0%, hsl(${(hue + 40) % 360},40%,12%) 100%)`,
        }}
      >
        <span className="text-xl font-bold text-white/40">
          {result.title.slice(0, 2).toUpperCase()}
        </span>
      </div>
    );
  }

  return (
    <img
      src={coverUrl}
      alt={result.title}
      className="w-full h-full object-cover"
      loading="lazy"
      onError={(e) => {
        const el = e.target as HTMLImageElement;
        if (result.cover_url && el.src !== result.cover_url) {
          el.src = result.cover_url;
          return;
        }
        el.style.display = 'none';
      }}
    />
  );
}

// 3-state checkbox
function TriCheckbox({
  state,
  onClick,
  className = '',
}: {
  state: 'none' | 'some' | 'all';
  onClick: (e: React.MouseEvent) => void;
  className?: string;
}) {
  const checked = state === 'all';
  const indeterminate = state === 'some';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-4 h-4 border rounded flex items-center justify-center transition-colors shrink-0 ${
        checked || indeterminate
          ? 'bg-mangarr-accent border-mangarr-accent'
          : 'border-mangarr-border bg-mangarr-input hover:border-mangarr-muted'
      } ${className}`}
      aria-checked={checked}
    >
      {checked && <Check className="w-3 h-3 text-white" />}
      {indeterminate && <div className="w-2 h-0.5 bg-white rounded-sm" />}
    </button>
  );
}

interface BulkMatchModalProps {
  fileIds: number[];
  allSeries: Series[];
  folders: RootFolder[];
  onClose: () => void;
  onMatched: (count: number, seriesTitle: string) => void;
}

function BulkMatchModal({
  fileIds,
  allSeries,
  folders,
  onClose,
  onMatched,
}: BulkMatchModalProps) {
  const [tab, setTab] = useState<'existing' | 'new'>('existing');
  const addToast = useNotificationStore((s) => s.addToast);

  // ---- Existing tab ----
  const [existingQuery, setExistingQuery] = useState('');
  const [selectedExistingId, setSelectedExistingId] = useState<number | null>(null);

  const filteredSeries = useMemo(() => {
    const q = existingQuery.trim().toLowerCase();
    if (!q) return allSeries;
    return allSeries.filter((s) => s.title.toLowerCase().includes(q));
  }, [allSeries, existingQuery]);

  const { mutate: matchExisting, isPending: isMatchingExisting } = useMutation({
    mutationFn: (seriesId: number) =>
      scannerApi.matchBulk({ file_ids: fileIds, series_id: seriesId }),
    onSuccess: (res, seriesId) => {
      const series = allSeries.find((s) => s.id === seriesId);
      if (res.failed > 0) {
        addToast(
          `Matched ${res.matched} file(s), ${res.failed} failed`,
          'error',
        );
      }
      onMatched(res.matched, series?.title ?? 'series');
    },
    onError: (err) => addToast(`Match failed: ${(err as Error).message}`, 'error'),
  });

  // ---- New tab ----
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [provider, setProvider] = useState<
    'auto' | 'mangadex' | 'mangabaka' | 'mangaupdates'
  >('auto');
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [rootFolderId, setRootFolderId] = useState<number | ''>(folders[0]?.id ?? '');
  const [monitorStatus, setMonitorStatus] = useState<'all' | 'future' | 'none'>('all');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQuery(searchQuery), 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchQuery]);

  useEffect(() => {
    if (rootFolderId === '' && folders.length > 0) {
      setRootFolderId(folders[0].id);
    }
  }, [folders, rootFolderId]);

  const { data: searchResults = [], isLoading: isSearching } = useQuery({
    queryKey: ['scanner-search', debouncedQuery, provider],
    queryFn: () => searchApi.searchManga({ q: debouncedQuery, provider }),
    enabled: tab === 'new' && debouncedQuery.trim().length >= 2,
  });

  const { mutate: addAndMatch, isPending: isAddingAndMatching } = useMutation({
    mutationFn: async () => {
      if (!selectedResult) throw new Error('No series selected');
      if (rootFolderId === '') throw new Error('Root folder required');
      const effectiveProvider =
        provider === 'auto'
          ? (selectedResult.metadata_provider as
              | 'mangadex'
              | 'mangabaka'
              | 'mangaupdates') ?? 'mangadex'
          : provider;
      const series = await seriesApi.add({
        metadata_id: selectedResult.mangadex_id,
        metadata_provider: effectiveProvider,
        root_folder_id: Number(rootFolderId),
        monitor_status: monitorStatus,
      });
      const res = await scannerApi.matchBulk({
        file_ids: fileIds,
        series_id: series.id,
      });
      return { series, res };
    },
    onSuccess: ({ series, res }) => {
      addToast(`Added "${series.title}" and matched ${res.matched} files`, 'success');
      onMatched(res.matched, series.title);
    },
    onError: (err) =>
      addToast(`Add & match failed: ${(err as Error).message}`, 'error'),
  });

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={`Match ${fileIds.length} file${fileIds.length === 1 ? '' : 's'} to Series`}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {tab === 'existing' ? (
            <Button
              loading={isMatchingExisting}
              disabled={selectedExistingId === null}
              onClick={() =>
                selectedExistingId !== null && matchExisting(selectedExistingId)
              }
            >
              Match {fileIds.length} file{fileIds.length === 1 ? '' : 's'}
            </Button>
          ) : (
            <Button
              loading={isAddingAndMatching}
              disabled={!selectedResult || rootFolderId === ''}
              onClick={() => addAndMatch()}
              leftIcon={<Plus className="w-4 h-4" />}
            >
              Add Series & Match {fileIds.length} File{fileIds.length === 1 ? '' : 's'}
            </Button>
          )}
        </>
      }
    >
      {/* Tabs */}
      <div className="flex gap-1 border-b border-mangarr-border mb-4 -mt-2">
        <button
          type="button"
          onClick={() => setTab('existing')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            tab === 'existing'
              ? 'border-mangarr-accent text-mangarr-text'
              : 'border-transparent text-mangarr-muted hover:text-mangarr-text'
          }`}
        >
          Existing Series
        </button>
        <button
          type="button"
          onClick={() => setTab('new')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            tab === 'new'
              ? 'border-mangarr-accent text-mangarr-text'
              : 'border-transparent text-mangarr-muted hover:text-mangarr-text'
          }`}
        >
          Search & Add New
        </button>
      </div>

      {tab === 'existing' ? (
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-mangarr-muted" />
            <input
              type="text"
              value={existingQuery}
              onChange={(e) => setExistingQuery(e.target.value)}
              placeholder="Filter library..."
              className="input-base w-full pl-9 pr-3 py-2 text-sm"
              autoFocus
            />
          </div>

          <div className="max-h-80 overflow-y-auto space-y-1.5">
            {filteredSeries.length === 0 ? (
              <p className="text-mangarr-muted text-sm text-center py-8">
                No matching series in your library.
              </p>
            ) : (
              filteredSeries.map((s) => {
                const selected = selectedExistingId === s.id;
                const coverUrl = s.cover_filename
                  ? `${window.location.origin}/covers/${s.cover_filename}`
                  : null;
                return (
                  <div
                    key={s.id}
                    onClick={() => setSelectedExistingId(s.id)}
                    className={`flex gap-3 p-2 rounded-lg cursor-pointer border transition-all ${
                      selected
                        ? 'border-mangarr-accent bg-mangarr-accent/10'
                        : 'border-mangarr-border bg-mangarr-input/50 hover:border-mangarr-accent/50'
                    }`}
                  >
                    <div
                      className="w-10 shrink-0 rounded overflow-hidden bg-mangarr-input"
                      style={{ aspectRatio: '2/3' }}
                    >
                      {coverUrl && (
                        <img
                          src={coverUrl}
                          alt={s.title}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-mangarr-text text-sm font-medium truncate">
                        {s.title}
                      </p>
                      {s.year && (
                        <p className="text-mangarr-muted text-xs">{s.year}</p>
                      )}
                    </div>
                    {selected && (
                      <Check className="w-4 h-4 text-mangarr-accent self-center" />
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {!selectedResult ? (
            <>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-mangarr-muted" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search for manga..."
                    className="input-base w-full pl-9 pr-3 py-2 text-sm"
                    autoFocus
                  />
                  {isSearching && (
                    <Spinner
                      size="sm"
                      className="absolute right-3 top-1/2 -translate-y-1/2"
                    />
                  )}
                </div>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value as typeof provider)}
                  className="select-base text-sm px-3 py-2 min-w-[130px]"
                >
                  <option value="auto">Auto</option>
                  <option value="mangadex">MangaDex</option>
                  <option value="mangabaka">MangaBaka</option>
                  <option value="mangaupdates">MangaUpdates</option>
                </select>
              </div>

              <div className="max-h-72 overflow-y-auto space-y-1.5">
                {debouncedQuery.trim().length < 2 ? (
                  <p className="text-mangarr-muted text-sm text-center py-8">
                    Enter at least 2 characters to search
                  </p>
                ) : !isSearching && searchResults.length === 0 ? (
                  <p className="text-mangarr-muted text-sm text-center py-8">
                    No results found
                  </p>
                ) : (
                  searchResults.map((r) => (
                    <div
                      key={`${r.metadata_provider ?? provider}-${r.mangadex_id}`}
                      onClick={() => setSelectedResult(r)}
                      className="flex gap-3 p-2 bg-mangarr-input/50 border border-mangarr-border rounded-lg cursor-pointer hover:border-mangarr-accent/50 transition-all"
                    >
                      <div
                        className="w-10 shrink-0 rounded overflow-hidden border border-mangarr-border"
                        style={{ aspectRatio: '2/3' }}
                      >
                        <CoverThumb result={r} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-mangarr-text text-sm font-medium truncate">
                          {r.title}
                        </p>
                        <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                          {r.status && (
                            <StatusBadge status={r.status as never} size="sm" />
                          )}
                          {r.content_rating && (
                            <ContentRatingBadge
                              rating={r.content_rating}
                              size="sm"
                            />
                          )}
                          {r.year && (
                            <span className="text-mangarr-disabled text-xs">
                              {r.year}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <div className="flex gap-3 p-3 bg-mangarr-input/50 border border-mangarr-border rounded-lg">
                <div
                  className="w-14 shrink-0 rounded overflow-hidden border border-mangarr-border"
                  style={{ aspectRatio: '2/3' }}
                >
                  <CoverThumb result={selectedResult} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-mangarr-text text-sm font-semibold">
                    {selectedResult.title}
                  </p>
                  <div className="flex flex-wrap items-center gap-1.5 mt-1">
                    {selectedResult.status && (
                      <StatusBadge
                        status={selectedResult.status as never}
                        size="sm"
                      />
                    )}
                    {selectedResult.year && (
                      <span className="text-mangarr-disabled text-xs">
                        {selectedResult.year}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedResult(null)}
                  className="text-mangarr-muted hover:text-mangarr-text self-start"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-1.5">
                <label className="text-mangarr-text text-sm font-medium block">
                  Root Folder
                </label>
                {folders.length === 0 ? (
                  <p className="text-mangarr-warning text-xs">
                    No root folders configured. Please add one in Settings.
                  </p>
                ) : (
                  <select
                    value={rootFolderId}
                    onChange={(e) => setRootFolderId(Number(e.target.value))}
                    className="select-base w-full text-sm"
                  >
                    {folders.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.label || f.path}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div className="space-y-1.5">
                <label className="text-mangarr-text text-sm font-medium block">
                  Monitor
                </label>
                <select
                  value={monitorStatus}
                  onChange={(e) =>
                    setMonitorStatus(e.target.value as typeof monitorStatus)
                  }
                  className="select-base w-full text-sm"
                >
                  <option value="all">All Chapters</option>
                  <option value="future">Future Only</option>
                  <option value="none">None</option>
                </select>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

export function Scanner() {
  const { status, setStatus } = useScanStore();
  const addToast = useNotificationStore((s) => s.addToast);
  const queryClient = useQueryClient();

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const collapsedInitialized = useRef(false);

  // Poll scan status
  const { data: scanStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['scan-status'],
    queryFn: () => scannerApi.getStatus(),
    refetchInterval: status?.status === 'running' ? 2000 : false,
  });

  useEffect(() => {
    if (scanStatus) setStatus(scanStatus);
  }, [scanStatus, setStatus]);

  const { data: unmatchedFiles = [] } = useQuery({
    queryKey: ['unmatched-files'],
    queryFn: () => scannerApi.getUnmatchedFiles(),
  });

  const { data: allSeries = [] } = useQuery({
    queryKey: ['series'],
    queryFn: () => seriesApi.list(),
  });

  const { data: folders = [] } = useQuery({
    queryKey: ['folders'],
    queryFn: () => libraryApi.getFolders(),
  });

  const { mutate: startScan, isPending: isStarting } = useMutation({
    mutationFn: () => scannerApi.startScan(),
    onSuccess: (s) => {
      setStatus(s);
      addToast('Scan started', 'info');
      refetchStatus();
    },
    onError: (err) => addToast(`Scan failed to start: ${(err as Error).message}`, 'error'),
  });

  const { mutate: cancelScan, isPending: isCancelling } = useMutation({
    mutationFn: () => scannerApi.cancelScan(),
    onSuccess: () => {
      addToast('Scan cancelled', 'info');
      refetchStatus();
    },
    onError: (err) => addToast(`Cancel failed: ${(err as Error).message}`, 'error'),
  });

  // Group unmatched files by parsed_series_title
  const groups = useMemo(() => {
    const map = new Map<string, ImportedFile[]>();
    for (const f of unmatchedFiles) {
      const key = f.parsed_series_title?.trim() || 'Unknown';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(f);
    }
    return Array.from(map.entries())
      .map(([title, files]) => ({ title, files }))
      .sort((a, b) => a.title.localeCompare(b.title));
  }, [unmatchedFiles]);

  // Default collapsed state (run once per "batch" of groups)
  useEffect(() => {
    if (collapsedInitialized.current) return;
    if (groups.length === 0) return;
    collapsedInitialized.current = true;
    if (groups.length > 3) {
      setCollapsedGroups(new Set(groups.map((g) => g.title)));
    }
  }, [groups]);

  // Remove stale selections whenever unmatched list changes
  useEffect(() => {
    setSelectedIds((prev) => {
      const valid = new Set(unmatchedFiles.map((f) => f.id));
      const next = new Set<number>();
      for (const id of prev) if (valid.has(id)) next.add(id);
      return next.size === prev.size ? prev : next;
    });
  }, [unmatchedFiles]);

  const toggleFile = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const groupState = (files: ImportedFile[]): 'none' | 'some' | 'all' => {
    let count = 0;
    for (const f of files) if (selectedIds.has(f.id)) count++;
    if (count === 0) return 'none';
    if (count === files.length) return 'all';
    return 'some';
  };

  const toggleGroup = (files: ImportedFile[]) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const state = groupState(files);
      if (state === 'all') {
        for (const f of files) next.delete(f.id);
      } else {
        for (const f of files) next.add(f.id);
      }
      return next;
    });
  };

  const toggleCollapse = (title: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };

  const handleMatched = (count: number, seriesTitle: string) => {
    addToast(`Matched ${count} file${count === 1 ? '' : 's'} to ${seriesTitle}`, 'success');
    queryClient.invalidateQueries({ queryKey: ['unmatched-files'] });
    queryClient.invalidateQueries({ queryKey: ['series'] });
    setSelectedIds(new Set());
    setBulkModalOpen(false);
  };

  const currentStatus = scanStatus ?? status;
  const isRunning = currentStatus?.status === 'running';
  const progressPct =
    currentStatus && currentStatus.total_files > 0
      ? Math.round((currentStatus.processed_files / currentStatus.total_files) * 100)
      : 0;

  const statusConfig: Record<
    string,
    { icon: React.ReactNode; label: string; color: string }
  > = {
    idle: {
      icon: <Clock className="w-4 h-4" />,
      label: 'Idle',
      color: 'text-mangarr-muted',
    },
    running: {
      icon: <Spinner size="sm" />,
      label: 'Running',
      color: 'text-mangarr-warning',
    },
    completed: {
      icon: <CheckCircle2 className="w-4 h-4" />,
      label: 'Complete',
      color: 'text-mangarr-success',
    },
    cancelled: {
      icon: <StopCircle className="w-4 h-4" />,
      label: 'Cancelled',
      color: 'text-mangarr-muted',
    },
    error: {
      icon: <XCircle className="w-4 h-4" />,
      label: 'Error',
      color: 'text-mangarr-danger',
    },
  };

  const statusInfo = statusConfig[currentStatus?.status ?? 'idle'];

  return (
    <div className="flex flex-col h-full">
      <TopBar title="Scanner" />
      <PageContainer className="max-w-4xl mx-auto w-full space-y-6">
        {/* Scan status card */}
        <div className="bg-mangarr-card border border-mangarr-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-mangarr-text font-semibold text-sm flex items-center gap-2">
              <Search className="w-4 h-4" />
              Scan Status
            </h2>
            <div className="flex gap-2">
              {isRunning ? (
                <Button
                  variant="danger"
                  size="sm"
                  loading={isCancelling}
                  onClick={() => cancelScan()}
                  leftIcon={<StopCircle className="w-4 h-4" />}
                >
                  Cancel
                </Button>
              ) : (
                <Button
                  size="sm"
                  loading={isStarting}
                  onClick={() => startScan()}
                  leftIcon={<Play className="w-4 h-4" />}
                >
                  Scan All
                </Button>
              )}
            </div>
          </div>

          {/* Status row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
            <div className="bg-mangarr-input border border-mangarr-border rounded-lg p-3">
              <p className="text-mangarr-muted text-xs mb-1">Status</p>
              <div className={`flex items-center gap-1.5 text-sm font-medium ${statusInfo.color}`}>
                {statusInfo.icon}
                {statusInfo.label}
              </div>
            </div>
            <div className="bg-mangarr-input border border-mangarr-border rounded-lg p-3">
              <p className="text-mangarr-muted text-xs mb-1">Files Found</p>
              <p className="text-mangarr-text text-sm font-semibold">
                {currentStatus?.total_files ?? 0}
              </p>
            </div>
            <div className="bg-mangarr-input border border-mangarr-border rounded-lg p-3">
              <p className="text-mangarr-muted text-xs mb-1">Matched</p>
              <p className="text-mangarr-success text-sm font-semibold">
                {currentStatus?.matched ?? 0}
              </p>
            </div>
            <div className="bg-mangarr-input border border-mangarr-border rounded-lg p-3">
              <p className="text-mangarr-muted text-xs mb-1">Unmatched</p>
              <p className="text-mangarr-warning text-sm font-semibold">
                {currentStatus?.unmatched ?? 0}
              </p>
            </div>
          </div>

          {/* Progress bar */}
          {isRunning && currentStatus && currentStatus.total_files > 0 && (
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-mangarr-muted">
                <span>
                  {currentStatus.processed_files} / {currentStatus.total_files} files processed
                </span>
                <span>{progressPct}%</span>
              </div>
              <div className="h-2 bg-mangarr-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-mangarr-accent rounded-full transition-all duration-300"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}

          {currentStatus?.started_at && (
            <p className="text-mangarr-disabled text-xs mt-3">
              Started: {formatDate(currentStatus.started_at)}
            </p>
          )}

          {currentStatus?.error && (
            <div className="mt-3 bg-mangarr-danger/10 border border-mangarr-danger/30 rounded-lg p-3">
              <p className="text-mangarr-danger text-xs">{currentStatus.error}</p>
            </div>
          )}
        </div>

        {/* Unmatched files */}
        <div className="bg-mangarr-card border border-mangarr-border rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-mangarr-border flex items-center justify-between">
            <h2 className="text-mangarr-text font-semibold text-sm flex items-center gap-2">
              <FileQuestion className="w-4 h-4" />
              Unmatched Files
              {unmatchedFiles.length > 0 && (
                <span className="bg-mangarr-warning/20 text-mangarr-warning text-xs px-1.5 py-0.5 rounded-full border border-mangarr-warning/30">
                  {unmatchedFiles.length}
                </span>
              )}
            </h2>
          </div>

          {/* Bulk action bar */}
          {selectedIds.size > 0 && (
            <div className="sticky top-0 z-10 bg-mangarr-accent/10 border-b border-mangarr-accent/30 px-5 py-2.5 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm text-mangarr-text">
                <Check className="w-4 h-4 text-mangarr-accent" />
                <span className="font-medium">
                  {selectedIds.size} file{selectedIds.size === 1 ? '' : 's'} selected
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedIds(new Set())}
                  className="text-mangarr-muted hover:text-mangarr-text text-xs underline ml-2"
                >
                  Clear
                </button>
              </div>
              <Button
                size="sm"
                onClick={() => setBulkModalOpen(true)}
                rightIcon={<ChevronRight className="w-4 h-4" />}
              >
                Match to Series
              </Button>
            </div>
          )}

          {unmatchedFiles.length === 0 ? (
            <div className="py-10 text-center">
              <CheckCircle2 className="w-10 h-10 mx-auto mb-3 text-mangarr-success opacity-60" />
              <p className="text-mangarr-muted text-sm">All files are matched.</p>
            </div>
          ) : (
            <div className="divide-y divide-mangarr-border">
              {groups.map((group) => {
                const collapsed = collapsedGroups.has(group.title);
                const state = groupState(group.files);
                return (
                  <div key={group.title}>
                    {/* Group header */}
                    <div
                      className="px-5 py-2.5 bg-mangarr-input/30 flex items-center gap-3 cursor-pointer hover:bg-mangarr-input/60"
                      onClick={() => toggleCollapse(group.title)}
                    >
                      <TriCheckbox
                        state={state}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleGroup(group.files);
                        }}
                      />
                      {collapsed ? (
                        <ChevronRight className="w-4 h-4 text-mangarr-muted" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-mangarr-muted" />
                      )}
                      <p className="text-mangarr-text text-sm font-medium flex-1 truncate">
                        {group.title}
                      </p>
                      <span className="bg-mangarr-border/60 text-mangarr-muted text-xs px-2 py-0.5 rounded-full">
                        {group.files.length} file{group.files.length === 1 ? '' : 's'}
                      </span>
                    </div>

                    {/* Group files */}
                    {!collapsed && (
                      <div>
                        {group.files.map((file) => {
                          const checked = selectedIds.has(file.id);
                          return (
                            <div
                              key={file.id}
                              onClick={() => toggleFile(file.id)}
                              className={`px-5 py-2.5 pl-12 flex items-center gap-3 cursor-pointer border-t border-mangarr-border/50 ${
                                checked
                                  ? 'bg-mangarr-accent/5'
                                  : 'hover:bg-mangarr-input/40'
                              }`}
                            >
                              <TriCheckbox
                                state={checked ? 'all' : 'none'}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleFile(file.id);
                                }}
                              />
                              <div className="flex-1 min-w-0">
                                <p className="text-mangarr-text text-xs font-mono break-all">
                                  {file.file_name}
                                </p>
                                <p className="text-mangarr-disabled text-xs mt-0.5 truncate">
                                  {file.file_path}
                                </p>
                              </div>
                              <div className="hidden sm:flex items-center gap-3 text-xs text-mangarr-muted shrink-0">
                                {file.parsed_volume_number && (
                                  <span>Vol. {file.parsed_volume_number}</span>
                                )}
                                {file.parsed_chapter_number && (
                                  <span>Ch. {file.parsed_chapter_number}</span>
                                )}
                                <span className="text-mangarr-disabled">
                                  {formatBytes(file.file_size)}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {bulkModalOpen && (
          <BulkMatchModal
            fileIds={Array.from(selectedIds)}
            allSeries={allSeries}
            folders={folders}
            onClose={() => setBulkModalOpen(false)}
            onMatched={handleMatched}
          />
        )}
      </PageContainer>
    </div>
  );
}
