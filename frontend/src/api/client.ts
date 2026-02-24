const API_BASE = '/api';

export interface Config {
  deepgram_api_key: string;
  google_service_account_json: string;
  drive_folder_id: string;
  naming_mode: string;
  prefix: string;
  markdown_output_dir: string;
  output_mode: string;
}

export interface ConfigUpdate {
  deepgram_api_key?: string;
  google_service_account_json?: string;
  drive_folder_id?: string;
  naming_mode?: string;
  prefix?: string;
  markdown_output_dir?: string;
}

export interface UploadedFile {
  id: string;
  name: string;
  size_bytes: number;
}

export interface FileSpec {
  id: string;
  language: string;
}

export interface JobStatus {
  path: string;
  language: string;
  status: string;
  progress: number;
  transcript: string;
  doc_id: string;
  doc_url: string;
  output_path: string;
  error: string;
}

export async function getConfig(): Promise<Config> {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) throw new Error('Failed to fetch config');
  return res.json();
}

export async function putConfig(update: ConfigUpdate): Promise<void> {
  const res = await fetch(`${API_BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error('Failed to update config');
}

export async function uploadFiles(files: File[]): Promise<UploadedFile[]> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f));

  const res = await fetch(`${API_BASE}/files/upload`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Upload failed');
  }
  const data = await res.json();
  return data.files;
}

export async function startTranscription(
  fileSpecs: FileSpec[]
): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/transcription/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: fileSpecs }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start transcription');
  }
  return res.json();
}

export async function openPath(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}/paths/open`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to open path');
  }
}

export type SSEEvent =
  | { type: 'job_status'; job: JobStatus }
  | { type: 'log'; message: string; level: string }
  | { type: 'progress'; steps: number }
  | { type: 'status_label'; label: string }
  | { type: 'done' }
  | { type: 'error'; message: string }
  | { type: 'ping' };

export function subscribeToProgress(
  sessionId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (err: Error) => void
): () => void {
  const es = new EventSource(`${API_BASE}/transcription/progress/${sessionId}`);

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
      if (data.type === 'done') es.close();
    } catch {
      // ignore parse errors
    }
  };

  es.addEventListener('error', () => {
    onError?.(new Error('Connection lost'));
  });

  return () => es.close();
}
