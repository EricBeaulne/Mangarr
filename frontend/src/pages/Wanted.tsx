import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, ChevronDown, ChevronRight, ListX } from 'lucide-react';
import { seriesApi } from '../api/series';
import { TopBar } from '../components/layout/TopBar';
import { PageContainer } from '../components/layout/PageContainer';
import { Spinner } from '../components/ui/Spinner';
import type { WantedSeriesEntry, MissingChapter } from '../types';

// ── Cover image with gradient fallback ──────────────────────────────────────

function CoverThumb({
  coverFilename,
  title,
}: {
  coverFilename: string | null;
  title: string;
}) {
  const hue = title.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
  const initials = title
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');

  const localUrl = coverFilename
    ? `${window.location.origin}/covers/${coverFilename}`
    : null;

  const [failed, setFailed] = useState(false);

  if (!localUrl || failed) {
    return (
      <div
        className="w-full h-full rounded-lg flex items-center justify-center"
        style={{
          background: `linear-gradient(135deg, hsl(${hue},45%,20%) 0%, hsl(${(hue + 40) % 360},40%,14%) 100%)`,
        }}
      >
        <span className="text-xl font-bold text-white/30 select-none">{initials}</span>
      </div>
    );
  }

  return (
    <img
      src={localUrl}
      alt={title}
      className="w-full h-full object-cover rounded-lg"
      onError={() => setFailed(true)}
    />
  );
}

// ── Single series card ───────────────────────────────────────────────────────

function WantedCard({ entry }: { entry: WantedSeriesEntry }) {
  const [expanded, setExpanded] = useState(false);

  function chapterLabel(ch: MissingChapter): string {
    const parts: string[] = [];
    if (ch.chapter_number) parts.push(`Ch. ${ch.chapter_number}`);
    if (ch.volume_number) parts.push(`Vol. ${ch.volume_number}`);
    if (ch.title) parts.push(ch.title);
    return parts.length > 0 ? parts.join(' · ') : 'Unknown';
  }

  return (
    <div className="bg-mangarr-card border border-mangarr-border rounded-xl overflow-hidden">
      <div className="flex items-start gap-4 p-4">
        {/* Cover thumbnail */}
        <Link
          to={`/series/${entry.series_id}`}
          className="shrink-0 w-14 rounded-lg overflow-hidden border border-mangarr-border shadow"
          style={{ aspectRatio: '2/3' }}
        >
          <CoverThumb coverFilename={entry.cover_filename} title={entry.title} />
        </Link>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <Link
              to={`/series/${entry.series_id}`}
              className="text-mangarr-text font-semibold hover:text-mangarr-accent transition-colors truncate leading-snug"
            >
              {entry.title}
            </Link>
            <span className="shrink-0 text-xs font-medium text-mangarr-danger bg-mangarr-danger/10 border border-mangarr-danger/30 px-2 py-0.5 rounded-full">
              {entry.missing_count} missing
            </span>
          </div>
          <p className="text-mangarr-muted text-xs mt-1">
            {entry.missing_count} missing of {entry.total_chapters} total
          </p>

          {/* Expand/collapse toggle */}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="mt-2 inline-flex items-center gap-1 text-xs text-mangarr-muted hover:text-mangarr-text transition-colors"
          >
            {expanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
            {expanded ? 'Hide chapters' : 'Show chapters'}
          </button>
        </div>
      </div>

      {/* Expanded chapter list */}
      {expanded && (
        <div className="border-t border-mangarr-border px-4 py-3 bg-mangarr-input/20">
          <ul className="space-y-1">
            {entry.missing.map((ch) => (
              <li
                key={ch.id}
                className="flex items-center gap-2 text-xs text-mangarr-muted py-0.5"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-mangarr-danger/60 shrink-0" />
                <span className="font-mono">{chapterLabel(ch)}</span>
                {ch.publish_at && (
                  <span className="ml-auto text-mangarr-disabled shrink-0">
                    {new Date(ch.publish_at).toLocaleDateString()}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function Wanted() {
  const { data: entries, isLoading, error } = useQuery({
    queryKey: ['wanted'],
    queryFn: () => seriesApi.getWanted(),
  });

  const totalMissing = entries?.reduce((sum, e) => sum + e.missing_count, 0) ?? 0;

  return (
    <div className="flex flex-col h-full">
      <TopBar title="Wanted" />
      <PageContainer>
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <Spinner size="lg" />
          </div>
        ) : error ? (
          <div className="bg-mangarr-danger/10 border border-mangarr-danger/30 rounded-lg p-4">
            <p className="text-mangarr-danger text-sm">
              Failed to load wanted list: {(error as Error).message}
            </p>
          </div>
        ) : !entries || entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <CheckCircle2 className="w-12 h-12 text-mangarr-success mb-4 opacity-80" />
            <h2 className="text-mangarr-text font-semibold text-lg mb-1">All caught up!</h2>
            <p className="text-mangarr-muted text-sm">Nothing missing.</p>
          </div>
        ) : (
          <>
            {/* Summary header */}
            <div className="flex items-center gap-2 mb-5">
              <ListX className="w-5 h-5 text-mangarr-accent" />
              <p className="text-mangarr-muted text-sm">
                <span className="text-mangarr-text font-semibold">{entries.length}</span>{' '}
                {entries.length === 1 ? 'series' : 'series'} with missing chapters
                {' · '}
                <span className="text-mangarr-text font-semibold">{totalMissing}</span> total
                missing
              </p>
            </div>

            {/* Series cards */}
            <div className="space-y-3">
              {entries.map((entry) => (
                <WantedCard key={entry.series_id} entry={entry} />
              ))}
            </div>
          </>
        )}
      </PageContainer>
    </div>
  );
}
