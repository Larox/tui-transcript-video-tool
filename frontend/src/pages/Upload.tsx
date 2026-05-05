import { useQuery } from '@tanstack/react-query';
import { useState, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Loader2, Upload as UploadIcon } from 'lucide-react';
import { getCollections, type CollectionEntry } from '@/api/client';
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

interface ProgressState {
  label: string;
  percent: number;
  done: boolean;
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

// ------------------------------------------------------------------
// Step 1: File Drop
// ------------------------------------------------------------------

function FilePicker({
  onFile,
}: {
  onFile: (f: File) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (!ALLOWED_EXTENSIONS.test(f.name)) {
      alert('Formato no soportado. Usa mp4, mkv, mov, avi, webm, m4a, mp3, wav, ogg, flac');
      return;
    }
    onFile(f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
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
        accept=".mp4,.mkv,.mov,.avi,.webm,.m4a,.mp3,.wav,.ogg,.flac"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
        }}
      />
      <UploadIcon className="mx-auto size-12 text-muted-foreground/40 mb-4" />
      <p className="text-base font-medium">Suelta tu video o audio aquí</p>
      <p className="text-sm text-muted-foreground mt-1">
        o haz click para buscar
      </p>
      <p className="text-xs text-muted-foreground mt-3">
        mp4, mkv, mov, avi, webm, m4a, mp3, wav, ogg, flac
      </p>
    </div>
  );
}

// ------------------------------------------------------------------
// Progress display
// ------------------------------------------------------------------

type ProgressStep = {
  key: string;
  label: string;
};

const UPLOAD_STEPS: ProgressStep[] = [
  { key: 'upload', label: 'Subiendo archivo' },
  { key: 'transcription', label: 'Transcribiendo' },
  { key: 'summary', label: 'Generando resumen' },
  { key: 'qa', label: 'Generando Q&A' },
  { key: 'flashcards', label: 'Generando flashcards' },
  { key: 'action_items', label: 'Detectando tareas' },
];

function ProgressView({ progress }: { progress: ProgressState }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        {progress.done ? (
          <CheckCircle2 className="size-4 text-green-500" />
        ) : (
          <Loader2 className="size-4 animate-spin text-primary" />
        )}
        {progress.label}
      </div>
      <div className="w-full bg-muted rounded-full h-2">
        <div
          className="bg-primary h-2 rounded-full transition-all duration-500"
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      {progress.error && (
        <p className="text-sm text-destructive">{progress.error}</p>
      )}
    </div>
  );
}

// ------------------------------------------------------------------
// Main page
// ------------------------------------------------------------------

