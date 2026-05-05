/**
 * Speed.tsx — Speed Round timed flashcard mode (SEB-84)
 *
 * Students race through as many flashcards as possible in 60 seconds.
 * Route: /speed (optional ?courseId=X to filter by course)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Zap, ArrowLeft, CheckCircle2, XCircle, Loader2, BookOpen, RotateCcw } from 'lucide-react';
import { getCollections, getCollection, type CollectionEntry, type CollectionItemEntry } from '@/api/client';
import { getFlashcards, logActivity, type Flashcard } from '@/api/learning';
import { Button } from '@/components/ui/button';

const ROUND_SECONDS = 60;

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

interface SpeedCard {
  id: string;
  concept: string;
  definition: string;
  courseName: string;
  className: string;
}

interface ClassMeta {
  item: CollectionItemEntry;
  courseName: string;
}

type RoundPhase = 'lobby' | 'round' | 'results';

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function shuffle<T>(arr: T[]): T[] {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function buildDeck(classMeta: ClassMeta, flashcards: Flashcard[]): SpeedCard[] {
  return flashcards.map((fc, i) => ({
    id: `fc-${classMeta.item.id}-${i}`,
    concept: fc.concept,
    definition: fc.definition,
    courseName: classMeta.courseName,
    className: classMeta.item.output_title,
  }));
}

// ------------------------------------------------------------------
// Timer display
// ------------------------------------------------------------------

function TimerBar({ secondsLeft, total }: { secondsLeft: number; total: number }) {
  const pct = (secondsLeft / total) * 100;
  const urgent = secondsLeft <= 10;

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-3 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-1000 ${urgent ? 'bg-red-500' : 'bg-primary'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span
        className={`tabular-nums font-bold text-lg w-12 text-right ${urgent ? 'text-red-500' : 'text-foreground'}`}
      >
        {secondsLeft}s
      </span>
    </div>
  );
}

// ------------------------------------------------------------------
// Single flashcard in speed mode
// ------------------------------------------------------------------

function SpeedFlashcard({
  card,
  onCorrect,
  onIncorrect,
}: {
  card: SpeedCard;
  onCorrect: () => void;
  onIncorrect: () => void;
}) {
  const [revealed, setRevealed] = useState(false);

  return (
    <div className="w-full max-w-sm mx-auto">
      <div className="bg-card border rounded-2xl shadow-xl overflow-hidden min-h-[300px] flex flex-col">
        {/* Header */}
        <div className="bg-primary/10 px-5 py-3 flex items-center gap-2">
          <BookOpen className="size-4 text-primary shrink-0" />
          <span className="text-xs font-medium text-primary truncate">{card.courseName}</span>
          <span className="text-xs text-muted-foreground truncate">· {card.className}</span>
        </div>

        {/* Content — tap to flip */}
        <button
          className="flex-1 flex flex-col items-center justify-center px-6 py-8 gap-5 text-left w-full cursor-pointer hover:bg-muted/30 transition-colors"
          onClick={() => setRevealed((r) => !r)}
        >
          <div className="text-center w-full">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Concepto</p>
            <p className="text-xl font-bold leading-snug">{card.concept}</p>
          </div>

          {!revealed ? (
            <p className="text-sm text-muted-foreground">Toca para revelar definición</p>
          ) : (
            <div className="w-full border-t pt-5 text-center">
              <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Definición</p>
              <p className="text-base leading-relaxed text-foreground">{card.definition}</p>
            </div>
          )}
        </button>

        {/* Action buttons */}
        <div className="px-5 pb-5 flex gap-3">
          <Button
            variant="outline"
            className="flex-1 border-red-300 text-red-600 hover:bg-red-50"
            onClick={onIncorrect}
          >
            <XCircle className="size-4 mr-1.5" />
            Incorrecto ✗
          </Button>
          <Button
            variant="outline"
            className="flex-1 border-green-300 text-green-600 hover:bg-green-50"
            onClick={onCorrect}
          >
            <CheckCircle2 className="size-4 mr-1.5" />
            Correcto ✓
          </Button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Results screen
// ------------------------------------------------------------------

