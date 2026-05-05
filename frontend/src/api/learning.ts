/**
 * API functions for the learning-tool features:
 * dashboard alerts, classes, study content generation.
 */

const API_BASE = '/api';

// ------------------------------------------------------------------
// Shared types
// ------------------------------------------------------------------

export type Urgency = 'high' | 'medium' | 'low';

// ------------------------------------------------------------------
// Dashboard alerts
// ------------------------------------------------------------------

export interface AlertEntry {
  id: number;
  video_id: number;
  text: string;
  urgency: Urgency;
  extracted_date: string | null;
  dismissed: boolean;
  created_at: string;
}

export interface AlertsResponse {
  alerts: AlertEntry[];
}

export async function getDashboardAlerts(): Promise<AlertsResponse> {
  const res = await fetch(`${API_BASE}/dashboard/alerts`);
  if (!res.ok) throw new Error('Failed to fetch alerts');
  return res.json();
}

export async function dismissAlert(videoId: number, itemId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/classes/${videoId}/action-items/${itemId}/dismiss`, {
    method: 'PATCH',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to dismiss alert');
  }
}

// ------------------------------------------------------------------
// Videos by collection
// ------------------------------------------------------------------

export interface VideoEntry {
  id: number;
  source_path: string;
  output_title: string;
  output_path: string | null;
  language: string | null;
  processed_at: string;
}

export async function getVideosByCollection(collectionId: number): Promise<VideoEntry[]> {
  const res = await fetch(`${API_BASE}/videos?collection_id=${collectionId}`);
  if (!res.ok) throw new Error('Failed to fetch videos');
  return res.json();
}

export async function getVideoById(videoId: number): Promise<VideoEntry> {
  const res = await fetch(`${API_BASE}/videos/${videoId}`);
  if (!res.ok) throw new Error('Failed to fetch video');
  return res.json();
}

// ------------------------------------------------------------------
// Study content
// ------------------------------------------------------------------

export interface SummaryResponse {
  text: string;
  generated_at: string;
}

export interface QAPair {
  question: string;
  answer: string;
}

export interface QAResponse {
  pairs: QAPair[];
}

export interface Flashcard {
  concept: string;
  definition: string;
}

export interface FlashcardsResponse {
  cards: Flashcard[];
}

export interface ActionItem {
  id: number;
  text: string;
  urgency: Urgency;
  extracted_date: string | null;
  dismissed: boolean;
}

export interface ActionItemsResponse {
  items: ActionItem[];
}

export async function getSummary(videoId: number): Promise<SummaryResponse> {
  const res = await fetch(`${API_BASE}/classes/${videoId}/summary`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'No summary found');
  }
  return res.json();
}

export async function getQA(videoId: number): Promise<QAResponse> {
  const res = await fetch(`${API_BASE}/classes/${videoId}/qa`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'No Q&A found');
  }
  return res.json();
}

export async function getFlashcards(videoId: number): Promise<FlashcardsResponse> {
  const res = await fetch(`${API_BASE}/classes/${videoId}/flashcards`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'No flashcards found');
  }
  return res.json();
}

export async function getActionItems(videoId: number): Promise<ActionItemsResponse> {
  const res = await fetch(`${API_BASE}/classes/${videoId}/action-items`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'No action items found');
  }
  return res.json();
}

export async function dismissActionItem(videoId: number, itemId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/classes/${videoId}/action-items/${itemId}/dismiss`, {
    method: 'PATCH',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to dismiss action item');
  }
}

// ------------------------------------------------------------------
// Generation SSE
// ------------------------------------------------------------------

export type GenerationStep = 'summary' | 'qa' | 'flashcards' | 'action_items';

export type GenerationEvent =
  | { type: 'progress'; step: GenerationStep; status: 'done' }
  | { type: 'complete' }
  | { type: 'error'; message: string };

/**
 * Start content generation for a video, streaming SSE progress events.
 * Returns a cancel function.
 */
export function startGeneration(
  videoId: number,
  onEvent: (event: GenerationEvent) => void,
  onError?: (err: Error) => void
): () => void {
  let cancelled = false;
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/classes/${videoId}/generate`, {
        method: 'POST',
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || 'Generation failed');
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
            const payload = JSON.parse(dataLine.slice(5).trim()) as GenerationEvent;
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
// Upload + Transcription
// ------------------------------------------------------------------

export interface UploadedFile {
  id: string;
  name: string;
  size_bytes: number;
}

export type Engine = 'deepgram' | 'whisper_local';
export type WhisperModelName = 'small' | 'medium' | 'large-v3';

export async function uploadFile(file: File): Promise<UploadedFile> {
  const form = new FormData();
  form.append('files', file);
  const res = await fetch(`${API_BASE}/files/upload`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Upload failed');
  }
  const data = (await res.json()) as { files: UploadedFile[] };
  return data.files[0];
}

export interface StartTranscriptionPayload {
  fileId: string;
  language: string;
  engine: Engine;
  whisperModel?: WhisperModelName;
  collectionId?: number;
  className: string;
}

export interface TranscriptionStartResponse {
  session_id: string;
  video_id?: number;
}

export async function startLearningTranscription(
  payload: StartTranscriptionPayload
): Promise<TranscriptionStartResponse> {
  const body = {
    files: [
      {
        id: payload.fileId,
        language: payload.language,
        engine: payload.engine,
        whisper_model: payload.whisperModel,
        output_title: payload.className,
      },
    ],
    collection_id: payload.collectionId ?? null,
  };
  const res = await fetch(`${API_BASE}/transcription/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to start transcription');
  }
  return res.json();
}

export type TranscriptionEvent =
  | { type: 'job_status'; job: { path: string; status: string; progress: number; error: string; video_id?: number } }
  | { type: 'log'; message: string; level: string }
  | { type: 'progress'; steps: number }
  | { type: 'status_label'; label: string }
  | { type: 'done'; video_id?: number }
  | { type: 'error'; message: string }
  | { type: 'ping' };

export function subscribeToTranscriptionProgress(
  sessionId: string,
  onEvent: (event: TranscriptionEvent) => void,
  onError?: (err: Error) => void
): () => void {
  const es = new EventSource(`${API_BASE}/transcription/progress/${sessionId}`);

  es.onmessage = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as TranscriptionEvent;
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
