import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PlusCircle, BookOpen } from 'lucide-react';
import { seriesApi } from '../api/series';
import { TopBar } from '../components/layout/TopBar';
import { PageContainer } from '../components/layout/PageContainer';
import { SeriesGrid } from '../components/series/SeriesGrid';
import { Button } from '../components/ui/Button';
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
  const navigate = useNavigate();

  const { data: allSeries = [], isLoading, error } = useQuery({
    queryKey: ['series'],
    queryFn: () => seriesApi.list(),
  });

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
          <Button
            size="sm"
            onClick={() => navigate('/add')}
            leftIcon={<PlusCircle className="w-4 h-4" />}
          >
            Add Series
          </Button>
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
    </div>
  );
}
