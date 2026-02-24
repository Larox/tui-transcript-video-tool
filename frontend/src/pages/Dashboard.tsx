import { useQuery } from '@tanstack/react-query';
import { useState, useCallback, useRef } from 'react';
import {
  getConfig,
  uploadFiles,
  startTranscription,
  subscribeToProgress,
  type UploadedFile,
  type FileSpec,
  type SSEEvent,
  type JobStatus,
} from '@/api/client';
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
        () => setProcessing(false)
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

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Transcribe</h2>
        <p className="text-sm text-muted-foreground">
          Output: {config?.output_mode === 'google_docs' ? 'Google Docs' : 'Local Markdown'}
        </p>
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

      {files.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Files ({files.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {files.map((f) => (
              <div
                key={f.id}
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
                <span className="text-xs text-muted-foreground capitalize shrink-0 w-24">
                  {Object.values(jobs).find((j) => j.path.endsWith(f.name))?.status ?? 'pending'}
                </span>
                {!processing && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-destructive shrink-0"
                    onClick={() => removeFile(f.id)}
                  >
                    Remove
                  </Button>
                )}
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

      {logs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Logs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[200px] overflow-y-auto rounded-md border bg-muted/30 p-3 font-mono text-xs text-muted-foreground space-y-1">
              {logs.map((msg, i) => (
                <div key={i} className="break-all">
                  {msg}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
