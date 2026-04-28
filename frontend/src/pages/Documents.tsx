import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  FolderOpen,
  FolderPlus,
  FolderSearch,
  ChevronRight,
  ChevronDown,
  FileText,
  Trash2,
  AlertTriangle,
  RefreshCw,
  X,
  Sparkles,
  Loader2,
} from 'lucide-react';
import {
  getDirectories,
  getDirectoryFiles,
  updateDirectory,
  deleteDirectory,
  openDirectory,
  openPath,
  pickDirectory,
  getHighlights,
  type DirectoryEntry,
  type DocumentFile,
  type KeyMoment,
} from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DirectoryForm } from '@/components/DirectoryForm';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function HighlightsPanel({ slug }: { slug: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['highlights', slug],
    queryFn: () => getHighlights(slug),
  });

  if (isLoading)
    return (
      <div className="flex flex-1 items-center justify-center py-8">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  if (error)
    return (
      <p className="px-4 text-sm text-destructive">{(error as Error).message}</p>
    );
  if (!data?.moments.length)
    return (
      <p className="px-4 text-sm text-muted-foreground">No key moments found for this document.</p>
    );

  return (
    <div className="flex-1 overflow-y-auto px-4 space-y-3">
      {data.moments.map((m: KeyMoment, i: number) => (
        <div key={i} className="flex gap-3">
          <span className="font-mono text-sm text-muted-foreground shrink-0 pt-0.5">
            {m.timestamp}
          </span>
          <p className="text-sm leading-relaxed">{m.description}</p>
        </div>
      ))}
    </div>
  );
}

function DirectoryFiles({ dirId, dirPath }: { dirId: number; dirPath: string }) {
  const { data: files, isLoading, error } = useQuery({
    queryKey: ['directory-files', dirId],
    queryFn: () => getDirectoryFiles(dirId),
  });
  const [activeSlug, setActiveSlug] = useState<string | null>(null);

  if (isLoading) return <p className="text-sm text-muted-foreground px-3 py-2">Loading files...</p>;
  if (error)
    return (
      <p className="text-sm text-destructive px-3 py-2">
        {(error as Error).message}
      </p>
    );
  if (!files?.length)
    return <p className="text-sm text-muted-foreground px-3 py-2">No documents yet.</p>;

  return (
    <>
      <div className="space-y-1 px-3 pb-3">
        {files.map((f: DocumentFile) => (
          <div
            key={f.name}
            className="flex items-center gap-3 rounded-md border bg-background px-3 py-2 text-sm"
          >
            <FileText className="size-4 shrink-0 text-muted-foreground" />
            <span className="flex-1 truncate font-medium">{f.name}</span>
            <span className="text-xs text-muted-foreground shrink-0">
              {formatSize(f.size_bytes)}
            </span>
            <span className="text-xs text-muted-foreground shrink-0">
              {formatDate(f.modified_at)}
            </span>
            {f.highlights_slug && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0 size-7"
                title="View key moments"
                onClick={() => setActiveSlug(f.highlights_slug!)}
              >
                <Sparkles className="size-3.5" />
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0 size-7"
              title="Open in file browser"
              onClick={async () => {
                try {
                  await openPath(`${dirPath}/${f.name}`);
                } catch (e) {
                  alert((e as Error).message);
                }
              }}
            >
              <FolderOpen className="size-3.5" />
            </Button>
          </div>
        ))}
      </div>
      <Sheet open={activeSlug !== null} onOpenChange={(open) => { if (!open) setActiveSlug(null); }}>
        <SheetContent side="right" className="flex flex-col w-full sm:max-w-md gap-4">
          <SheetHeader>
            <SheetTitle>Key Moments</SheetTitle>
            <SheetDescription className="truncate">
              {files.find((f: DocumentFile) => f.highlights_slug === activeSlug)?.name ?? activeSlug}
            </SheetDescription>
          </SheetHeader>
          {activeSlug && <HighlightsPanel slug={activeSlug} />}
        </SheetContent>
      </Sheet>
    </>
  );
}

function DirectoryCard({ dir }: { dir: DirectoryEntry }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [reattaching, setReattaching] = useState(false);
  const [newPath, setNewPath] = useState('');

  const removeMutation = useMutation({
    mutationFn: () => deleteDirectory(dir.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['directories'] }),
  });

  const reattachMutation = useMutation({
    mutationFn: (path: string) => updateDirectory(dir.id, path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['directories'] });
      setReattaching(false);
      setNewPath('');
    },
  });

  const handleReattach = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPath.trim()) return;
    reattachMutation.mutate(newPath.trim());
  };

  return (
    <Card className={!dir.exists ? 'border-destructive/50' : undefined}>
      <CardHeader className="p-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => dir.exists && setExpanded(!expanded)}
            className="flex items-center gap-2 flex-1 min-w-0 text-left"
            disabled={!dir.exists}
          >
            {dir.exists ? (
              expanded ? (
                <ChevronDown className="size-4 shrink-0" />
              ) : (
                <ChevronRight className="size-4 shrink-0" />
              )
            ) : (
              <AlertTriangle className="size-4 shrink-0 text-destructive" />
            )}
            <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <CardTitle className="text-sm font-semibold truncate">
                {dir.name}
              </CardTitle>
              <p className="text-xs text-muted-foreground truncate">{dir.path}</p>
            </div>
          </button>

          {dir.exists && (
            <span className="text-xs text-muted-foreground shrink-0">
              {dir.file_count} {dir.file_count === 1 ? 'file' : 'files'}
            </span>
          )}

          {dir.exists && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0 size-8"
              title="Open in file manager"
              onClick={async () => {
                try {
                  await openDirectory(dir.id);
                } catch (e) {
                  alert((e as Error).message);
                }
              }}
            >
              <FolderOpen className="size-4" />
            </Button>
          )}

          {!dir.exists && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() => setReattaching(!reattaching)}
            >
              <RefreshCw className="size-3.5 mr-1.5" />
              Re-attach
            </Button>
          )}

          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="shrink-0 size-8 text-muted-foreground hover:text-destructive"
            title="Remove directory"
            onClick={() => {
              if (confirm(`Remove "${dir.name}" from the list? Files on disk will not be deleted.`))
                removeMutation.mutate();
            }}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>

        {!dir.exists && !reattaching && (
          <p className="text-xs text-destructive mt-2">
            Directory not found. Click "Re-attach" to provide a new path.
          </p>
        )}

        {reattaching && (
          <form onSubmit={handleReattach} className="flex gap-2 mt-3">
            <Input
              type="text"
              placeholder="New directory path..."
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              className="flex-1 h-8 text-sm"
              autoFocus
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  const picked = await pickDirectory();
                  if (picked) setNewPath(picked);
                } catch (e) {
                  alert((e as Error).message);
                }
              }}
            >
              <FolderSearch className="size-3.5 mr-1.5" />
              Browse
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={reattachMutation.isPending || !newPath.trim()}
            >
              {reattachMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8"
              onClick={() => {
                setReattaching(false);
                setNewPath('');
              }}
            >
              <X className="size-4" />
            </Button>
            {reattachMutation.isError && (
              <span className="text-xs text-destructive self-center">
                {(reattachMutation.error as Error).message}
              </span>
            )}
          </form>
        )}
      </CardHeader>

      {expanded && dir.exists && (
        <CardContent className="p-0 pt-0">
          <DirectoryFiles dirId={dir.id} dirPath={dir.path} />
        </CardContent>
      )}
    </Card>
  );
}

