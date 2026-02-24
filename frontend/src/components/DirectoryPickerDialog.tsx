import { useState, useEffect, useCallback } from 'react';
import {
  Folder,
  FolderOpen,
  ChevronRight,
  ArrowUp,
  Loader2,
} from 'lucide-react';
import { browseDirectory, type BrowseResponse } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '@/components/ui/sheet';

interface DirectoryPickerDialogProps {
  open: boolean;
  onSelect: (path: string) => void;
  onCancel: () => void;
  initialPath?: string;
}

function Breadcrumb({
  path,
  onNavigate,
}: {
  path: string;
  onNavigate: (path: string) => void;
}) {
  const sep = path.includes('\\') ? '\\' : '/';
  const parts = path.split(sep).filter(Boolean);

  const segments: { label: string; path: string }[] = [];
  let accumulated = path.startsWith(sep) ? sep : '';
  for (const part of parts) {
    accumulated = accumulated + (accumulated.endsWith(sep) ? '' : sep) + part;
    segments.push({ label: part, path: accumulated });
  }

  return (
    <div className="flex items-center gap-0.5 text-xs text-muted-foreground overflow-x-auto min-w-0">
      <button
        type="button"
        className="shrink-0 hover:text-foreground transition-colors px-1"
        onClick={() => onNavigate(sep)}
      >
        {sep}
      </button>
      {segments.map((seg, i) => (
        <span key={seg.path} className="flex items-center gap-0.5 shrink-0">
          {i > 0 && <ChevronRight className="size-3 text-muted-foreground/50" />}
          <button
            type="button"
            className={`hover:text-foreground transition-colors px-0.5 truncate max-w-[120px] ${
              i === segments.length - 1 ? 'text-foreground font-medium' : ''
            }`}
            onClick={() => onNavigate(seg.path)}
            title={seg.path}
          >
            {seg.label}
          </button>
        </span>
      ))}
    </div>
  );
}

export function DirectoryPickerDialog({
  open,
  onSelect,
  onCancel,
  initialPath,
}: DirectoryPickerDialogProps) {
  const [data, setData] = useState<BrowseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [manualPath, setManualPath] = useState('');

  const navigate = useCallback(async (path?: string) => {
    setLoading(true);
    setError('');
    try {
      const result = await browseDirectory(path);
      setData(result);
      setManualPath(result.current);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      navigate(initialPath || undefined);
    }
  }, [open, initialPath, navigate]);

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (manualPath.trim()) {
      navigate(manualPath.trim());
    }
  };

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onCancel()}>
      <SheetContent side="right" className="flex flex-col w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Select Directory</SheetTitle>
          <SheetDescription>Navigate to a folder and click "Select" to confirm.</SheetDescription>
        </SheetHeader>

        {data && (
          <div className="px-4">
            <Breadcrumb path={data.current} onNavigate={navigate} />
          </div>
        )}

        {data?.parent && (
          <div className="px-4">
            <button
              type="button"
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors py-1"
              onClick={() => navigate(data.parent!)}
            >
              <ArrowUp className="size-3.5" />
              <span>Up to parent</span>
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-4 min-h-0">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <p className="text-sm text-destructive py-4">{error}</p>
          )}

          {!loading && !error && data && data.children.length === 0 && (
            <p className="text-sm text-muted-foreground py-4">No subdirectories.</p>
          )}

          {!loading && !error && data && data.children.length > 0 && (
            <div className="space-y-0.5">
              {data.children.map((child) => (
                <button
                  key={child.path}
                  type="button"
                  className="flex items-center gap-2.5 w-full rounded-md px-2.5 py-2 text-sm hover:bg-accent transition-colors text-left"
                  onClick={() => navigate(child.path)}
                >
                  {child.has_children ? (
                    <Folder className="size-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className="truncate">{child.name}</span>
                  {child.has_children && (
                    <ChevronRight className="size-3.5 shrink-0 text-muted-foreground/50 ml-auto" />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="px-4">
          <form onSubmit={handleManualSubmit} className="flex gap-2">
            <Input
              type="text"
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              placeholder="Type a path and press Enter"
              className="h-8 text-xs flex-1"
            />
            <Button type="submit" variant="ghost" size="sm" className="shrink-0 h-8">
              Go
            </Button>
          </form>
        </div>

        <SheetFooter className="flex-row gap-2 px-4 pb-4">
          <Button
            onClick={() => data && onSelect(data.current)}
            disabled={!data}
          >
            Select
          </Button>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
