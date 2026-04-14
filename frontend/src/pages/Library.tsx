import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { PlusCircle, BookOpen, ArrowRightLeft, X, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import { seriesApi } from '../api/series';
import { api } from '../api/client';
import { TopBar } from '../components/layout/TopBar';
import { PageContainer } from '../components/layout/PageContainer';
import { SeriesGrid } from '../components/series/SeriesGrid';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { useNotificationStore } from '../store/notificationStore';
import type { Series } from '../types';

type StatusFilter = 'all' | 'ongoing' | 'completed' | 'hiatus' | 'cancelled';
type SortOption = 'title_asc' | 'recently_added' | 'pct_complete';

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'ongoing', label: 'Ongoing' },
  { value: 'completed', label: 'Completed' },
  { value: 'hiatus', label: 'Hiatus' },
  { value: 'cancelled', label: 'Cancelled' },
];

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'title_asc', label: 'Title A–Z' },
  { value: 'recently_added', label: 'Recently Added' },
  { value: 'pct_complete', label: '% Complete' },
];

function sortSeries(series: Series[], sort: SortOption): Series[] {
  const copy = [...series];
  switch (sort) {
    case 'title_asc':
      return copy.sort((a, b) => a.title.localeCompare(b.title));
    case 'recently_added':
      return copy.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    case 'pct_complete': {
      const pct = (s: Series) =>
        s.chapter_count ? ((s.downloaded_count ?? 0) / s.chapter_count) * 100 : 0;
      return copy.sort((a, b) => pct(b) - pct(a));
    }
  }
}

interface MigrateResult {
  series_id: number;
  title: string;
  status: 'migrated' | 'skipped' | 'no_match' | 'error';
  new_provider?: string;
  new_provider_id?: string;
  error?: string;
}