export function Upload() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedCourseId = searchParams.get('courseId');

  const { data: collections = [] } = useQuery({
    queryKey: ['collections'],
    queryFn: getCollections,
  });

  const [step, setStep] = useState<Step>('file');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [className, setClassName] = useState('');
  const [courseId, setCourseId] = useState<string>(preselectedCourseId ?? '');
  const [language, setLanguage] = useState<string>('es');
  const [engine, setEngine] = useState<Engine>('deepgram');
  const [progress, setProgress] = useState<ProgressState>({
    label: 'Iniciando...',
    percent: 0,
    done: false,
    error: null,
  });

  const handleFileSelected = (f: File) => {
    setSelectedFile(f);
    // Auto-fill class name from filename
    const nameParts = f.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ');
    setClassName(nameParts);
    setStep('details');
  };

  const handleStart = async () => {
    if (!selectedFile || !className.trim()) return;
    setStep('processing');

    try {
      // Step 1: Upload
      setProgress({ label: 'Subiendo archivo...', percent: 5, done: false, error: null });
      const uploaded = await uploadFile(selectedFile);
      setProgress({ label: 'Archivo subido', percent: 15, done: false, error: null });

      // Step 2: Start transcription
      setProgress({ label: 'Iniciando transcripción...', percent: 20, done: false, error: null });
      const { session_id } = await startLearningTranscription({
        fileId: uploaded.id,
        language,
        engine,
        collectionId: courseId ? Number(courseId) : undefined,
        className: className.trim(),
      });

      // Step 3: Listen to SSE progress
      let resolvedVideoId: number | null = null;

      await new Promise<void>((resolve, reject) => {
        const cancel = subscribeToTranscriptionProgress(
          session_id,
          (event: TranscriptionEvent) => {
            if (event.type === 'status_label') {
              setProgress((p) => ({ ...p, label: event.label, percent: Math.min(p.percent + 10, 80) }));
            } else if (event.type === 'progress') {
              setProgress((p) => ({
                ...p,
                percent: Math.min(p.percent + 5, 85),
              }));
            } else if (event.type === 'job_status') {
              if (event.job.video_id) {
                resolvedVideoId = event.job.video_id;
              }
              if (event.job.status === 'done') {
                setProgress({ label: 'Transcripción completa', percent: 90, done: false, error: null });
              } else if (event.job.status === 'error') {
                cancel();
                reject(new Error(event.job.error || 'Transcription failed'));
              }
            } else if (event.type === 'done') {
              cancel();
              setProgress({ label: '¡Listo!', percent: 100, done: true, error: null });
              resolve();
            } else if (event.type === 'error') {
              cancel();
              reject(new Error(event.message));
            }
          },
          (err) => {
            reject(err);
          }
        );
      });

      // Navigate to the class detail if we have a video_id
      if (resolvedVideoId) {
        navigate(`/classes/${resolvedVideoId}`);
      } else {
        // Fall back to courses
        navigate(courseId ? `/courses/${courseId}` : '/courses');
      }
    } catch (e) {
      setProgress((p) => ({
        ...p,
        done: false,
        error: (e as Error).message,
      }));
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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
          {step === 'details' ? 'Cambiar archivo' : 'Volver'}
        </button>
        <h1 className="text-2xl font-bold">Subir Clase</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Sube un video o audio para transcribir y generar material de estudio
        </p>
      </div>

      {/* Step indicator */}
      {step !== 'processing' && (
        <div className="flex items-center gap-2 text-sm">
          <span className={`font-medium ${step === 'file' ? 'text-foreground' : 'text-muted-foreground'}`}>
            1. Archivo
          </span>
          <ChevronRightIcon />
          <span className={`font-medium ${step === 'details' ? 'text-foreground' : 'text-muted-foreground'}`}>
            2. Detalles
          </span>
        </div>
      )}

      {/* Step 1: File picker */}
      {step === 'file' && <FilePicker onFile={handleFileSelected} />}

      {/* Step 2: Details */}
      {step === 'details' && selectedFile && (
        <div className="space-y-4 max-w-lg">
          {/* Selected file */}
          <Card className="py-3">
            <CardContent className="px-4 flex items-center gap-3">
              <UploadIcon className="size-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{selectedFile.name}</p>
                <p className="text-xs text-muted-foreground">{formatSize(selectedFile.size)}</p>
              </div>
            </CardContent>
          </Card>

          {/* Form */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Detalles de la clase</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="class-name">Nombre de la clase</Label>
                <Input
                  id="class-name"
                  placeholder="e.g. Clase 3 — Límites"
                  value={className}
                  onChange={(e) => setClassName(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="course-select">Materia (opcional)</Label>
                <Select value={courseId} onValueChange={setCourseId}>
                  <SelectTrigger id="course-select">
                    <SelectValue placeholder="Sin materia" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Sin materia</SelectItem>
                    {collections.map((c: CollectionEntry) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
            disabled={!className.trim()}
            size="lg"
            className="w-full"
          >
            <UploadIcon className="size-4 mr-2" />
            Comenzar Transcripción
          </Button>
        </div>
      )}

      {/* Step 3: Processing */}
      {step === 'processing' && (
        <div className="max-w-lg space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Procesando "{className}"</CardTitle>
            </CardHeader>
            <CardContent>
              <ProgressView progress={progress} />
              {progress.error && (
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => setStep('details')}
                >
                  Volver a intentar
                </Button>
              )}
              {progress.done && (
                <p className="text-sm text-muted-foreground mt-3">
                  Redirigiendo a la clase...
                </p>
              )}
            </CardContent>
          </Card>

          {/* Progress steps */}
          <div className="space-y-2">
            {UPLOAD_STEPS.map(({ key, label }, idx) => {
              const stepPercent = ((idx + 1) / UPLOAD_STEPS.length) * 100;
              const done = progress.percent >= stepPercent;
              const active = !done && progress.percent >= ((idx) / UPLOAD_STEPS.length) * 100;
              return (
                <div key={key} className="flex items-center gap-2 text-sm">
                  {done ? (
                    <CheckCircle2 className="size-4 text-green-500 shrink-0" />
                  ) : active ? (
                    <Loader2 className="size-4 animate-spin text-primary shrink-0" />
                  ) : (
                    <div className="size-4 rounded-full border-2 border-muted shrink-0" />
                  )}
                  <span
                    className={
                      done
                        ? 'text-muted-foreground line-through'
                        : active
                        ? 'text-foreground font-medium'
                        : 'text-muted-foreground'
                    }
                  >
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function ChevronRightIcon() {
  return <span className="text-muted-foreground/50">›</span>;
}
