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
} from '../api/client';
import './Dashboard.css';

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
    <div className="dashboard">
      <h2>Transcribe</h2>
      <p className="dashboard-desc">
        Output: {config?.output_mode === 'google_docs' ? 'Google Docs' : 'Local Markdown'}
      </p>

      <div
        className={`dropzone ${dragOver ? 'drag-over' : ''} ${uploading ? 'uploading' : ''}`}
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
          style={{ display: 'none' }}
        />
        {uploading ? 'Uploading...' : 'Drop files here or click to browse'}
      </div>

      {files.length > 0 && (
        <div className="file-list">
          <h3>Files ({files.length})</h3>
          {files.map((f) => (
            <div key={f.id} className="file-row">
              <span className="file-name">{f.name}</span>
              <span className="file-size">{formatSize(f.size_bytes)}</span>
              <select
                value={f.language}
                onChange={(e) => setFileLanguage(f.id, e.target.value)}
                disabled={processing}
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </select>
              <span className="file-status">
                {Object.values(jobs).find((j) => j.path.endsWith(f.name))?.status ?? 'pending'}
              </span>
              {!processing && (
                <button
                  type="button"
                  className="btn-remove"
                  onClick={() => removeFile(f.id)}
                >
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="actions">
        <button
          className="btn-primary"
          onClick={start}
          disabled={!files.length || processing}
        >
          {processing ? 'Processing...' : 'Start'}
        </button>
        <button
          className="btn-secondary"
          onClick={clear}
          disabled={processing}
        >
          Clear
        </button>
      </div>

      {statusLabel && (
        <p className="status-label">{statusLabel}</p>
      )}

      {logs.length > 0 && (
        <div className="log-panel">
          <h3>Logs</h3>
          <div className="log-content">
            {logs.map((msg, i) => (
              <div key={i} className="log-line">
                {msg}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