function MigrateModal({ onClose }: { onClose: () => void }) {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<MigrateResult[] | null>(null);
  const queryClient = useQueryClient();
  const addToast = useNotificationStore((s) => s.addToast);

  async function handleMigrate() {
    setRunning(true);
    setResults(null);
    try {
      const data = await api.post<MigrateResult[]>('/series/bulk-migrate', {
        target_provider: 'mangabaka',
      });
      setResults(data);
      const migrated = data.filter((r) => r.status === 'migrated').length;
      addToast(`Migrated ${migrated} series to MangaBaka`, 'success');
      void queryClient.invalidateQueries({ queryKey: ['series'] });
    } catch (e) {
      addToast(`Migration failed: ${(e as Error).message}`, 'error');
    } finally {
      setRunning(false);
    }
  }

  const migrated = results?.filter((r) => r.status === 'migrated').length ?? 0;
  const noMatch = results?.filter((r) => r.status === 'no_match').length ?? 0;
  const errors = results?.filter((r) => r.status === 'error').length ?? 0;

  return (
    <Modal
      isOpen
      title="Migrate Library to MangaBaka"
      onClose={onClose}
      footer={
        results ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose} disabled={running}>Cancel</Button>
            <Button onClick={() => void handleMigrate()} disabled={running}>
              {running ? 'Migrating…' : 'Migrate All'}
            </Button>
          </div>
        )
      }
    >
      {!results && !running && (
        <div className="space-y-3 text-sm text-mangarr-muted">
          <p>
            This will search MangaBaka for every series currently sourced from MangaDex and
            switch them over automatically.
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Series metadata (cover, description, tags) will be updated from MangaBaka.</li>
            <li>Existing chapter records and file links are preserved.</li>
            <li>MangaBaka does not expose individual chapters — chapter tracking stays
                file-based after migration.</li>
            <li>Series with no MangaBaka match will be skipped.</li>
          </ul>
        </div>
      )}

      {running && (
        <div className="flex items-center gap-3 py-6 justify-center text-mangarr-muted">
          <Loader className="w-5 h-5 animate-spin" />
          <span>Searching and migrating… this may take a minute.</span>
        </div>
      )}

      {results && (
        <div className="space-y-3">
          {/* Summary */}
          <div className="flex gap-4 text-sm">
            <span className="text-mangarr-success flex items-center gap-1">
              <CheckCircle className="w-4 h-4" /> {migrated} migrated
            </span>
            {noMatch > 0 && (
              <span className="text-mangarr-muted flex items-center gap-1">
                <X className="w-4 h-4" /> {noMatch} no match
              </span>
            )}
            {errors > 0 && (
              <span className="text-mangarr-danger flex items-center gap-1">
                <AlertCircle className="w-4 h-4" /> {errors} errors
              </span>
            )}
          </div>

          {/* Row list */}
          <div className="max-h-64 overflow-y-auto space-y-1">
            {results.map((r) => (
              <div
                key={r.series_id}
                className="flex items-center gap-2 text-xs py-1 border-b border-mangarr-border/40"
              >
                {r.status === 'migrated' && <CheckCircle className="w-3.5 h-3.5 text-mangarr-success shrink-0" />}
                {r.status === 'no_match' && <X className="w-3.5 h-3.5 text-mangarr-muted shrink-0" />}
                {r.status === 'error' && <AlertCircle className="w-3.5 h-3.5 text-mangarr-danger shrink-0" />}
                <span className="flex-1 truncate text-mangarr-text">{r.title}</span>
                {r.status === 'error' && (
                  <span className="text-mangarr-danger truncate max-w-[200px]">{r.error}</span>
                )}
                {r.status === 'no_match' && (
                  <span className="text-mangarr-disabled">not found</span>
                )}
                {r.status === 'migrated' && r.new_provider_id && (
                  <span className="text-mangarr-muted font-mono">#{r.new_provider_id}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}

function EmptyState() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-20 h-20 bg-mangarr-card border border-mangarr-border rounded-2xl flex items-center justify-center mb-6">
        <BookOpen className="w-10 h-10 text-mangarr-muted" />
      </div>
      <h2 className="text-mangarr-text text-xl font-semibold mb-2">No manga in your library</h2>
      <p className="text-mangarr-muted text-sm mb-6 max-w-xs">
        Start building your collection by searching for manga and adding them to your library.
      </p>
      <Button
        onClick={() => navigate('/add')}
        leftIcon={<PlusCircle className="w-4 h-4" />}
      >
        Add Series
      </Button>
    </div>
  );
}

export function Library() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sort, setSort] = useState<SortOption>('title_asc');
  const [showMigrate, setShowMigrate] = useState(false);
  const navigate = useNavigate();

  const { data: allSeries = [], isLoading, error } = useQuery({
    queryKey: ['series'],
    queryFn: () => seriesApi.list(),
  });

  const hasMangadexSeries = allSeries.some((s) => s.metadata_provider === 'mangadex');

  const filtered = useMemo(() => {
    const byStatus =
      statusFilter === 'all'
        ? allSeries
        : allSeries.filter((s) => s.status === statusFilter);
    return sortSeries(byStatus, sort);
  }, [allSeries, statusFilter, sort]);

  return (
    <div className="flex flex-col h-full">
      <TopBar
        title="Library"
        rightContent={
          <div className="flex items-center gap-2">
            {hasMangadexSeries && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowMigrate(true)}
                leftIcon={<ArrowRightLeft className="w-4 h-4" />}
              >
                Migrate to MangaBaka
              </Button>
            )}
            <Button
              size="sm"
              onClick={() => navigate('/add')}
              leftIcon={<PlusCircle className="w-4 h-4" />}
            >
              Add Series
            </Button>
          </div>
        }
      />
      <PageContainer>
        {/* Filter bar */}
        {!isLoading && allSeries.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 mb-6">
            {/* Status filters */}
            <div className="flex items-center gap-1 bg-mangarr-card border border-mangarr-border rounded-lg p-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setStatusFilter(f.value)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    statusFilter === f.value
                      ? 'bg-mangarr-accent text-white'
                      : 'text-mangarr-muted hover:text-mangarr-text hover:bg-mangarr-input'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {/* Sort */}
            <div className="flex items-center gap-2 ml-auto">
              <label className="text-mangarr-muted text-xs font-medium">Sort:</label>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortOption)}
                className="select-base text-xs py-1.5 pr-8"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Count */}
            <span className="text-mangarr-muted text-xs">
              {filtered.length} series
            </span>
          </div>
        )}

        {error && (
          <div className="bg-mangarr-danger/10 border border-mangarr-danger/30 rounded-lg p-4 mb-6">
            <p className="text-mangarr-danger text-sm">
              Failed to load library: {(error as Error).message}
            </p>
          </div>
        )}

        <SeriesGrid
          series={filtered}
          isLoading={isLoading}
          emptyState={<EmptyState />}
        />
      </PageContainer>

      {showMigrate && <MigrateModal onClose={() => setShowMigrate(false)} />}
    </div>
  );
}