export function Documents() {
  const queryClient = useQueryClient();
  const { data: directories, isLoading, error } = useQuery({
    queryKey: ['directories'],
    queryFn: getDirectories,
  });

  const [showAdd, setShowAdd] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Documents</h2>
          <p className="text-sm text-muted-foreground">
            Browse output folders and their transcripts.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAdd(!showAdd)}
        >
          <FolderPlus className="size-4 mr-1.5" />
          Add Directory
        </Button>
      </div>

      {showAdd && (
        <Card>
          <CardHeader className="p-4">
            <CardTitle className="text-sm">Register Output Directory</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <DirectoryForm
              idPrefix="docs-add"
              onSubmit={() => {
                queryClient.invalidateQueries({ queryKey: ['directories'] });
                setShowAdd(false);
              }}
              onCancel={() => setShowAdd(false)}
            />
          </CardContent>
        </Card>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Loading directories...</p>}
      {error && (
        <p className="text-sm text-destructive">
          Failed to load directories: {(error as Error).message}
        </p>
      )}

      {directories && directories.length === 0 && !showAdd && (
        <div className="rounded-lg border-2 border-dashed p-8 text-center">
          <FolderOpen className="mx-auto size-8 text-muted-foreground/50 mb-3" />
          <p className="text-muted-foreground text-sm">
            No output directories registered yet.
          </p>
          <p className="text-muted-foreground text-xs mt-1">
            Directories are auto-registered when transcriptions are saved, or you
            can add one manually.
          </p>
        </div>
      )}

      {directories && directories.length > 0 && (
        <div className="space-y-3">
          {directories.map((dir) => (
            <DirectoryCard key={dir.id} dir={dir} />
          ))}
        </div>
      )}
    </div>
  );
}