function ResultsScreen({
  correct,
  total,
  elapsedSeconds,
  onPlayAgain,
}: {
  correct: number;
  total: number;
  elapsedSeconds: number;
  onPlayAgain: () => void;
}) {
  const cpm =
    elapsedSeconds > 0 ? Math.round((total / elapsedSeconds) * 60) : total;
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
  const pctColor =
    pct >= 70 ? '#16a34a' : pct >= 40 ? '#ea580c' : '#dc2626';

  return (
    <div className="flex flex-col items-center justify-center px-6 py-8 min-h-[60vh]">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="text-5xl">⚡</div>
        <div>
          <h2 className="text-2xl font-bold">Ronda completada</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            {total === 0
              ? 'No se respondieron tarjetas'
              : `Respondiste ${total} tarjeta${total !== 1 ? 's' : ''} en ${elapsedSeconds}s`}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {/* Score */}
          <div className="bg-card border rounded-xl p-4 col-span-2">
            <p className="text-4xl font-bold" style={{ color: pctColor }}>
              {correct}/{total}
            </p>
            <p className="text-xs text-muted-foreground mt-1">Correctas</p>
          </div>

          {/* Accuracy */}
          {total > 0 && (
            <div className="bg-card border rounded-xl p-4">
              <p className="text-3xl font-bold" style={{ color: pctColor }}>
                {pct}%
              </p>
              <p className="text-xs text-muted-foreground mt-1">Precisión</p>
            </div>
          )}

          {/* Cards per minute */}
          {total > 0 && (
            <div className="bg-card border rounded-xl p-4">
              <p className="text-3xl font-bold text-primary">{cpm}</p>
              <p className="text-xs text-muted-foreground mt-1">Tarjetas/min</p>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <Button onClick={onPlayAgain} className="w-full">
            <RotateCcw className="size-4 mr-2" />
            Jugar de nuevo
          </Button>
          <Link to="/speed">
            <Button variant="outline" className="w-full">
              <ArrowLeft className="size-4 mr-2" />
              Volver
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Lobby — course selector
// ------------------------------------------------------------------

function Lobby({
  collections,
  selectedCourseId,
  onSelectCourse,
  onStart,
  hasCards,
}: {
  collections: CollectionEntry[];
  selectedCourseId: number | null;
  onSelectCourse: (id: number | null) => void;
  onStart: () => void;
  hasCards: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-8 min-h-[60vh]">
      <div className="w-full max-w-sm space-y-6">
        {/* Hero */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center size-16 rounded-full bg-primary/10 mx-auto">
            <Zap className="size-8 text-primary" />
          </div>
          <h1 className="text-2xl font-bold">Speed Round</h1>
          <p className="text-muted-foreground text-sm">
            {ROUND_SECONDS} segundos. Tantas flashcards como puedas. ¡Sin distracciones!
          </p>
        </div>

        {/* Course selector */}
        <div className="space-y-2">
          <label className="text-sm font-medium">Materia</label>
          <select
            className="w-full border rounded-lg px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={selectedCourseId ?? ''}
            onChange={(e) =>
              onSelectCourse(e.target.value === '' ? null : Number(e.target.value))
            }
          >
            <option value="">Todas las materias</option>
            {collections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <Button className="w-full text-base py-5" onClick={onStart} disabled={!hasCards}>
          <Zap className="size-4 mr-2" />
          ¡Comenzar!
        </Button>

        {!hasCards && (
          <p className="text-center text-sm text-muted-foreground">
            No hay flashcards disponibles para esta selección.{' '}
            <Link to="/courses" className="underline text-primary">
              Genera contenido primero.
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Main Speed page
// ------------------------------------------------------------------

export function Speed() {
  const [searchParams] = useSearchParams();
  const courseIdParam = searchParams.get('courseId');
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(
    courseIdParam ? Number(courseIdParam) : null
  );

  const [phase, setPhase] = useState<RoundPhase>('lobby');
  const [deck, setDeck] = useState<SpeedCard[]>([]);
  const [cardIndex, setCardIndex] = useState(0);
  const [correct, setCorrect] = useState(0);
  const [timeLeft, setTimeLeft] = useState(ROUND_SECONDS);
  const [deckSeed, setDeckSeed] = useState(0);
  const startTimeRef = useRef<number>(0);
  const elapsedRef = useRef<number>(0);

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------

  const { data: allCollections, isLoading: collectionsLoading } = useQuery({
    queryKey: ['collections'],
    queryFn: getCollections,
  });

  const collectionsToLoad: CollectionEntry[] = selectedCourseId
    ? (allCollections?.filter((c) => c.id === selectedCourseId) ?? [])
    : (allCollections ?? []);

  const collectionQueries = useQuery({
    queryKey: ['collection-detail-batch', collectionsToLoad.map((c) => c.id).sort()],
    queryFn: async () => Promise.all(collectionsToLoad.map((c) => getCollection(c.id))),
    enabled: collectionsToLoad.length > 0,
  });

  const isLoading = collectionsLoading || collectionQueries.isLoading;

  const classMetas: ClassMeta[] = [];
  if (collectionQueries.data) {
    for (const colDetail of collectionQueries.data) {
      const courseName =
        allCollections?.find((c) => c.id === colDetail.id)?.name ?? colDetail.name;
      for (const item of colDetail.items) {
        classMetas.push({ item, courseName });
      }
    }
  }

  const classIds = classMetas.map((cm) => cm.item.id);

  const contentQuery = useQuery({
    queryKey: ['speed-content', classIds.sort().join(','), deckSeed],
    queryFn: async () => {
      const results = await Promise.all(
        classMetas.map(async (cm) => {
          const fcRes = await getFlashcards(cm.item.id).catch(() => ({ cards: [] as Flashcard[] }));
          return { meta: cm, flashcards: fcRes.cards };
        })
      );
      return results;
    },
    enabled: classMetas.length > 0,
  });

  // Build deck whenever content loads
  useEffect(() => {
    if (!contentQuery.data) return;
    const allCards: SpeedCard[] = contentQuery.data.flatMap((r) =>
      buildDeck(r.meta, r.flashcards)
    );
    setDeck(shuffle(allCards));
  }, [contentQuery.data]);

  const hasCards = deck.length > 0;

  // ------------------------------------------------------------------
  // Timer
  // ------------------------------------------------------------------

  useEffect(() => {
    if (phase !== 'round') return;

    const interval = setInterval(() => {
      setTimeLeft((t) => {
        if (t <= 1) {
          clearInterval(interval);
          elapsedRef.current = ROUND_SECONDS;
          setPhase('results');
          return 0;
        }
        return t - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [phase]);

  // ------------------------------------------------------------------
  // Round actions
  // ------------------------------------------------------------------

  const startRound = useCallback(() => {
    setCardIndex(0);
    setCorrect(0);
    setTimeLeft(ROUND_SECONDS);
    startTimeRef.current = Date.now();
    setPhase('round');
  }, []);

  const advance = useCallback(
    (wasCorrect: boolean) => {
      if (wasCorrect) setCorrect((n) => n + 1);

      const nextIndex = cardIndex + 1;
      if (nextIndex >= deck.length) {
        elapsedRef.current = Math.round((Date.now() - startTimeRef.current) / 1000);
        setCardIndex(nextIndex);
        setPhase('results');
      } else {
        setCardIndex(nextIndex);
      }
    },
    [cardIndex, deck.length]
  );

  // Log stats on round end
  useEffect(() => {
    if (phase !== 'results') return;
    const total = Math.min(cardIndex, deck.length);
    if (total > 0) {
      logActivity('speed_round', total, correct);
    }
  }, [phase]); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePlayAgain = () => {
    setDeckSeed((s) => s + 1);
    setDeck((d) => shuffle([...d]));
    startRound();
  };

  const handleSelectCourse = (id: number | null) => {
    setSelectedCourseId(id);
    setDeckSeed((s) => s + 1);
    setPhase('lobby');
  };

  // ------------------------------------------------------------------
  // Loading state
  // ------------------------------------------------------------------

  if (isLoading || (classMetas.length > 0 && contentQuery.isLoading)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <Loader2 className="size-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground text-sm">Cargando flashcards...</p>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Results
  // ------------------------------------------------------------------

  if (phase === 'results') {
    const total = Math.min(cardIndex, deck.length);
    const elapsed =
      elapsedRef.current > 0 ? elapsedRef.current : ROUND_SECONDS - timeLeft;
    return (
      <ResultsScreen
        correct={correct}
        total={total}
        elapsedSeconds={elapsed}
        onPlayAgain={handlePlayAgain}
      />
    );
  }

  // ------------------------------------------------------------------
  // Lobby
  // ------------------------------------------------------------------

  if (phase === 'lobby') {
    return (
      <Lobby
        collections={allCollections ?? []}
        selectedCourseId={selectedCourseId}
        onSelectCourse={handleSelectCourse}
        onStart={startRound}
        hasCards={hasCards}
      />
    );
  }

  // ------------------------------------------------------------------
  // Round
  // ------------------------------------------------------------------

  const currentCard = deck[cardIndex];

  // Shouldn't happen but guard anyway
  if (!currentCard) return null;

  return (
    <div className="flex flex-col gap-4 px-4 py-4 max-w-sm mx-auto">
      {/* Timer */}
      <TimerBar secondsLeft={timeLeft} total={ROUND_SECONDS} />

      {/* Progress indicator */}
      <p className="text-xs text-muted-foreground text-center tabular-nums">
        Tarjeta {cardIndex + 1} · {correct} correcta{correct !== 1 ? 's' : ''}
      </p>

      {/* Card */}
      <SpeedFlashcard
        key={currentCard.id}
        card={currentCard}
        onCorrect={() => advance(true)}
        onIncorrect={() => advance(false)}
      />
    </div>
  );
}
