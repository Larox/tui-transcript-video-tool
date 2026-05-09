import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Loader2, Plus, Upload as UploadIcon, X } from 'lucide-react';
import { getCollections, createCollection, type CollectionEntry } from '@/api/client';
import {
  uploadFile,
  startLearningTranscription,
  subscribeToTranscriptionProgress,
  type Engine,
  type TranscriptionEvent,
} from '@/api/learning';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

type Step = 'file' | 'details' | 'processing';

interface PendingFile {
  uid: string;
  file: File;
  className: string;
}

type FileStatus = 'pending' | 'uploading' | 'transcribing' | 'done' | 'error';

interface FileProgress {
  status: FileStatus;
  label: string;
  percent: number;
  videoId: number | null;
  error: string | null;
}

const ALLOWED_EXTENSIONS = /\.(mp4|mkv|mov|avi|webm|m4a|mp3|wav|ogg|flac)$/i;

const LANGUAGES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'Inglés' },
  { code: 'multi', label: 'Multilingüe' },
  { code: 'fr', label: 'Francés' },
  { code: 'pt', label: 'Portugués' },
  { code: 'de', label: 'Alemán' },
] as const;

function deriveClassName(filename: string): string {
  return filename.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ').trim();
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ------------------------------------------------------------------
// Step 1: File Drop (multi-select)
// ------------------------------------------------------------------

function FilePicker({
  onFiles,
}: {
  onFiles: (files: File[]) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (list: FileList | File[]) => {
    const files = Array.from(list);
    const valid: File[] = [];
    const invalid: string[] = [];
    for (const f of files) {
      if (ALLOWED_EXTENSIONS.test(f.name)) valid.push(f);
      else invalid.push(f.name);
    }
    if (invalid.length > 0) {
      alert(
        `Formato no soportado: ${invalid.join(', ')}\n` +
          'Usa mp4, mkv, mov, avi, webm, m4a, mp3, wav, ogg, flac',
      );
    }
    if (valid.length > 0) onFiles(valid);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-16 text-center cursor-pointer transition-colors ${
        dragOver
          ? 'border-primary bg-primary/5'
          : 'border-muted-foreground/30 hover:border-primary/50'
      }`}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={() => setDragOver(false)}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".mp4,.mkv,.mov,.avi,.webm,.m4a,.mp3,.wav,.ogg,.flac"
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) handleFiles(e.target.files);
          e.target.value = '';
        }}
      />
      <UploadIcon className="mx-auto size-12 text-muted-foreground/40 mb-4" />
      <p className="text-base font-medium">Suelta tus videos o audios aquí</p>
      <p className="text-sm text-muted-foreground mt-1">
        Puedes seleccionar varios archivos a la vez
      </p>
      <p className="text-xs text-muted-foreground mt-3">
        mp4, mkv, mov, avi, webm, m4a, mp3, wav, ogg, flac
      </p>
    </div>
  );
}

// ------------------------------------------------------------------
// Step 3: per-file progress card
// ------------------------------------------------------------------
// Course combobox with search + create
// ------------------------------------------------------------------

function CourseCombobox({
  collections,
  value,
  onChange,
}: {
  collections: CollectionEntry[];
  value: string;
  onChange: (id: string, newCollection?: CollectionEntry) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const selected = value && value !== 'none'
    ? collections.find((c) => String(c.id) === value)
    : null;

  const filtered = query.trim()
    ? collections.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))
    : collections;

  const exactMatch = collections.some(
    (c) => c.name.toLowerCase() === query.toLowerCase().trim()
  );

  const handleCreate = async () => {
    const name = query.trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await createCollection({ name, collection_type: 'course' });
      onChange(String(created.id), created);
      setOpen(false);
      setQuery('');
    } catch {
      // ignore
    } finally {
      setCreating(false);
    }
  };

  const itemClass =
    'w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground cursor-pointer truncate';

  return (
    <div ref={ref} className="relative">
      <Input
        value={open ? query : (selected?.name ?? '')}
        placeholder="Buscar o crear materia..."
        onFocus={() => { setOpen(true); setQuery(''); }}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false);
          if (e.key === 'Enter' && query.trim() && !exactMatch) handleCreate();
        }}
      />
      {open && (
        <div className="absolute z-50 w-full mt-1 rounded-md border bg-popover text-popover-foreground shadow-md max-h-52 overflow-auto">
          <button type="button" className={itemClass} onClick={() => { onChange('none'); setOpen(false); setQuery(''); }}>
            Sin materia
          </button>
          {filtered.map((c) => (
            <button
              type="button"
              key={c.id}
              className={`${itemClass}${String(c.id) === value ? ' font-medium text-primary' : ''}`}
              onClick={() => { onChange(String(c.id)); setOpen(false); setQuery(''); }}
            >
              {c.name}
            </button>
          ))}
          {query.trim() && !exactMatch && (
            <button
              type="button"
              className={`${itemClass} text-primary flex items-center gap-1.5`}
              onClick={handleCreate}
              disabled={creating}
            >
              {creating
                ? <Loader2 className="size-3.5 animate-spin" />
                : <Plus className="size-3.5" />}
              Crear "{query.trim()}"
            </button>
          )}
          {filtered.length === 0 && !query.trim() && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No hay materias. Escribe para crear una.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------

function FileProgressCard({
  pending,
  progress,
  onOpen,
}: {
  pending: PendingFile;
  progress: FileProgress;
  onOpen: (videoId: number) => void;
}) {
  const icon =
    progress.status === 'done' ? (
      <CheckCircle2 className="size-4 text-green-500 shrink-0" />
    ) : progress.status === 'error' ? (
      <X className="size-4 text-destructive shrink-0" />
    ) : progress.status === 'pending' ? (
      <div className="size-4 rounded-full border-2 border-muted shrink-0" />
    ) : (
      <Loader2 className="size-4 animate-spin text-primary shrink-0" />
    );

  return (
    <Card className="py-3">
      <CardContent className="px-4 space-y-2">
        <div className="flex items-center gap-2">
          {icon}
          <p className="text-sm font-medium truncate flex-1">{pending.className}</p>
          <span className="text-xs text-muted-foreground shrink-0">
            {formatSize(pending.file.size)}
          </span>
        </div>
        <div className="w-full bg-muted rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full transition-all duration-500 ${
              progress.status === 'error' ? 'bg-destructive' : 'bg-primary'
            }`}
            style={{ width: `${progress.percent}%` }}
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">{progress.label}</p>
          {progress.status === 'done' && progress.videoId !== null && (
            <button
              type="button"
              onClick={() => onOpen(progress.videoId!)}
              className="text-xs text-primary hover:underline shrink-0"
            >
              Abrir clase
            </button>
          )}
        </div>
        {progress.error && (
          <p className="text-xs text-destructive">{progress.error}</p>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------
// Main page
// ------------------------------------------------------------------

export function Upload() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const preselectedCourseId = searchParams.get('courseId');

  const { data: fetchedCollections = [] } = useQuery({
    queryKey: ['collections'],
    queryFn: getCollections,
  });
  const [extraCollections, setExtraCollections] = useState<CollectionEntry[]>([]);
  const collections = [...fetchedCollections, ...extraCollections.filter(
    (e) => !fetchedCollections.some((f) => f.id === e.id)
  )];

  const [step, setStep] = useState<Step>('file');
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [courseId, setCourseId] = useState<string>(preselectedCourseId ?? '');
  const [language, setLanguage] = useState<string>('es');
  const [engine, setEngine] = useState<Engine>('deepgram');
  const [progressByUid, setProgressByUid] = useState<Record<string, FileProgress>>({});
  const [batchDone, setBatchDone] = useState(false);

  const handleFilesSelected = (files: File[]) => {
    const next: PendingFile[] = files.map((f, i) => ({
      uid: `${Date.now()}-${i}-${f.name}`,
      file: f,
      className: deriveClassName(f.name),
    }));
    setPendingFiles(next);
    setStep('details');
  };

  const addMoreFiles = (files: File[]) => {
    const next: PendingFile[] = files.map((f, i) => ({
      uid: `${Date.now()}-${i}-${f.name}`,
      file: f,
      className: deriveClassName(f.name),
    }));
    setPendingFiles((prev) => [...prev, ...next]);
  };

  const removeFile = (uid: string) => {
    setPendingFiles((prev) => prev.filter((p) => p.uid !== uid));
  };

  const updateClassName = (uid: string, name: string) => {
    setPendingFiles((prev) =>
      prev.map((p) => (p.uid === uid ? { ...p, className: name } : p)),
    );
  };

  const updateProgress = (uid: string, patch: Partial<FileProgress>) => {
    setProgressByUid((prev) => ({
      ...prev,
      [uid]: { ...prev[uid], ...patch },
    }));
  };

  const processFile = async (pending: PendingFile): Promise<void> => {
    updateProgress(pending.uid, {
      status: 'uploading',
      label: 'Subiendo archivo...',
      percent: 5,
      error: null,
    });

    try {
      const uploaded = await uploadFile(pending.file);
      updateProgress(pending.uid, {
        status: 'transcribing',
        label: 'Iniciando transcripción...',
        percent: 20,
      });

      const { session_id } = await startLearningTranscription({
        fileId: uploaded.id,
        language,
        engine,
        collectionId: courseId && courseId !== 'none' ? Number(courseId) : undefined,
        className: pending.className.trim() || pending.file.name,
      });

      let resolvedVideoId: number | null = null;

      await new Promise<void>((resolve, reject) => {
        const cancel = subscribeToTranscriptionProgress(
          session_id,
          (event: TranscriptionEvent) => {
            if (event.type === 'status_label') {
              updateProgress(pending.uid, {
                label: event.label,
                percent: Math.min((progressByUid[pending.uid]?.percent ?? 20) + 10, 80),
              });
            } else if (event.type === 'progress') {
              setProgressByUid((prev) => {
                const cur = prev[pending.uid];
                return {
                  ...prev,
                  [pending.uid]: { ...cur, percent: Math.min(cur.percent + 5, 85) },
                };
              });
            } else if (event.type === 'job_status') {
              if (event.job.video_id) resolvedVideoId = event.job.video_id;
              if (event.job.status === 'done') {
                updateProgress(pending.uid, {
                  label: 'Transcripción completa',
                  percent: 90,
                });
              } else if (event.job.status === 'error') {
                cancel();
                reject(new Error(event.job.error || 'Transcription failed'));
              }
            } else if (event.type === 'done') {
              cancel();
              resolve();
            } else if (event.type === 'error') {
              cancel();
              reject(new Error(event.message));
            }
          },
          (err) => reject(err),
        );
      });

      updateProgress(pending.uid, {
        status: 'done',
        label: '¡Listo!',
        percent: 100,
        videoId: resolvedVideoId,
      });
    } catch (e) {
      updateProgress(pending.uid, {
        status: 'error',
        label: 'Error',
        error: (e as Error).message,
      });
      throw e;
    }
  };

  const handleStart = async () => {
    if (pendingFiles.length === 0) return;
    if (pendingFiles.some((p) => !p.className.trim())) return;
    setStep('processing');
    setBatchDone(false);

    const initial: Record<string, FileProgress> = {};
    for (const p of pendingFiles) {
      initial[p.uid] = {
        status: 'pending',
        label: 'En cola',
        percent: 0,
        videoId: null,
        error: null,
      };
    }
    setProgressByUid(initial);

    for (const pending of pendingFiles) {
      try {
        await processFile(pending);
      } catch {
        // Already recorded on the file's progress; continue with the rest.
      }
    }

    setBatchDone(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <button
          type="button"
          onClick={() => {
            if (step === 'details') setStep('file');
            else navigate(-1);
          }}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3"
        >
          <ArrowLeft className="size-4" />
          {step === 'details' ? 'Cambiar archivos' : 'Volver'}
        </button>
        <h1 className="text-2xl font-bold">Subir Clases</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Sube uno o varios videos o audios para transcribir y generar material de estudio
        </p>
      </div>

      {/* Step indicator */}
      {step !== 'processing' && (
        <div className="flex items-center gap-2 text-sm">
          <span className={`font-medium ${step === 'file' ? 'text-foreground' : 'text-muted-foreground'}`}>
            1. Archivos
          </span>
          <ChevronRightIcon />
          <span className={`font-medium ${step === 'details' ? 'text-foreground' : 'text-muted-foreground'}`}>
            2. Detalles
          </span>
        </div>
      )}

      {/* Step 1: File picker */}
      {step === 'file' && <FilePicker onFiles={handleFilesSelected} />}

      {/* Step 2: Details */}
      {step === 'details' && pendingFiles.length > 0 && (
        <div className="space-y-4 max-w-2xl">
          {/* File list with editable names */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-base">
                {pendingFiles.length} archivo{pendingFiles.length !== 1 ? 's' : ''} seleccionado
                {pendingFiles.length !== 1 ? 's' : ''}
              </CardTitle>
              <AddMoreButton onAdd={addMoreFiles} />
            </CardHeader>
            <CardContent className="space-y-3">
              {pendingFiles.map((p) => (
                <div
                  key={p.uid}
                  className="flex items-start gap-2 p-3 rounded-lg border bg-muted/20"
                >
                  <UploadIcon className="size-4 text-muted-foreground shrink-0 mt-2" />
                  <div className="flex-1 min-w-0 space-y-1">
                    <Input
                      value={p.className}
                      onChange={(e) => updateClassName(p.uid, e.target.value)}
                      placeholder="Nombre de la clase"
                      className="h-8 text-sm"
                    />
                    <p className="text-xs text-muted-foreground truncate">
                      {p.file.name} · {formatSize(p.file.size)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => removeFile(p.uid)}
                  >
                    <X className="size-3.5" />
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Shared settings */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Configuración del lote</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="course-select">Materia (opcional)</Label>
                <CourseCombobox
                  collections={collections}
                  value={courseId}
                  onChange={(id, newCollection) => {
                    setCourseId(id);
                    if (newCollection) {
                      setExtraCollections((prev) => [...prev, newCollection]);
                      queryClient.invalidateQueries({ queryKey: ['collections'] });
                    }
                  }}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="lang-select">Idioma</Label>
                  <Select value={language} onValueChange={setLanguage}>
                    <SelectTrigger id="lang-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LANGUAGES.map((l) => (
                        <SelectItem key={l.code} value={l.code}>
                          {l.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="engine-select">Motor</Label>
                  <Select
                    value={engine}
                    onValueChange={(v) => setEngine(v as Engine)}
                  >
                    <SelectTrigger id="engine-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="deepgram">Deepgram</SelectItem>
                      <SelectItem value="whisper_local">Whisper (local)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          <Button
            onClick={handleStart}
            disabled={pendingFiles.some((p) => !p.className.trim())}
            size="lg"
            className="w-full"
          >
            <UploadIcon className="size-4 mr-2" />
            Comenzar Transcripción ({pendingFiles.length})
          </Button>
        </div>
      )}

      {/* Step 3: Processing */}
      {step === 'processing' && (
        <div className="max-w-2xl space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Procesando {pendingFiles.length} clase{pendingFiles.length !== 1 ? 's' : ''}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {pendingFiles.map((p) => (
                <FileProgressCard
                  key={p.uid}
                  pending={p}
                  progress={progressByUid[p.uid] ?? {
                    status: 'pending',
                    label: 'En cola',
                    percent: 0,
                    videoId: null,
                    error: null,
                  }}
                  onOpen={(vid) => navigate(`/classes/${vid}`)}
                />
              ))}
            </CardContent>
          </Card>

          {batchDone && (
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                {Object.values(progressByUid).filter((p) => p.status === 'done').length} de{' '}
                {pendingFiles.length} completadas
              </p>
              <Button
                onClick={() =>
                  navigate(courseId && courseId !== 'none' ? `/courses/${courseId}` : '/courses')
                }
              >
                Ir a Mis Materias
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AddMoreButton({ onAdd }: { onAdd: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".mp4,.mkv,.mov,.avi,.webm,.m4a,.mp3,.wav,.ogg,.flac"
        className="hidden"
        onChange={(e) => {
          const files = e.target.files;
          if (!files || files.length === 0) return;
          const valid = Array.from(files).filter((f) => ALLOWED_EXTENSIONS.test(f.name));
          if (valid.length > 0) onAdd(valid);
          e.target.value = '';
        }}
      />
      <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
        <UploadIcon className="size-3.5 mr-1.5" />
        Añadir más
      </Button>
    </>
  );
}

function ChevronRightIcon() {
  return <span className="text-muted-foreground/50">›</span>;
}
