import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Loader2, Trash2, Download, Check } from 'lucide-react';
import {
  listLocalModels,
  deleteLocalModel,
  subscribeToModelDownload,
  type LocalModelInfo,
  type WhisperModelName,
} from '@/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function LocalModelsPanel() {
  const queryClient = useQueryClient();
  const { data: models = [], isLoading } = useQuery<LocalModelInfo[]>({
    queryKey: ['local-models'],
    queryFn: listLocalModels,
  });
  const [progress, setProgress] = useState<Record<string, number>>({});

  const formatSize = (mb: number) =>
    mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;

  const startDownload = (name: WhisperModelName) => {
    setProgress((p) => ({ ...p, [name]: 0 }));
    subscribeToModelDownload(
      name,
      (event) => {
        if (event.type === 'progress') {
          setProgress((p) => ({ ...p, [name]: event.progress }));
        } else if (event.type === 'done') {
          setProgress((p) => {
            const next = { ...p };
            delete next[name];
            return next;
          });
          queryClient.invalidateQueries({ queryKey: ['local-models'] });
        } else if (event.type === 'error') {
          alert(`Download failed: ${event.message}`);
          setProgress((p) => {
            const next = { ...p };
            delete next[name];
            return next;
          });
        }
      },
      (err) => {
        alert(err.message);
        setProgress((p) => {
          const next = { ...p };
          delete next[name];
          return next;
        });
      }
    );
  };

  const remove = async (name: WhisperModelName) => {
    if (!confirm(`Remove ${name} model from local cache?`)) return;
    try {
      await deleteLocalModel(name);
      queryClient.invalidateQueries({ queryKey: ['local-models'] });
    } catch (e) {
      alert((e as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Local Whisper models</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {models.map((m) => {
          const inflight = progress[m.name];
          return (
            <div
              key={m.name}
              className="flex items-center gap-3 rounded-md border bg-card p-3 text-sm"
            >
              <span className="flex-1 font-medium">{m.name}</span>
              <span className="text-muted-foreground shrink-0">
                {formatSize(m.size_mb)}
              </span>
              {m.downloaded ? (
                <>
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <Check className="size-3.5" /> Downloaded
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(m.name)}
                    title="Remove model"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </>
              ) : inflight !== undefined ? (
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  Downloading {inflight}%
                </span>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startDownload(m.name)}
                >
                  <Download className="size-4 mr-1.5" />
                  Download
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
