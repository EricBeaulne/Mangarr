import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Search, CheckCircle } from 'lucide-react';
import { searchApi } from '../api/search';
import { seriesApi } from '../api/series';
import { libraryApi } from '../api/library';
import { TopBar } from '../components/layout/TopBar';
import { PageContainer } from '../components/layout/PageContainer';
import { Modal } from '../components/ui/Modal';
import { Button } from '../components/ui/Button';
import { StatusBadge, ContentRatingBadge } from '../components/ui/Badge';
import { Spinner } from '../components/ui/Spinner';
import { useNotificationStore } from '../store/notificationStore';
import type { SearchResult, RootFolder } from '../types';

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

interface AddModalProps {
  result: SearchResult;
  folders: RootFolder[];
  alreadyAdded: boolean;
  onClose: () => void;
  onSuccess: (id: number) => void;
}

function AddSeriesModal({ result, folders, alreadyAdded, onClose, onSuccess }: AddModalProps) {
  const [rootFolderId, setRootFolderId] = useState<number | ''>(
    folders[0]?.id ?? '',
  );
  const [monitorStatus, setMonitorStatus] = useState<'all' | 'future' | 'none'>('all');
  const [provider] = useState<'mangadex' | 'mangabaka'>((result as any).metadata_provider ?? 'mangadex');
  const addToast = useNotificationStore((s) => s.addToast);

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      seriesApi.add({
        metadata_id: result.mangadex_id,
        metadata_provider: provider,
        root_folder_id: Number(rootFolderId),
        monitor_status: monitorStatus,
      }),
    onSuccess: (series) => {
      addToast(`"${series.title}" added to library`, 'success');
      onSuccess(series.id);
    },
    onError: (err) => {
      addToast(`Failed to add series: ${(err as Error).message}`, 'error');
    },
  });

  const coverUrl = pickCoverSrc(result);
  const hue =
    result.title.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={alreadyAdded ? 'Already in Library' : 'Add to Library'}
      size="md"
      footer={
        alreadyAdded ? (
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              loading={isPending}
              disabled={rootFolderId === ''}
              onClick={() => mutate()}
            >
              Add Series
            </Button>
          </>
        )
      }
    >
      <div className="space-y-5">
        {/* Cover + title */}
        <div className="flex gap-4">
          <div className="w-20 shrink-0 rounded-md overflow-hidden" style={{ aspectRatio: '2/3' }}>
            {coverUrl ? (
              <img
                src={coverUrl}
                alt={result.title}
                className="w-full h-full object-cover"
                onError={(e) => {
                  const el = e.target as HTMLImageElement;
                  if (result.cover_url && el.src !== result.cover_url) {
                    el.src = result.cover_url;
                    return;
                  }
                  el.style.display = 'none';
                }}
              />
            ) : (
              <div
                className="w-full h-full flex items-center justify-center"
                style={{
                  background: `linear-gradient(135deg, hsl(${hue},45%,18%) 0%, hsl(${(hue + 40) % 360},40%,12%) 100%)`,
                }}
              >
                <span className="text-sm font-bold text-white/40">
                  {result.title.slice(0, 2).toUpperCase()}
                </span>
              </div>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-mangarr-text font-semibold text-base leading-tight mb-2">
              {result.title}
            </h3>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {result.status && (
                <StatusBadge status={result.status as never} size="sm" />
              )}
              {result.content_rating && (
                <ContentRatingBadge rating={result.content_rating} size="sm" />
              )}
              {result.year && (
                <span className="text-mangarr-muted text-xs">{result.year}</span>
              )}
            </div>
            {result.description && (
              <p className="text-mangarr-muted text-xs leading-relaxed line-clamp-3">
                {result.description}
              </p>
            )}
          </div>
        </div>

        {alreadyAdded ? (
          <div className="flex items-center gap-2 bg-mangarr-success/10 border border-mangarr-success/30 rounded-lg p-3">
            <CheckCircle className="w-4 h-4 text-mangarr-success shrink-0" />
            <p className="text-mangarr-success text-sm">This series is already in your library.</p>
          </div>
        ) : (
          <>
            {/* Root folder */}
            <div className="space-y-1.5">
              <label className="text-mangarr-text text-sm font-medium block">Root Folder</label>
              {folders.length === 0 ? (
                <p className="text-mangarr-warning text-xs">
                  No root folders configured. Please add one in Settings → Root Folders.
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

            {/* Monitor status */}
            <div className="space-y-1.5">
              <label className="text-mangarr-text text-sm font-medium block">Monitor</label>
              <select
                value={monitorStatus}
                onChange={(e) => setMonitorStatus(e.target.value as typeof monitorStatus)}
                className="select-base w-full text-sm"
              >
                <option value="all">All Chapters</option>
                <option value="future">Future Only</option>
                <option value="none">None</option>
              </select>
              <p className="text-mangarr-muted text-xs">
                {monitorStatus === 'all' && 'Monitor and download all chapters.'}
                {monitorStatus === 'future' && 'Only monitor new chapters released after adding.'}
                {monitorStatus === 'none' && 'Do not automatically monitor any chapters.'}
              </p>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

function SearchResultCard({
  result,
  existingIds,
  onSelect,
}: {
  result: SearchResult;
  existingIds: Set<string>;
  onSelect: (r: SearchResult) => void;
}) {
  const alreadyAdded = existingIds.has(result.mangadex_id);

  return (
    <div
      onClick={() => onSelect(result)}
      className="flex gap-3 p-3 bg-mangarr-card border border-mangarr-border rounded-lg cursor-pointer
                 hover:border-mangarr-accent/50 hover:bg-mangarr-input transition-all duration-150 group"
    >
      {/* Cover */}
      <div
        className="w-12 shrink-0 rounded overflow-hidden border border-mangarr-border"
        style={{ aspectRatio: '2/3' }}
      >
        <CoverThumb result={result} />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2 mb-1">
          <p className="text-mangarr-text text-sm font-medium leading-snug line-clamp-2 group-hover:text-mangarr-accent transition-colors">
            {result.title}
          </p>
          {alreadyAdded && (
            <CheckCircle className="w-4 h-4 text-mangarr-success shrink-0 mt-0.5" />
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {result.status && <StatusBadge status={result.status as never} size="sm" />}
          {result.content_rating && (
            <ContentRatingBadge rating={result.content_rating} size="sm" />
          )}
          {result.year && (
            <span className="text-mangarr-disabled text-xs">{result.year}</span>
          )}
        </div>
        {result.description && (
          <p className="text-mangarr-muted text-xs mt-1 line-clamp-2 leading-relaxed">
            {result.description}
          </p>
        )}
        {result.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {result.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="text-[10px] text-mangarr-disabled bg-mangarr-input px-1.5 py-0.5 rounded"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function AddSeries() {
  const [query, setQuery] = useState('');
  const [provider, setProvider] = useState<'mangadex' | 'mangabaka'>('mangabaka');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const navigate = useNavigate();

  // Debounce search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQuery(query), 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const { data: results = [], isLoading: isSearching } = useQuery({
    queryKey: ['search', debouncedQuery, provider],
    queryFn: () => searchApi.searchManga({ q: debouncedQuery, provider }),
    enabled: debouncedQuery.trim().length >= 2,
  });

  const { data: existingSeries = [] } = useQuery({
    queryKey: ['series'],
    queryFn: () => seriesApi.list(),
  });

  const { data: folders = [] } = useQuery({
    queryKey: ['folders'],
    queryFn: () => libraryApi.getFolders(),
  });

  const existingIds = new Set(
    existingSeries
      .map((s) => s.metadata_id || s.mangadex_id)
      .filter((id): id is string => id !== null),
  );

  const showResults = debouncedQuery.trim().length >= 2;

  return (
    <div className="flex flex-col h-full">
      <TopBar title="Add Series" />
      <PageContainer className="max-w-3xl mx-auto w-full">
        {/* Search input with provider selector */}
        <div className="space-y-3 mb-6">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-mangarr-muted" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search for manga by title..."
                autoFocus
                className="input-base w-full pl-10 pr-4 py-3 text-sm"
              />
              {isSearching && (
                <Spinner size="sm" className="absolute right-3 top-1/2 -translate-y-1/2" />
              )}
            </div>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value as 'mangadex' | 'mangabaka')}
              className="select-base text-sm px-3 py-3 min-w-[140px]"
            >
              <option value="mangadex">MangaDex</option>
              <option value="mangabaka">MangaBaka</option>
            </select>
          </div>
        </div>

        {/* Results */}
        {showResults && (
          <div className="space-y-2">
            {!isSearching && results.length === 0 && (
              <div className="text-center py-12 text-mangarr-muted">
                <p className="text-base mb-1">No results found</p>
                <p className="text-sm">Try a different search term</p>
              </div>
            )}
            {results.map((result) => (
              <SearchResultCard
                key={`${provider}-${result.mangadex_id}`}
                result={result}
                existingIds={existingIds}
                onSelect={setSelectedResult}
              />
            ))}
          </div>
        )}

        {!showResults && (
          <div className="text-center py-16 text-mangarr-muted">
            <Search className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Enter at least 2 characters to search</p>
          </div>
        )}

        {selectedResult && (
          <AddSeriesModal
            result={{...selectedResult, metadata_provider: provider}}
            folders={folders}
            alreadyAdded={existingIds.has(selectedResult.mangadex_id)}
            onClose={() => setSelectedResult(null)}
            onSuccess={(id) => navigate(`/series/${id}`)}
          />
        )}
      </PageContainer>
    </div>
  );
}
