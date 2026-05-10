const API_BASE = '/api';

export interface MateriaFileEntry {
  id: number;
  collection_id: number;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: 'pending' | 'extracting' | 'embedding' | 'indexed' | 'error';
  error_message: string | null;
  uploaded_at: string;
  indexed_at: string | null;
}

export interface RagSearchHit {
  text: string;
  score: number;
  collection_id: number;
  collection_name: string;
  source_type: 'pdf' | 'transcript';
  source_label: string;
  source_id: string;
  page_number: number | null;
  chunk_index: number;
}

export async function listMateriaFiles(collectionId: number): Promise<MateriaFileEntry[]> {
  const res = await fetch(`${API_BASE}/materias/${collectionId}/files`);
  if (!res.ok) throw new Error('Failed to list files');
  return res.json();
}

export async function uploadMateriaFile(
  collectionId: number,
  file: File,
): Promise<MateriaFileEntry> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/materias/${collectionId}/files`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Upload failed');
  }
  return res.json();
}

export async function deleteMateriaFile(
  collectionId: number,
  fileId: number,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/materias/${collectionId}/files/${fileId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error('Delete failed');
}

export async function reindexMateria(collectionId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/materias/${collectionId}/reindex`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Reindex failed');
}

export async function ragSearch(
  query: string,
  collectionId?: number,
  k: number = 8,
): Promise<RagSearchHit[]> {
  const res = await fetch(`${API_BASE}/rag/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, collection_id: collectionId ?? null, k }),
  });
  if (!res.ok) throw new Error('Search failed');
  return res.json();
}
