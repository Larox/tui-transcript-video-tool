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

// ------------------------------------------------------------------
// Document storage
// ------------------------------------------------------------------

export interface DirectoryEntry {
  id: number;
  name: string;
  path: string;
  exists: boolean;
  file_count: number;
  created_at: string;
}

export interface DocumentFile {
  name: string;
  size_bytes: number;
  modified_at: string;
}

export async function getDirectories(): Promise<DirectoryEntry[]> {
  const res = await fetch(`${API_BASE}/documents/directories`);
  if (!res.ok) throw new Error('Failed to fetch directories');
  return res.json();
}

export async function createDirectory(
  name: string,
  path: string
): Promise<DirectoryEntry> {
  const res = await fetch(`${API_BASE}/documents/directories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, path }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to register directory');
  }
  return res.json();
}

export async function updateDirectory(
  id: number,
  path: string
): Promise<DirectoryEntry> {
  const res = await fetch(`${API_BASE}/documents/directories/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update directory');
  }
  return res.json();
}

export async function deleteDirectory(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/directories/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete directory');
  }
}

export async function getDirectoryFiles(id: number): Promise<DocumentFile[]> {
  const res = await fetch(`${API_BASE}/documents/directories/${id}/files`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch files');
  }
  return res.json();
}

export async function openDirectory(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/directories/${id}/open`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to open directory');
  }
}

// ------------------------------------------------------------------
// Native OS directory picker
// ------------------------------------------------------------------

export async function pickDirectory(): Promise<string | null> {
  const res = await fetch(`${API_BASE}/paths/pick-directory`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to open directory picker');
  }
  const data = await res.json();
  return data.path ?? null;
}

// ------------------------------------------------------------------
// Filesystem browsing
// ------------------------------------------------------------------

export interface BrowseEntry {
  name: string;
  path: string;
  has_children: boolean;
}

export interface BrowseResponse {
  current: string;
  parent: string | null;
  children: BrowseEntry[];
}

export async function browseDirectory(path?: string): Promise<BrowseResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : '';
  const res = await fetch(`${API_BASE}/paths/browse${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to browse directory');
  }
  return res.json();
}

// ------------------------------------------------------------------
// SSE / Transcription progress
// ------------------------------------------------------------------

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
