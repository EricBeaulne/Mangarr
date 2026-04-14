import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  RefreshCw,
  FolderSync,
  Download,
  FileX,
  CheckCircle,
  HardDrive,
  Pencil,
  X,
  Save,
  BookOpen,
  ArrowRight,
  AlertTriangle,
  MoveRight,
  ExternalLink,
  Copy,
  Check,
  Trash2,
} from 'lucide-react';
import { seriesApi } from '../api/series';
import type { OrganizeProposal } from '../api/series';
import { api } from '../api/client';
import { TopBar } from '../components/layout/TopBar';
import { PageContainer } from '../components/layout/PageContainer';
import { Button } from '../components/ui/Button';
import { StatusBadge, ContentRatingBadge, Badge } from '../components/ui/Badge';
import { Spinner } from '../components/ui/Spinner';
import { useNotificationStore } from '../store/notificationStore';
import type { Chapter } from '../types';

// ── File types ───────────────────────────────────────────────────────────────
interface LinkedChapter {
  id: number;
  chapter_number: string | null;
  volume_number: string | null;
  title: string | null;
}

interface SeriesFile {
  id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  extension: string;
  parsed_volume_number: string | null;
  parsed_chapter_number: string | null;
  scan_state: string;
  chapter_id: number | null;
  linked_chapter: LinkedChapter | null;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// ── File row with inline edit ─────────────────────────────────────────────────
function FileRow({
  file,
  seriesId,
  onUpdated,
  onDeleted,
}: {
  file: SeriesFile;
  seriesId: number;
  onUpdated: (updated: SeriesFile) => void;
  onDeleted: (fileId: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [vol, setVol] = useState(file.parsed_volume_number ?? '');
  const [ch, setCh] = useState(file.parsed_chapter_number ?? '');
  const [saving, setSaving] = useState(false);
  const [pathCopied, setPathCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const addToast = useNotificationStore((s) => s.addToast);

  async function handleCopyPath() {
    try {
      await navigator.clipboard.writeText(file.file_path);
      setPathCopied(true);
      setTimeout(() => setPathCopied(false), 2000);
      addToast('Full path copied', 'success');
    } catch {
      addToast('Could not copy path', 'error');
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const updated = await api.put<SeriesFile>(
        `/series/${seriesId}/files/${file.id}`,
        {
          parsed_volume_number: vol || null,
          parsed_chapter_number: ch || null,
        },
      );
      onUpdated(updated);
      setEditing(false);
      addToast('File mapping updated', 'success');
    } catch (e) {
      addToast(`Save failed: ${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(deleteFromDisk: boolean) {
    setDeleting(true);
    try {
      await api.delete<void>(
        `/series/${seriesId}/files/${file.id}?delete_from_disk=${deleteFromDisk}`,
      );
      addToast(
        deleteFromDisk ? 'File deleted from disk' : 'File removed from library',
        'success',
      );
      onDeleted(file.id);
    } catch (e) {
      addToast(`Delete failed: ${(e as Error).message}`, 'error');
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  // For volume-only files (no chapter_number in parsed), show "Vol. X (whole volume)"
  const isVolumeFile = !file.parsed_chapter_number && !!file.parsed_volume_number;
  const linkedLabel = file.linked_chapter
    ? isVolumeFile
      ? `Vol. ${file.linked_chapter.volume_number ?? file.parsed_volume_number} (whole volume)`
      : [
          file.linked_chapter.volume_number ? `Vol. ${file.linked_chapter.volume_number}` : null,
          file.linked_chapter.chapter_number ? `Ch. ${file.linked_chapter.chapter_number}` : null,
          file.linked_chapter.title,
        ]
          .filter(Boolean)
          .join(' · ')
    : null;

  return (
    <tr className="border-b border-mangarr-border hover:bg-mangarr-input/40 transition-colors group">
      {/* Filename + full path */}
      <td className="py-2.5 px-4 text-sm min-w-0 max-w-md lg:max-w-xl align-top">
        <div className="text-mangarr-text text-sm font-medium truncate" title={file.file_name}>
          {file.file_name}
        </div>
        <p
          className="text-mangarr-muted text-[11px] font-mono break-all mt-1 leading-snug select-text"
          title={file.file_path}
        >
          {file.file_path}
        </p>
        <span className="text-mangarr-disabled text-xs mt-0.5 inline-block">{formatBytes(file.file_size)}</span>
      </td>

      {/* Vol / Ch detected */}
      <td className="py-2.5 px-4 text-sm w-40">
        {editing ? (
          <div className="flex gap-1.5">
            <input
              className="input-base w-16 py-1 text-xs text-center"
              placeholder="Vol"
              value={vol}
              onChange={(e) => setVol(e.target.value)}
            />
            <input
              className="input-base w-16 py-1 text-xs text-center"
              placeholder="Ch"
              value={ch}
              onChange={(e) => setCh(e.target.value)}
            />
          </div>
        ) : (
          <span className="text-mangarr-muted text-xs font-mono">
            {file.parsed_volume_number ? `Vol.${file.parsed_volume_number}` : ''}
            {file.parsed_volume_number && file.parsed_chapter_number ? ' ' : ''}
            {file.parsed_chapter_number ? `Ch.${file.parsed_chapter_number}` : ''}
            {!file.parsed_volume_number && !file.parsed_chapter_number ? '—' : ''}
          </span>
        )}
      </td>

      {/* Linked MangaDex chapter */}
      <td className="py-2.5 px-4 text-sm hidden md:table-cell">
        {linkedLabel ? (
          <span className="text-mangarr-success text-xs flex items-center gap-1">
            <CheckCircle className="w-3 h-3 shrink-0" />
            {linkedLabel}
          </span>
        ) : (
          <span className="text-mangarr-muted text-xs flex items-center gap-1">
            <FileX className="w-3 h-3 shrink-0" />
            Not linked
          </span>
        )}
      </td>

      {/* Actions */}
      <td className="py-2.5 px-4 w-28 text-right align-top">
        {editing ? (
          <div className="flex items-center justify-end gap-1">
            <button
              onClick={handleSave}
              disabled={saving}
              className="p-1 rounded hover:bg-mangarr-accent/20 text-mangarr-accent transition-colors"
              title="Save"
            >
              {saving ? <Spinner size="sm" /> : <Save className="w-3.5 h-3.5" />}
            </button>
            <button
              onClick={() => { setEditing(false); setVol(file.parsed_volume_number ?? ''); setCh(file.parsed_chapter_number ?? ''); }}
              className="p-1 rounded hover:bg-mangarr-danger/20 text-mangarr-muted hover:text-mangarr-danger transition-colors"
              title="Cancel"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : confirmDelete ? (
          <div className="flex flex-col items-end gap-1">
            <p className="text-[10px] text-mangarr-muted text-right">Delete file?</p>
            <div className="flex items-center gap-1">
              <button
                type="button"
                disabled={deleting}
                onClick={() => void handleDelete(false)}
                className="px-1.5 py-0.5 rounded text-[10px] bg-mangarr-input hover:bg-mangarr-border text-mangarr-text transition-colors"
                title="Remove from library only"
              >
                Library only
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={() => void handleDelete(true)}
                className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/60 hover:bg-red-800/80 text-red-300 transition-colors"
                title="Delete file from disk"
              >
                {deleting ? <Spinner size="sm" /> : 'From disk'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="p-1 rounded hover:bg-mangarr-input text-mangarr-muted transition-colors"
                title="Cancel"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-end gap-0.5">
            <button
              type="button"
              onClick={() => void handleCopyPath()}
              className="p-1 rounded opacity-100 md:opacity-0 md:group-hover:opacity-100 hover:bg-mangarr-input text-mangarr-muted hover:text-mangarr-text transition-all"
              title="Copy full path"
            >
              {pathCopied ? (
                <Check className="w-3.5 h-3.5 text-mangarr-success" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="p-1 rounded opacity-100 md:opacity-0 md:group-hover:opacity-100 hover:bg-mangarr-input text-mangarr-muted hover:text-mangarr-text transition-all"
              title="Edit mapping"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="p-1 rounded opacity-100 md:opacity-0 md:group-hover:opacity-100 hover:bg-red-900/40 text-mangarr-muted hover:text-red-400 transition-all"
              title="Delete file"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}

function CoverImage({
  mangadexId,
  coverFilename,
  title,
}: {
  mangadexId: string;
  coverFilename: string | null;
  title: string;
}) {
  const hue = title.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
  const initials = title
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');

  const remoteUrl = useMemo(() => {
    if (!coverFilename) return null;
    return `https://uploads.mangadex.org/covers/${mangadexId}/${coverFilename}.512.jpg`;
  }, [mangadexId, coverFilename]);

  const localUrl = coverFilename
    ? `${window.location.origin}/covers/${coverFilename}`
    : null;

  const [src, setSrc] = useState<string | null>(() => localUrl ?? remoteUrl);
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div
        className="w-full h-full rounded-xl flex items-center justify-center"
        style={{
          background: `linear-gradient(135deg, hsl(${hue},45%,20%) 0%, hsl(${(hue + 40) % 360},40%,14%) 100%)`,
        }}
      >
        <span className="text-5xl font-bold text-white/30 select-none">{initials}</span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={title}
      className="w-full h-full object-cover rounded-xl"
      onError={() => {
        if (localUrl && remoteUrl && src === localUrl) {
          setSrc(remoteUrl);
          return;
        }
        setFailed(true);
      }}
    />
  );
}

function parseFloat2(val: string | null): number {
  if (!val) return 0;
  return parseFloat(val) || 0;
}

function sortChapters(chapters: Chapter[]): Chapter[] {
  return [...chapters].sort((a, b) => {
    const hasCh = (c: Chapter) => c.chapter_number !== null && c.chapter_number !== undefined;
    // Real chapters (with chapter_number) first, sorted numerically
    if (hasCh(a) && hasCh(b)) return parseFloat2(a.chapter_number) - parseFloat2(b.chapter_number);
    // Synthetic volume-only chapters at the end, sorted by volume
    if (!hasCh(a) && !hasCh(b)) return parseFloat2(a.volume_number) - parseFloat2(b.volume_number);
    return hasCh(a) ? -1 : 1;
  });
}

function getProviderUrl(provider: string, metadataId: string): string | null {
  if (provider === 'mangadex') {
    return `https://mangadex.org/title/${metadataId}`;
  } else if (provider === 'mangabaka') {
    return `https://mangabaka.org/${metadataId}`;
  }
  return null;
}

interface ChapterRowProps {
  chapter: Chapter;
  index: number;
}

function ChapterRow({ chapter }: ChapterRowProps) {
  const isDownloaded = chapter.is_downloaded;

  return (
    <tr
      className={`border-b border-mangarr-border transition-colors hover:bg-mangarr-input/50 ${
        !isDownloaded ? 'opacity-50' : ''
      }`}
    >
      <td className="py-2.5 px-4 text-mangarr-muted text-sm font-mono w-20">
        {chapter.chapter_number ?? (chapter.volume_number ? `Vol.${chapter.volume_number}` : '—')}
      </td>
      <td className="py-2.5 px-4 text-sm">
        <span className={isDownloaded ? 'text-mangarr-text' : 'text-mangarr-muted'}>
          {chapter.title || (chapter.chapter_number ? `Chapter ${chapter.chapter_number}` : chapter.volume_number ? `Volume ${chapter.volume_number}` : 'Unknown')}
        </span>
      </td>
      <td className="py-2.5 px-4 text-mangarr-muted text-sm w-24 hidden md:table-cell">
        {chapter.volume_number ? `Vol. ${chapter.volume_number}` : '—'}
      </td>
      <td className="py-2.5 px-4 text-mangarr-muted text-xs w-32 hidden lg:table-cell">
        {chapter.publish_at
          ? new Date(chapter.publish_at).toLocaleDateString()
          : '—'}
      </td>
      <td className="py-2.5 px-4 w-16 text-right">
        {isDownloaded ? (
          <CheckCircle className="w-4 h-4 text-mangarr-success inline-block" />
        ) : (
          <FileX className="w-4 h-4 text-mangarr-muted inline-block" />
        )}
      </td>
    </tr>
  );
}

// ── Organize preview modal ────────────────────────────────────────────────────
function OrganizeModal({
  proposals,
  onConfirm,
  onClose,
  isExecuting,
  results,
}: {
  proposals: OrganizeProposal[];
  onConfirm: () => void;
  onClose: () => void;
  isExecuting: boolean;
  results: OrganizeProposal[] | null;
}) {
  const toMove   = proposals.filter(p => p.source !== p.destination && !p.would_conflict);
  const already  = proposals.filter(p => p.source === p.destination);
  const conflicts = proposals.filter(p => p.would_conflict);

  const basename = (p: string) => p.split(/[\\/]/).pop() ?? p;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-mangarr-card border border-mangarr-border rounded-xl w-full max-w-3xl max-h-[80vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-mangarr-border">
          <div>
            <h2 className="text-mangarr-text font-semibold">Organize Files — Preview</h2>
            <p className="text-mangarr-muted text-xs mt-0.5">
              Review proposed renames before anything moves on disk
            </p>
          </div>
          <button onClick={onClose} className="text-mangarr-muted hover:text-mangarr-text transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Summary pills */}
        <div className="flex gap-3 px-6 py-3 border-b border-mangarr-border text-xs">
          <span className="flex items-center gap-1 bg-mangarr-accent/10 text-mangarr-accent px-2.5 py-1 rounded-full">
            <MoveRight className="w-3 h-3" /> {toMove.length} will rename/move
          </span>
          {already.length > 0 && (
            <span className="flex items-center gap-1 bg-mangarr-success/10 text-mangarr-success px-2.5 py-1 rounded-full">
              <CheckCircle className="w-3 h-3" /> {already.length} already correct
            </span>
          )}
          {conflicts.length > 0 && (
            <span className="flex items-center gap-1 bg-mangarr-danger/10 text-mangarr-danger px-2.5 py-1 rounded-full">
              <AlertTriangle className="w-3 h-3" /> {conflicts.length} conflict
            </span>
          )}
        </div>

        {/* File list */}
        <div className="flex-1 overflow-y-auto px-6 py-3 space-y-2">
          {results ? (
            // Show results after execution
            results.map((r) => (
              <div key={r.file_id} className="text-xs flex items-start gap-2 py-1.5 border-b border-mangarr-border/50 last:border-0">
                {r.error ? (
                  <AlertTriangle className="w-3.5 h-3.5 text-mangarr-danger mt-0.5 shrink-0" />
                ) : r.moved ? (
                  <CheckCircle className="w-3.5 h-3.5 text-mangarr-success mt-0.5 shrink-0" />
                ) : (
                  <CheckCircle className="w-3.5 h-3.5 text-mangarr-muted mt-0.5 shrink-0" />
                )}
                <div className="min-w-0">
                  <p className={`font-mono truncate ${r.error ? 'text-mangarr-danger' : 'text-mangarr-text'}`}>
                    {basename(r.destination)}
                  </p>
                  {r.error && <p className="text-mangarr-danger mt-0.5">{r.error}</p>}
                  {r.note && <p className="text-mangarr-muted mt-0.5">{r.note}</p>}
                </div>
              </div>
            ))
          ) : proposals.length === 0 ? (
            <p className="text-mangarr-muted text-sm py-6 text-center">No files to organize.</p>
          ) : (
            proposals.map((p) => {
              const same = p.source === p.destination;
              return (
                <div key={p.file_id} className={`text-xs py-2 border-b border-mangarr-border/50 last:border-0 ${same ? 'opacity-40' : ''}`}>
                  {p.would_conflict && (
                    <p className="text-mangarr-danger flex items-center gap-1 mb-1">
                      <AlertTriangle className="w-3 h-3" /> Conflict — destination already exists
                    </p>
                  )}
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-mangarr-muted truncate flex-1">{basename(p.source)}</span>
                    <ArrowRight className="w-3.5 h-3.5 text-mangarr-disabled shrink-0" />
                    <span className={`font-mono truncate flex-1 ${p.would_conflict ? 'text-mangarr-danger' : same ? 'text-mangarr-muted' : 'text-mangarr-text'}`}>
                      {basename(p.destination)}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-mangarr-border">
          <Button variant="ghost" onClick={onClose}>
            {results ? 'Close' : 'Cancel'}
          </Button>
          {!results && toMove.length > 0 && (
            <Button
              onClick={onConfirm}
              loading={isExecuting}
              leftIcon={<FolderSync className="w-4 h-4" />}
            >
              Move {toMove.length} file{toMove.length !== 1 ? 's' : ''}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

type Tab = 'chapters' | 'files';

export function SeriesDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const addToast = useNotificationStore((s) => s.addToast);
  const [monitorEdit, setMonitorEdit] = useState(false);
  const [monitorVal, setMonitorVal] = useState<'all' | 'future' | 'none'>('all');
  const [activeTab, setActiveTab] = useState<Tab>('chapters');
  const [organizeModal, setOrganizeModal] = useState<{
    proposals: OrganizeProposal[];
    results: OrganizeProposal[] | null;
  } | null>(null);

  const seriesId = Number(id);

  const { data: series, isLoading, error } = useQuery({
    queryKey: ['series', seriesId],
    queryFn: () => seriesApi.get(seriesId),
    enabled: !isNaN(seriesId),
  });

  const { mutate: refreshMeta, isPending: isRefreshing } = useMutation({
    mutationFn: () => seriesApi.refreshMetadata(seriesId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['series', seriesId] });
      addToast('Metadata refreshed', 'success');
    },
    onError: (err) => addToast(`Refresh failed: ${(err as Error).message}`, 'error'),
  });

  const { mutate: loadPreview, isPending: isLoadingPreview } = useMutation({
    mutationFn: () => seriesApi.previewOrganize(seriesId),
    onSuccess: (proposals) => setOrganizeModal({ proposals, results: null }),
    onError: (err) => addToast(`Preview failed: ${(err as Error).message}`, 'error'),
  });

  const { mutate: executeOrganize, isPending: isOrganizing } = useMutation({
    mutationFn: () => seriesApi.organizeFiles(seriesId),
    onSuccess: (results) => {
      const moved = results.filter((r) => r.moved).length;
      setOrganizeModal((m) => m ? { ...m, results } : null);
      queryClient.invalidateQueries({ queryKey: ['series-files', seriesId] });
      addToast(`Organized ${moved} file${moved !== 1 ? 's' : ''}`, 'success');
    },
    onError: (err) => addToast(`Organize failed: ${(err as Error).message}`, 'error'),
  });

  const { data: seriesFiles, isLoading: filesLoading } = useQuery({
    queryKey: ['series-files', seriesId],
    queryFn: () => api.get<SeriesFile[]>(`/series/${seriesId}/files`),
    enabled: activeTab === 'files' && !isNaN(seriesId),
  });


  const { mutate: updateMonitor, isPending: isUpdatingMonitor } = useMutation({
    mutationFn: (val: 'all' | 'future' | 'none') =>
      seriesApi.update(seriesId, { monitor_status: val }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['series', seriesId], (old: typeof series) =>
        old ? { ...old, monitor_status: updated.monitor_status } : old,
      );
      queryClient.invalidateQueries({ queryKey: ['series'] });
      setMonitorEdit(false);
      addToast('Monitor status updated', 'success');
    },
    onError: (err) => addToast(`Update failed: ${(err as Error).message}`, 'error'),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <TopBar title="Series" />
        <div className="flex items-center justify-center flex-1">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error || !series) {
    return (
      <div className="flex flex-col h-full">
        <TopBar title="Series" />
        <PageContainer>
          <div className="bg-mangarr-danger/10 border border-mangarr-danger/30 rounded-lg p-4">
            <p className="text-mangarr-danger text-sm">
              {error ? `Error: ${(error as Error).message}` : 'Series not found.'}
            </p>
          </div>
        </PageContainer>
      </div>
    );
  }

  const chapters = series.chapters ?? series.volumes?.flatMap((v) => v.chapters) ?? [];
  const sortedChapters = sortChapters(chapters);
  const downloadedCount = chapters.filter((c) => c.is_downloaded).length;
  const totalCount = chapters.length;

  let tags: string[] = [];
  try {
    tags = series.tags_json ? JSON.parse(series.tags_json) : [];
  } catch {
    tags = [];
  }

  const progressPct = totalCount > 0 ? Math.round((downloadedCount / totalCount) * 100) : 0;

  return (
    <div className="flex flex-col h-full">
      {organizeModal && (
        <OrganizeModal
          proposals={organizeModal.proposals}
          results={organizeModal.results}
          isExecuting={isOrganizing}
          onConfirm={() => executeOrganize()}
          onClose={() => setOrganizeModal(null)}
        />
      )}
      <TopBar
        title={series.title}
        rightContent={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            leftIcon={<ArrowLeft className="w-4 h-4" />}
          >
            Back
          </Button>
        }
      />
      <PageContainer>
        {/* Hero section */}
        <div className="flex flex-col md:flex-row gap-6 mb-8">
          {/* Cover */}
          <div
            className="w-full md:w-44 shrink-0 rounded-xl overflow-hidden border border-mangarr-border shadow-lg"
            style={{ aspectRatio: '2/3' }}
          >
            <CoverImage
              mangadexId={series.mangadex_id || series.metadata_id}
              coverFilename={series.cover_filename}
              title={series.title}
            />
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold text-mangarr-text mb-1">{series.title}</h1>
            {series.year && (
              <p className="text-mangarr-muted text-sm mb-3">{series.year}</p>
            )}

            {/* Badges */}
            <div className="flex flex-wrap gap-2 mb-4">
              <StatusBadge status={series.status} />
              {series.content_rating && (
                <ContentRatingBadge rating={series.content_rating} />
              )}
              {series.original_language && (
                <Badge variant="muted">{series.original_language.toUpperCase()}</Badge>
              )}
              <Badge variant="info" size="sm">
                {series.metadata_provider === 'mangadex' ? 'MangaDex' : series.metadata_provider === 'mangabaka' ? 'MangaBaka' : series.metadata_provider}
              </Badge>
            </div>

            {/* Description */}
            {series.description && (
              <p className="text-mangarr-muted text-sm leading-relaxed mb-4 line-clamp-4 max-w-2xl">
                {series.description}
              </p>
            )}

            {/* Tags */}
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-4">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-xs text-mangarr-muted bg-mangarr-input border border-mangarr-border px-2 py-0.5 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {/* Progress */}
            {totalCount > 0 && (
              <div className="mb-4 max-w-xs">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-mangarr-muted text-xs">
                    {downloadedCount} of {totalCount} chapters downloaded
                  </span>
                  <span className="text-mangarr-muted text-xs">{progressPct}%</span>
                </div>
                <div className="h-1.5 bg-mangarr-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-mangarr-accent rounded-full transition-all duration-500"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>
            )}

            {/* Monitor status */}
            <div className="flex items-center gap-2 mb-5">
              <span className="text-mangarr-muted text-sm">Monitor:</span>
              {monitorEdit ? (
                <div className="flex items-center gap-2">
                  <select
                    defaultValue={series.monitor_status}
                    onChange={(e) => setMonitorVal(e.target.value as typeof monitorVal)}
                    className="select-base text-xs py-1"
                  >
                    <option value="all">All Chapters</option>
                    <option value="future">Future Only</option>
                    <option value="none">None</option>
                  </select>
                  <Button
                    size="sm"
                    loading={isUpdatingMonitor}
                    onClick={() => updateMonitor(monitorVal)}
                  >
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setMonitorEdit(false)}
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <button
                  onClick={() => {
                    setMonitorVal(series.monitor_status);
                    setMonitorEdit(true);
                  }}
                  className="text-mangarr-accent text-sm hover:underline capitalize"
                >
                  {series.monitor_status === 'all'
                    ? 'All Chapters'
                    : series.monitor_status === 'future'
                    ? 'Future Only'
                    : 'None'}
                </button>
              )}
            </div>

            {/* Provider links */}
            <div className="mb-5">
              <p className="text-mangarr-muted text-xs uppercase tracking-wide mb-2">Source</p>
              <div className="flex flex-wrap gap-2">
                {getProviderUrl(series.metadata_provider, series.metadata_id) && (
                  <a
                    href={getProviderUrl(series.metadata_provider, series.metadata_id) || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-mangarr-input border border-mangarr-border rounded-lg hover:bg-mangarr-card transition-colors text-mangarr-accent hover:text-mangarr-accent"
                  >
                    {series.metadata_provider === 'mangadex' ? 'View on MangaDex' : 'View on MangaBaka'}
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                loading={isRefreshing}
                onClick={() => refreshMeta()}
                leftIcon={<RefreshCw className="w-4 h-4" />}
              >
                Refresh Metadata
              </Button>
              <Button
                variant="secondary"
                size="sm"
                loading={isLoadingPreview}
                onClick={() => loadPreview()}
                leftIcon={<FolderSync className="w-4 h-4" />}
              >
                Organize Files
              </Button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-mangarr-card border border-mangarr-border rounded-xl overflow-hidden">
          {/* Tab bar */}
          <div className="flex items-center border-b border-mangarr-border px-2 pt-1">
            <button
              onClick={() => setActiveTab('chapters')}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === 'chapters'
                  ? 'border-mangarr-accent text-mangarr-accent'
                  : 'border-transparent text-mangarr-muted hover:text-mangarr-text'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              Chapters
              <span className="ml-1 text-xs bg-mangarr-input px-1.5 py-0.5 rounded-full">
                {downloadedCount}/{totalCount}
              </span>
            </button>
            <button
              onClick={() => setActiveTab('files')}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === 'files'
                  ? 'border-mangarr-accent text-mangarr-accent'
                  : 'border-transparent text-mangarr-muted hover:text-mangarr-text'
              }`}
            >
              <HardDrive className="w-4 h-4" />
              Files
            </button>
            <div className="ml-auto flex items-center gap-3 pr-3 pb-1">
              {activeTab === 'chapters' && (
                <Badge variant={downloadedCount === totalCount && totalCount > 0 ? 'success' : 'muted'}>
                  <Download className="w-3 h-3 mr-1" />
                  {progressPct}%
                </Badge>
              )}
            </div>
          </div>

          {/* ── Chapters tab ── */}
          {activeTab === 'chapters' && (
            sortedChapters.length === 0 ? (
              <div className="py-12 text-center text-mangarr-muted">
                <p className="text-sm">No chapters found.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-mangarr-border bg-mangarr-input/30">
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider">#</th>
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider">Title</th>
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider hidden md:table-cell">Volume</th>
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider hidden lg:table-cell">Published</th>
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedChapters.map((chapter, i) => (
                      <ChapterRow key={chapter.id} chapter={chapter} index={i} />
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {/* ── Files tab ── */}
          {activeTab === 'files' && (
            filesLoading ? (
              <div className="py-12 flex justify-center">
                <Spinner size="md" />
              </div>
            ) : (seriesFiles ?? []).length === 0 ? (
              <div className="py-12 text-center text-mangarr-muted">
                <HardDrive className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No files matched to this series yet.</p>
                <p className="text-xs mt-1">Run a scan to detect files on disk.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-mangarr-border bg-mangarr-input/30">
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider min-w-0">
                        File
                      </th>
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider w-44">Detected Vol / Ch</th>
                      <th className="py-2 px-4 text-mangarr-muted text-xs font-medium uppercase tracking-wider hidden md:table-cell">Linked Chapter</th>
                      <th className="py-2 px-4 w-20" />
                    </tr>
                  </thead>
                  <tbody>
                    {(seriesFiles ?? []).map((f) => (
                      <FileRow
                        key={f.id}
                        file={f}
                        seriesId={seriesId}
                        onUpdated={(updated) => {
                          queryClient.setQueryData(
                            ['series-files', seriesId],
                            (old: SeriesFile[] | undefined) =>
                              old ? old.map((x) => (x.id === updated.id ? updated : x)) : [updated],
                          );
                        }}
                        onDeleted={(fileId) => {
                          queryClient.setQueryData(
                            ['series-files', seriesId],
                            (old: SeriesFile[] | undefined) =>
                              old ? old.filter((x) => x.id !== fileId) : [],
                          );
                          // Invalidate series stats so downloaded count refreshes
                          void queryClient.invalidateQueries({ queryKey: ['series', seriesId] });
                        }}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </div>
      </PageContainer>
    </div>
  );
}
