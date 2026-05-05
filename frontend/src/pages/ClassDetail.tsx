import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import { useState, useCallback } from 'react';
import {
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  PenLine,
  RotateCcw,
  Sparkles,
  Zap,
} from 'lucide-react';
import {
  getSummary,
  getQA,
  getFlashcards,
  getActionItems,
  getFillInBlank,
  dismissActionItem,
  startGeneration,
  type Urgency,
  type ActionItem,
  type QAPair,
  type Flashcard,
  type FillInBlankItem,
} from '@/api/learning';
import { getVideoById } from '@/api/client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

const GENERATION_STEPS = ['summary', 'qa', 'flashcards', 'action_items', 'fill_in_blank'] as const;
type GenStep = (typeof GENERATION_STEPS)[number];

const STEP_LABELS: Record<GenStep, string> = {
  summary: 'Resumen',
  qa: 'Preguntas y Respuestas',
  flashcards: 'Flashcards',
  action_items: 'Tareas',
  fill_in_blank: 'Completar',
};

function urgencyBadge(urgency: Urgency) {
  if (urgency === 'high')
    return <Badge className="bg-red-100 text-red-700 border-red-200">Alta</Badge>;
  if (urgency === 'medium')
    return <Badge className="bg-yellow-100 text-yellow-700 border-yellow-200">Media</Badge>;
  return <Badge className="bg-gray-100 text-gray-500 border-gray-200">Baja</Badge>;
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function GenerateButton({
  videoId,
  onComplete,
}: {
  videoId: number;
  onComplete: () => void;
}) {
  const [generating, setGenerating] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<Set<GenStep>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = useCallback(() => {
    setGenerating(true);
    setCompletedSteps(new Set());
    setError(null);

    const cancel = startGeneration(
      videoId,
      (event) => {
        if (event.type === 'progress') {
          setCompletedSteps((prev) => new Set(prev).add(event.step));
        } else if (event.type === 'complete') {
          setGenerating(false);
          cancel();
          onComplete();
        } else if (event.type === 'error') {
          setError(event.message);
          setGenerating(false);
        }
      },
      (err) => {
        setError(err.message);
        setGenerating(false);
      }
    );
  }, [videoId, onComplete]);

  return (
    <div className="space-y-3">
      <Button onClick={handleGenerate} disabled={generating}>
        {generating ? (
          <>
            <Loader2 className="size-4 mr-2 animate-spin" />
            Generando...
          </>
        ) : (
          <>
            <Sparkles className="size-4 mr-2" />
            Generar Material de Estudio
          </>
        )}
      </Button>

      {generating && (
        <div className="space-y-1.5">
          {GENERATION_STEPS.map((step) => {
            const done = completedSteps.has(step);
            const steps = [...completedSteps];
            const currentIdx = GENERATION_STEPS.indexOf(steps[steps.length - 1] ?? 'summary');
            const stepIdx = GENERATION_STEPS.indexOf(step);
            const active = !done && stepIdx === (steps.length > 0 ? currentIdx + 1 : 0);
            return (
              <div key={step} className="flex items-center gap-2 text-sm">
                {done ? (
                  <CheckCircle2 className="size-4 text-green-500 shrink-0" />
                ) : active ? (
                  <Loader2 className="size-4 animate-spin text-primary shrink-0" />
                ) : (
                  <div className="size-4 rounded-full border-2 border-muted shrink-0" />
                )}
                <span className={done ? 'text-muted-foreground line-through' : active ? 'text-foreground font-medium' : 'text-muted-foreground'}>
                  {STEP_LABELS[step]}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">Error: {error}</p>
      )}
    </div>
  );
}

function SummarySection({ videoId }: { videoId: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['summary', videoId],
    queryFn: () => getSummary(videoId),
    retry: false,
  });

  if (isLoading) return <div className="flex justify-center py-4"><Loader2 className="size-4 animate-spin text-muted-foreground" /></div>;
  if (error) return <p className="text-sm text-muted-foreground italic">Sin resumen todavía. Genera el material de estudio primero.</p>;

  return (
    <div className="prose prose-sm max-w-none text-sm leading-relaxed whitespace-pre-wrap">
      {data?.text}
    </div>
  );
}

function QASection({ videoId }: { videoId: number }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const { data, isLoading, error } = useQuery({
    queryKey: ['qa', videoId],
    queryFn: () => getQA(videoId),
    retry: false,
  });

  if (isLoading) return <div className="flex justify-center py-4"><Loader2 className="size-4 animate-spin text-muted-foreground" /></div>;
  if (error || !data?.pairs.length)
    return <p className="text-sm text-muted-foreground italic">Sin preguntas todavía.</p>;

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  return (
    <div className="space-y-2">
      {data.pairs.map((pair: QAPair, i: number) => (
        <Card key={i} className="py-0 cursor-pointer" onClick={() => toggle(i)}>
          <CardContent className="px-4 py-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{pair.question}</p>
                {expanded.has(i) && (
                  <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                    {pair.answer}
                  </p>
                )}
              </div>
              {expanded.has(i) ? (
                <ChevronDown className="size-4 shrink-0 text-muted-foreground mt-0.5" />
              ) : (
                <ChevronRight className="size-4 shrink-0 text-muted-foreground mt-0.5" />
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function FlashcardsSection({ videoId }: { videoId: number }) {
  const [flipped, setFlipped] = useState<Set<number>>(new Set());
  const { data, isLoading, error } = useQuery({
    queryKey: ['flashcards', videoId],
    queryFn: () => getFlashcards(videoId),
    retry: false,
  });

  if (isLoading) return <div className="flex justify-center py-4"><Loader2 className="size-4 animate-spin text-muted-foreground" /></div>;
  if (error || !data?.cards.length)
    return <p className="text-sm text-muted-foreground italic">Sin flashcards todavía.</p>;

  const toggle = (i: number) => {
    setFlipped((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const flipAll = () => {
    if (flipped.size === data.cards.length) {
      setFlipped(new Set());
    } else {
      setFlipped(new Set(data.cards.map((_, i) => i)));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {data.cards.length} tarjeta{data.cards.length !== 1 ? 's' : ''} — haz click para revelar
        </p>
        <Button variant="outline" size="sm" onClick={flipAll}>
          <RotateCcw className="size-3 mr-1.5" />
          {flipped.size === data.cards.length ? 'Ocultar todo' : 'Revelar todo'}
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {data.cards.map((card: Flashcard, i: number) => (
          <div
            key={i}
            className={`rounded-xl border p-4 cursor-pointer transition-colors min-h-[80px] flex flex-col justify-between ${
              flipped.has(i) ? 'bg-primary/5 border-primary/30' : 'hover:bg-muted/50'
            }`}
            onClick={() => toggle(i)}
          >
            <p className="text-sm font-semibold">{card.concept}</p>
            {flipped.has(i) && (
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed border-t pt-2">
                {card.definition}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ActionItemsSection({
  videoId,
  showDismissed = false,
}: {
  videoId: number;
  showDismissed?: boolean;
}) {
  const queryClient = useQueryClient();
  const [dismissing, setDismissing] = useState<Set<number>>(new Set());
  const [localDismissed, setLocalDismissed] = useState<Set<number>>(new Set());

  const { data, isLoading, error } = useQuery({
    queryKey: ['action-items', videoId],
    queryFn: () => getActionItems(videoId),
    retry: false,
  });

  const handleDismiss = async (item: ActionItem) => {
    setDismissing((prev) => new Set(prev).add(item.id));
    setLocalDismissed((prev) => new Set(prev).add(item.id));
    try {
      await dismissActionItem(videoId, item.id);
      queryClient.invalidateQueries({ queryKey: ['action-items', videoId] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-alerts'] });
    } catch {
      setLocalDismissed((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    } finally {
      setDismissing((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  };

  if (isLoading) return <div className="flex justify-center py-4"><Loader2 className="size-4 animate-spin text-muted-foreground" /></div>;
  if (error) return <p className="text-sm text-muted-foreground italic">Sin tareas todavía.</p>;

  const items = (data?.items ?? []).filter(
    (item) => showDismissed || (!item.dismissed && !localDismissed.has(item.id))
  );

  if (items.length === 0)
    return (
      <p className="text-sm text-muted-foreground italic">
        <CheckCircle2 className="inline size-4 text-green-500 mr-1" />
        Sin tareas pendientes.
      </p>
    );

  return (
    <div className="space-y-2">
      {items.map((item: ActionItem) => (
        <Card key={item.id} className="py-0">
          <CardContent className="px-4 py-3 flex items-start gap-3">
            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                {urgencyBadge(item.urgency)}
                {item.extracted_date && (
                  <span className="text-xs text-muted-foreground">
                    {item.extracted_date}
                  </span>
                )}
              </div>
              <p className="text-sm">{item.text}</p>
            </div>
            {!item.dismissed && !localDismissed.has(item.id) && (
              <Button
                variant="ghost"
                size="icon"
                className="size-7 shrink-0 text-muted-foreground hover:text-foreground"
                onClick={() => handleDismiss(item)}
                disabled={dismissing.has(item.id)}
              >
                {dismissing.has(item.id) ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="size-3.5" />
                )}
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function FillInBlankSection({ videoId }: { videoId: number }) {
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const { data, isLoading, error } = useQuery({
    queryKey: ['fill-in-blank', videoId],
    queryFn: () => getFillInBlank(videoId),
    retry: false,
  });

  if (isLoading) return <div className="flex justify-center py-4"><Loader2 className="size-4 animate-spin text-muted-foreground" /></div>;
  if (error || !data?.items.length)
    return <p className="text-sm text-muted-foreground italic">Sin ejercicios de completar todavía.</p>;

  const toggle = (i: number) => {
    setRevealed((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  return (
    <div className="space-y-2">
      {data.items.map((item: FillInBlankItem, i: number) => (
        <Card key={i} className="py-0">
          <CardContent className="px-4 py-3 space-y-2">
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{item.sentence}</p>
                {revealed.has(i) && (
                  <div className="mt-2 space-y-1">
                    <p className="text-sm text-green-700 font-semibold">
                      Respuesta: {item.answer}
                    </p>
                    {item.hint && (
                      <p className="text-xs text-muted-foreground">
                        Pista: {item.hint}
                      </p>
                    )}
                  </div>
                )}
              </div>
              {item.starred && (
                <span className="text-sm shrink-0" title="Importante para el examen">⭐</span>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => toggle(i)}
              className="text-xs"
            >
              {revealed.has(i) ? 'Ocultar respuesta' : 'Ver respuesta'}
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------
// Main page
// ------------------------------------------------------------------

type Tab = 'resumen' | 'qa' | 'flashcards' | 'tareas' | 'completar';

const TABS: { id: Tab; label: string; icon: typeof BookOpen }[] = [
  { id: 'resumen', label: 'Resumen', icon: BookOpen },
  { id: 'qa', label: 'Q&A', icon: Zap },
  { id: 'flashcards', label: 'Flashcards', icon: RotateCcw },
  { id: 'tareas', label: 'Tareas', icon: CheckCircle2 },
  { id: 'completar', label: 'Completar', icon: PenLine },
];

export function ClassDetail() {
  const { videoId } = useParams<{ videoId: string }>();
  const queryClient = useQueryClient();
  const id = Number(videoId);
  const [activeTab, setActiveTab] = useState<Tab>('resumen');

  const { data: video, isLoading: videoLoading } = useQuery({
    queryKey: ['video', id],
    queryFn: () => getVideoById(id),
    enabled: !isNaN(id),
  });

  const handleGenerateComplete = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['summary', id] });
    queryClient.invalidateQueries({ queryKey: ['qa', id] });
    queryClient.invalidateQueries({ queryKey: ['flashcards', id] });
    queryClient.invalidateQueries({ queryKey: ['action-items', id] });
    queryClient.invalidateQueries({ queryKey: ['fill-in-blank', id] });
  }, [queryClient, id]);

  if (videoLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const title = video?.output_title ?? `Clase #${id}`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to="/courses"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3"
        >
          <ArrowLeft className="size-4" />
          Mis Materias
        </Link>
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-bold leading-tight">{title}</h1>
        </div>
        {video?.processed_at && (
          <p className="text-xs text-muted-foreground mt-1">
            Transcrito:{' '}
            {new Date(video.processed_at).toLocaleDateString('es-MX', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </p>
        )}
      </div>

      {/* Generate button */}
      <Card className="py-4">
        <CardContent className="px-4">
          <GenerateButton videoId={id} onComplete={handleGenerateComplete} />
        </CardContent>
      </Card>

      {/* Tabs */}
      <div>
        <div className="flex gap-1 border-b mb-4 overflow-x-auto">
          {TABS.map(({ id: tabId, label, icon: Icon }) => (
            <button
              key={tabId}
              type="button"
              onClick={() => setActiveTab(tabId)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tabId
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/30'
              }`}
            >
              <Icon className="size-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div>
          {activeTab === 'resumen' && <SummarySection videoId={id} />}
          {activeTab === 'qa' && <QASection videoId={id} />}
          {activeTab === 'flashcards' && <FlashcardsSection videoId={id} />}
          {activeTab === 'tareas' && <ActionItemsSection videoId={id} />}
          {activeTab === 'completar' && <FillInBlankSection videoId={id} />}
        </div>
      </div>
    </div>
  );
}
