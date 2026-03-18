import { useQuery } from '@tanstack/react-query';
import { useState, useCallback, useRef } from 'react';
import {
  getConfig,
  uploadFiles,
  startTranscription,
  subscribeToProgress,
  getTranscriptionStatus,
  openPath,
  type UploadedFile,
  type FileSpec,
  type SSEEvent,
  type JobStatus,
  type KeyMoment,
} from '@/api/client';
import { FolderOpen, Loader2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const LANGUAGES = [
  { code: 'es', name: 'Spanish' },
  { code: 'en', name: 'English' },
  { code: 'multi', name: 'Multilingual' },
  { code: 'fr', name: 'French' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'de', name: 'German' },
] as const;

type FileWithLang = UploadedFile & { language: string };

export function Dashboard() {
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig });
  const [files, setFiles] = useState<FileWithLang[]>([]);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [statusLabel, setStatusLabel] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [jobs, setJobs] = useState<Record<string, JobStatus>>({});
  const [expandedMoments, setExpandedMoments] = useState<Record<string, boolean>>({});
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(async (fileList: FileList | null) => {
    if (!fileList?.length) return;
    const valid = Array.from(fileList).filter(
      (f) => /\.(mp4|mkv|mov|avi|webm|m4a|mp3|wav|ogg|flac)$/i.test(f.name)
    );
    if (!valid.length) {
      alert('No valid video/audio files. Supported: mp4, mkv, mov, avi, webm, m4a, mp3, wav, ogg, flac');
      return;
    }
    setUploading(true);
    try {
      const uploaded = await uploadFiles(valid);
      setFiles((prev) => [
        ...prev,
        ...uploaded.map((u) => ({ ...u, language: 'es' })),
      ]);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setUploading(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const onDragLeave = useCallback(() => setDragOver(false), []);

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const setFileLanguage = (id: string, language: string) => {
    setFiles((prev) =>
      prev.map((f) => (f.id === id ? { ...f, language } : f))
    );
  };

  const start = async () => {
    if (!files.length || processing) return;
    if (!config?.deepgram_api_key || config.deepgram_api_key === '***') {
      alert('Configure your Deepgram API key in Settings first.');
      return;
    }
    setProcessing(true);
    setLogs([]);
    setJobs({});
    setStatusLabel('Starting...');
    try {
      const specs: FileSpec[] = files.map((f) => ({ id: f.id, language: f.language }));
      const { session_id } = await startTranscription(specs);

      subscribeToProgress(
        session_id,
        (event: SSEEvent) => {
          if (event.type === 'job_status') {
            setJobs((j) => ({ ...j, [event.job.path]: event.job }));
          } else if (event.type === 'log') {
            setLogs((l) => [...l, event.message]);
          } else if (event.type === 'status_label') {
            setStatusLabel(event.label);
          } else if (event.type === 'done') {
            setProcessing(false);
            setStatusLabel('Done!');
          }
        },
        async () => {
          // On SSE connection loss, poll status to recover state
          for (let attempt = 0; attempt < 5; attempt++) {
            await new Promise((r) => setTimeout(r, 1000));
            try {
              const status = await getTranscriptionStatus(session_id);
              status.jobs.forEach((job) =>
                setJobs((j) => ({ ...j, [job.path]: job }))
              );
              if (status.status === 'done') {
                setStatusLabel('Done!');
                setProcessing(false);
                return;
              }
            } catch {
              // Ignore fetch errors, keep trying
            }
          }
          setProcessing(false);
        }
      );
    } catch (e) {
      alert((e as Error).message);
      setProcessing(false);
    }
  };

  const clear = () => {
    setFiles([]);
    setLogs([]);
    setJobs({});
    setStatusLabel('');
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const showTwoColumn = files.length > 0 || logs.length > 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Transcribe</h2>
        <p className="text-sm text-muted-foreground">Output: Local Markdown</p>
      </div>

      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-primary bg-primary/10' : 'border-muted-foreground/30 hover:border-primary/50'
        } ${uploading ? 'opacity-70 cursor-wait' : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".mp4,.mkv,.mov,.avi,.webm,.m4a,.mp3,.wav,.ogg,.flac"
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />
        <p className="text-muted-foreground">
          {uploading ? 'Uploading...' : 'Drop files here or click to browse'}
        </p>
      </div>

      {showTwoColumn ? (
        <div className="flex flex-col lg:flex-row gap-6 items-stretch lg:items-start">
          <div className="flex-1 min-w-0 space-y-6">
            {files.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Files ({files.length})</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {files.map((f) => (
                    <div key={f.id} className="flex flex-col">
                    <div
                      className="flex items-center gap-4 rounded-md border bg-card p-3 text-sm"
                    >
                      <span className="flex-1 truncate font-medium">{f.name}</span>
                      <span className="text-muted-foreground shrink-0">{formatSize(f.size_bytes)}</span>
                      <Select
                        value={f.language}
                        onValueChange={(v) => setFileLanguage(f.id, v)}
                        disabled={processing}
                      >
                        <SelectTrigger className="w-[140px] h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {LANGUAGES.map((l) => (
                            <SelectItem key={l.code} value={l.code}>
                              {l.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {(() => {
                        const job = Object.values(jobs).find((j) => j.path.endsWith(f.name));
                        const status = job?.status ?? 'pending';
                        const progress = job?.progress ?? 0;
                        const isInProgress = status === 'transcribing' || status === 'uploading';
                        const statusColor = {
                          pending: 'text-yellow-500',
                          transcribing: 'text-yellow-500',
                          uploading: 'text-yellow-500',
                          done: 'text-green-500',
                          error: 'text-red-500',
                        }[status] ?? 'text-muted-foreground';
                        return (
                          <span
                            className={`text-xs capitalize shrink-0 flex items-center gap-2 min-w-32 ${statusColor}`}
                          >
                            {isInProgress && (
                              <Loader2 className="size-3.5 shrink-0 animate-spin" />
                            )}
                            <span>{Math.round(progress * 100)}%</span>
                            <span className="capitalize">{status}</span>
                          </span>
                        );
                      })()}
                      {(() => {
                        const job = Object.values(jobs).find((j) => j.path.endsWith(f.name));
                        if (job?.status === 'done' && job.output_path) {
                          return (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="shrink-0"
                              title="Open in file browser"
                              onClick={async () => {
                                try {
                                  await openPath(job.output_path);
                                } catch (e) {
                                  alert((e as Error).message);
                                }
                              }}
                            >
                              <FolderOpen className="size-4" />
                            </Button>
                          );
                        }
                        if (!processing) {
                          return (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="text-muted-foreground hover:text-destructive shrink-0"
                              onClick={() => removeFile(f.id)}
                            >
                              Remove
                            </Button>
                          );
                        }
                        return null;
                      })()}
                      {(() => {
                        const job = Object.values(jobs).find((j) => j.path.endsWith(f.name));
                        if (job?.status === 'done' && (job?.key_moments?.length ?? 0) > 0) {
                          return (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="shrink-0"
                              title="View key moments"
                              onClick={() =>
                                setExpandedMoments((p) => ({
                                  ...p,
                                  [f.id]: !p[f.id],
                                }))
                              }
                            >
                              <Sparkles className="size-4" />
                            </Button>
                          );
                        }
                        return null;
                      })()}
                    </div>
                    {(() => {
                      const job = Object.values(jobs).find((j) => j.path.endsWith(f.name));
                      if (expandedMoments[f.id] && (job?.key_moments?.length ?? 0) > 0) {
                        return (
                          <div className="mt-1.5 rounded-md border bg-muted/30 p-3 space-y-2">
                            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                              Key Moments
                            </p>
                            {job!.key_moments.map((m: KeyMoment, i: number) => (
                              <div key={i} className="flex gap-2.5 text-sm">
                                <span className="font-mono text-muted-foreground shrink-0">
                                  {m.timestamp}
                                </span>
                                <span>{m.description}</span>
                              </div>
                            ))}
                          </div>
                        );
                      }
                      return null;
                    })()}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <div className="flex gap-3">
              <Button
                onClick={start}
                disabled={!files.length || processing}
              >
                {processing ? 'Processing...' : 'Start'}
              </Button>
              <Button
                variant="outline"
                onClick={clear}
                disabled={processing}
              >
                Clear
              </Button>
            </div>

            {statusLabel && (
              <p className="text-sm text-muted-foreground">{statusLabel}</p>
            )}
          </div>

          <aside className="w-full lg:w-[28rem] lg:min-w-96 shrink-0 lg:sticky lg:top-6 flex flex-col">
            <Card className="flex-1 min-h-0 flex flex-col">
              <CardHeader>
                <CardTitle className="text-base">Logs</CardTitle>
              </CardHeader>
              <CardContent className="flex-1 min-h-0">
                <div className="max-h-[min(70vh,560px)] overflow-y-auto rounded-md border bg-muted/30 p-4 font-mono text-sm text-muted-foreground space-y-1.5">
                  {logs.length > 0 ? (
                    logs.map((msg, i) => (
                      <div key={i} className="break-all">
                        {msg}
                      </div>
                    ))
                  ) : (
                    <p className="text-muted-foreground text-sm">Logs will appear here when processing.</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </aside>
        </div>
      ) : (
        <>
          <div className="flex gap-3">
            <Button onClick={start} disabled={!files.length || processing}>
              {processing ? 'Processing...' : 'Start'}
            </Button>
            <Button variant="outline" onClick={clear} disabled={processing}>
              Clear
            </Button>
          </div>
          {statusLabel && (
            <p className="text-sm text-muted-foreground">{statusLabel}</p>
          )}
        </>
      )}
    </div>
  );
}
