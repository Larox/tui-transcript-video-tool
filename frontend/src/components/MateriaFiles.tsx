import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload as UploadIcon,
} from 'lucide-react';
import {
  listMateriaFiles,
  uploadMateriaFile,
  deleteMateriaFile,
  reindexMateria,
  type MateriaFileEntry,
} from '@/api/rag';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const ACCEPT = '.pdf,application/pdf';

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusIcon({ status }: { status: MateriaFileEntry['status'] }) {
  if (status === 'indexed')
    return <CheckCircle2 className="size-4 text-green-500 shrink-0" />;
  if (status === 'error')
    return <AlertCircle className="size-4 text-destructive shrink-0" />;
  return <Loader2 className="size-4 animate-spin text-primary shrink-0" />;
}

export function MateriaFiles({ collectionId }: { collectionId: number }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const { data: files = [], isLoading } = useQuery({
    queryKey: ['materia-files', collectionId],
    queryFn: () => listMateriaFiles(collectionId),
    refetchInterval: (q) => {
      const items = (q.state.data ?? []) as MateriaFileEntry[];
      const anyPending = items.some(
        (f) => f.status !== 'indexed' && f.status !== 'error',
      );
      return anyPending ? 2000 : false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadMateriaFile(collectionId, file),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['materia-files', collectionId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteMateriaFile(collectionId, id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['materia-files', collectionId] });
    },
  });

  const reindexMutation = useMutation({
    mutationFn: () => reindexMateria(collectionId),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['materia-files', collectionId] });
    },
  });

  const handleFiles = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(list)) {
        await uploadMutation.mutateAsync(f);
      }
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Archivos</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => reindexMutation.mutate()}
            disabled={reindexMutation.isPending}
          >
            <RefreshCw className="size-3.5 mr-1.5" />
            Reindexar
          </Button>
          <Button
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <Loader2 className="size-3.5 mr-1.5 animate-spin" />
            ) : (
              <UploadIcon className="size-3.5 mr-1.5" />
            )}
            Subir PDF
          </Button>
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      {isLoading ? (
        <div className="flex justify-center py-6">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : files.length === 0 ? (
        <p className="text-sm text-muted-foreground italic">
          No hay archivos en esta materia. Sube un PDF para empezar.
        </p>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <Card key={f.id} className="py-0">
              <CardContent className="px-4 py-3 flex items-center gap-3">
                <FileText className="size-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{f.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatSize(f.size_bytes)} · {f.status}
                    {f.error_message ? ` — ${f.error_message}` : ''}
                  </p>
                </div>
                <StatusIcon status={f.status} />
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7 text-muted-foreground hover:text-destructive"
                  onClick={() => deleteMutation.mutate(f.id)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
