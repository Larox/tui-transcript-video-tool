const API_BASE = '/api';

export interface Config {
  deepgram_api_key: string;
  naming_mode: string;
  prefix: string;
  anthropic_api_key: string;
}

export interface ConfigUpdate {
  deepgram_api_key?: string;
  naming_mode?: string;
  prefix?: string;
  anthropic_api_key?: string;
}

export interface UploadedFile {
  id: string;
  name: string;
  size_bytes: number;
}

export type Engine = 'deepgram' | 'whisper_local';
export type WhisperModelName = 'small' | 'medium' | 'large-v3';

export interface FileSpec {
  id: string;
  language: string;
  engine?: Engine;
  whisper_model?: WhisperModelName;
}

export interface KeyMoment {
  timestamp: string;
  description: string;
}

export interface HighlightsResponse {
  id: number;
  slug: string;
  moments: KeyMoment[];
}

export interface JobStatus {
  path: string;
  language: string;
  status: string;
  progress: number;
  transcript: string;
  output_path: string;
  error: string;
  key_moments: KeyMoment[];
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
  fileSpecs: FileSpec[],
  directoryId: number
): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/transcription/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: fileSpecs, directory_id: directoryId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start transcription');
  }
  return res.json();
}

export interface TranscriptionStatus {
  status: 'running' | 'done';
  jobs: JobStatus[];
}

export async function getTranscriptionStatus(
  sessionId: string
): Promise<TranscriptionStatus> {
  const res = await fetch(`${API_BASE}/transcription/status/${sessionId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch status');
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
  highlights_id?: number;
  highlights_slug?: string;
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

export async function getHighlights(slug: string): Promise<HighlightsResponse> {
  const res = await fetch(`${API_BASE}/documents/highlights/${encodeURIComponent(slug)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch highlights');
  }
  return res.json();
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
// Collections
// ------------------------------------------------------------------

export interface CollectionEntry {
  id: number;
  name: string;
  collection_type: string;
  description: string;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface CollectionItemEntry {
  id: number;
  source_path: string;
  output_title: string;
  output_path: string | null;
  language: string | null;
  processed_at: string;
  position: number;
  tags: TagEntry[];
}

export interface CollectionDetail extends Omit<CollectionEntry, 'item_count'> {
  items: CollectionItemEntry[];
}

export async function getCollections(): Promise<CollectionEntry[]> {
  const res = await fetch(`${API_BASE}/collections`);
  if (!res.ok) throw new Error('Failed to fetch collections');
  return res.json();
}

export async function getCollection(id: number): Promise<CollectionDetail> {
  const res = await fetch(`${API_BASE}/collections/${id}`);
  if (!res.ok) throw new Error('Failed to fetch collection');
  return res.json();
}

export async function createCollection(data: {
  name: string;
  collection_type: string;
  description?: string;
}): Promise<CollectionEntry> {
  const res = await fetch(`${API_BASE}/collections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create collection');
  }
  return res.json();
}

export async function updateCollection(
  id: number,
  data: { name?: string; collection_type?: string; description?: string }
): Promise<CollectionEntry> {
  const res = await fetch(`${API_BASE}/collections/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update collection');
  }
  return res.json();
}

export async function deleteCollection(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/collections/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete collection');
  }
}

export async function addCollectionItems(
  collectionId: number,
  videoIds: number[]
): Promise<void> {
  const res = await fetch(`${API_BASE}/collections/${collectionId}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_ids: videoIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to add items');
  }
}

export async function removeCollectionItem(
  collectionId: number,
  videoId: number
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/collections/${collectionId}/items/${videoId}`,
    { method: 'DELETE' }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to remove item');
  }
}

// ------------------------------------------------------------------
// Tags
// ------------------------------------------------------------------

export interface TagEntry {
  id: number;
  name: string;
  color: string;
}

export async function getTags(): Promise<TagEntry[]> {
  const res = await fetch(`${API_BASE}/tags`);
  if (!res.ok) throw new Error('Failed to fetch tags');
  return res.json();
}

export async function createTag(
  name: string,
  color: string = '#6b7280'
): Promise<TagEntry> {
  const res = await fetch(`${API_BASE}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create tag');
  }
  return res.json();
}

export async function deleteTag(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/tags/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete tag');
  }
}

export async function addVideoTag(videoId: number, tagId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tag_id: tagId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to add tag');
  }
}

export async function removeVideoTag(videoId: number, tagId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/tags/${tagId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to remove tag');
  }
}

// ------------------------------------------------------------------
// Search & Videos
// ------------------------------------------------------------------

export interface SearchResultEntry {
  video_id: number;
  output_title: string;
  source_path: string;
  excerpt: string;
  rank: number;
}

export interface VideoEntry {
  id: number;
  source_path: string;
  output_title: string;
  output_path: string | null;
  language: string | null;
  processed_at: string;
}

export async function searchTranscripts(
  q: string,
  opts?: { collection_id?: number; tag?: string; limit?: number }
): Promise<SearchResultEntry[]> {
  const params = new URLSearchParams({ q });
  if (opts?.collection_id != null) params.set('collection_id', String(opts.collection_id));
  if (opts?.tag) params.set('tag', opts.tag);
  if (opts?.limit) params.set('limit', String(opts.limit));
  const res = await fetch(`${API_BASE}/search?${params}`);
  if (!res.ok) throw new Error('Search failed');
  return res.json();
}

export async function getVideos(): Promise<VideoEntry[]> {
  const res = await fetch(`${API_BASE}/videos`);
  if (!res.ok) throw new Error('Failed to fetch videos');
  return res.json();
}

export async function getVideoById(id: number): Promise<VideoEntry> {
  const res = await fetch(`${API_BASE}/videos/${id}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to fetch video');
  }
  return res.json();
}

// ------------------------------------------------------------------
// Local Whisper models
// ------------------------------------------------------------------

export interface LocalModelInfo {
  name: WhisperModelName;
  repo_id: string;
  size_mb: number;
  downloaded: boolean;
}

export async function listLocalModels(): Promise<LocalModelInfo[]> {
  const res = await fetch(`${API_BASE}/models/local`);
  if (!res.ok) throw new Error('Failed to list local models');
  return res.json();
}

export async function deleteLocalModel(name: WhisperModelName): Promise<void> {
  const res = await fetch(`${API_BASE}/models/local/${name}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete model');
  }
}

export type ModelDownloadEvent =
  | { type: 'progress'; progress: number }
  | { type: 'done' }
  | { type: 'error'; message: string };

export function subscribeToModelDownload(
  name: WhisperModelName,
  onEvent: (event: ModelDownloadEvent) => void,
  onError?: (err: Error) => void
): () => void {
  let cancelled = false;
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/models/local/${name}/download`, {
        method: 'POST',
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Download failed');
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!cancelled) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';
        for (const block of events) {
          const dataLine = block.split('\n').find((l) => l.startsWith('data:'));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(5).trim());
            onEvent(payload);
          } catch {
            // skip parse errors
          }
        }
      }
    } catch (e) {
      if (!cancelled) onError?.(e as Error);
    }
  })();

  return () => {
    cancelled = true;
    controller.abort();
  };
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
