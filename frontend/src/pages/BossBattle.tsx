/**
 * BossBattle.tsx — Weekly Boss Battle (SEB-87)
 *
 * Aggregates the most-failed cards of the week across all classes and
 * presents them in a dramatic dark "battle" arena. Pasar el boss = dominar
 * los puntos débiles. Completion unlocks the Boss Slayer badge.
 * Route: /boss-battle (optional ?courseId=X)
 */

import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Loader2, Skull, Swords, XCircle } from 'lucide-react';
import {
  getCollections,
  getCollection,
  type CollectionEntry,
  type CollectionItemEntry,
} from '@/api/client';
import {
  completeBossBattle,
  getBossBattle,
  getErrorDetection,
  getFillInBlank,
  getFlashcards,
  getQA,
  getTrueFalse,
  rateCard,
  type ErrorDetectionItem,
  type FillInBlankItem,
  type Flashcard,
  type QAPair,
  type TrueFalseItem,
} from '@/api/learning';
import { Button } from '@/components/ui/button';

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

interface BossCard {
  id: string;
  card_type: 'flashcard' | 'quiz' | 'fill_in_blank' | 'true_false' | 'error_detection';
  prompt: string;
  promptLabel: string;
  answer: string;
  answerLabel: string;
  explanation: string;
  courseName: string;
  className: string;
  videoId: number;
  failCount: number;
}

interface ClassMeta {
  item: CollectionItemEntry;
  courseName: string;
}

// ------------------------------------------------------------------
// Card-id pattern matching (mirrors Learn.tsx buildDeck)
// ------------------------------------------------------------------

function buildCardLookup(
  classMeta: ClassMeta,
  flashcards: Flashcard[],
  qaPairs: QAPair[],
  fillInBlanks: FillInBlankItem[],
  trueFalseItems: TrueFalseItem[],
  errorDetectionItems: ErrorDetectionItem[]
): Map<string, BossCard> {
  const map = new Map<string, BossCard>();
  const { item, courseName } = classMeta;
  const className = item.output_title;
  const videoId = item.id;

  flashcards.forEach((fc, i) => {
    map.set(`fc-${videoId}-${i}`, {
      id: `fc-${videoId}-${i}`,
      card_type: 'flashcard',
      prompt: fc.concept,
      promptLabel: 'Concepto',
      answer: fc.definition,
      answerLabel: 'Definición',
      explanation: '',
      courseName,
      className,
      videoId,
      failCount: 0,
    });
  });

  qaPairs.forEach((pair, i) => {
    // Either qa-fc fallback or full quiz card — both refer to the same Q&A pair.
    const base: Omit<BossCard, 'id'> = {
      card_type: 'quiz',
      prompt: pair.question,
      promptLabel: 'Pregunta',
      answer: pair.answer,
      answerLabel: 'Respuesta',
      explanation: '',
      courseName,
      className,
      videoId,
      failCount: 0,
    };
    map.set(`quiz-${videoId}-${i}`, { id: `quiz-${videoId}-${i}`, ...base });
    map.set(`qa-fc-${videoId}-${i}`, {
      id: `qa-fc-${videoId}-${i}`,
      ...base,
      card_type: 'flashcard',
    });
  });

  fillInBlanks.forEach((fib, i) => {
    map.set(`fib-${fib.id}-${i}`, {
      id: `fib-${fib.id}-${i}`,
      card_type: 'fill_in_blank',
      prompt: fib.sentence.replace('___', '_____'),
      promptLabel: 'Completar',
      answer: fib.answer,
      answerLabel: 'Respuesta',
      explanation: fib.hint ? `Pista: ${fib.hint}` : '',
      courseName,
      className,
      videoId,
      failCount: 0,
    });
  });

  trueFalseItems.forEach((tf, i) => {
    map.set(`tf-${tf.id}-${i}`, {
      id: `tf-${tf.id}-${i}`,
      card_type: 'true_false',
      prompt: tf.statement,
      promptLabel: 'Verdadero o Falso',
      answer: tf.is_true ? 'Verdadero' : 'Falso',
      answerLabel: 'Es',
      explanation: tf.explanation,
      courseName,
      className,
      videoId,
      failCount: 0,
    });
  });

  errorDetectionItems.forEach((ed, i) => {
    map.set(`ed-${ed.id}-${i}`, {
      id: `ed-${ed.id}-${i}`,
      card_type: 'error_detection',
      prompt: ed.statement,
      promptLabel: 'Detectar el error',
      answer: ed.correction,
      answerLabel: 'Corrección',
      explanation: ed.explanation,
      courseName,
      className,
      videoId,
      failCount: 0,
    });
  });

  return map;
}

// ------------------------------------------------------------------
// Battle card UI
// ------------------------------------------------------------------

function BattleCard({
  card,
  index,
  total,
  onResolve,
}: {
  card: BossCard;
  index: number;
  total: number;
  onResolve: (defeated: boolean) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const [exiting, setExiting] = useState<'left' | 'right' | null>(null);

  // Reset on card change
  useEffect(() => {
    setRevealed(false);
    setExiting(null);
  }, [card.id]);

  const handleResolve = (defeated: boolean) => {
    rateCard(card.videoId, card.id, card.card_type, defeated ? 4 : 1).catch(console.error);
    setExiting(defeated ? 'right' : 'left');
    setTimeout(() => onResolve(defeated), 280);
  };

  const translateX = exiting === 'left' ? -420 : exiting === 'right' ? 420 : 0;
  const opacity = exiting ? 0 : 1;

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-4">
      <div
        className="w-full max-w-md"
        style={{
          transform: `translateX(${translateX}px)`,
          opacity,
          transition: exiting ? 'transform 0.28s ease, opacity 0.28s ease' : 'none',
        }}
      >
        <div className="rounded-2xl border-2 border-red-500/40 bg-zinc-900/95 shadow-[0_0_40px_rgba(239,68,68,0.25)] overflow-hidden text-zinc-100">
          {/* Header */}
          <div className="bg-gradient-to-r from-red-900/60 via-zinc-900 to-red-900/60 px-5 py-3 flex items-center gap-2 border-b border-red-500/30">
            <Skull className="size-4 text-red-400 shrink-0" />
            <span className="text-xs font-bold uppercase tracking-widest text-red-300">
              Boss Round {index + 1}/{total}
            </span>
            <span className="ml-auto text-[11px] text-zinc-400 truncate">
              {card.courseName} · {card.className}
            </span>
          </div>

          {/* Content */}
          <div className="px-6 pt-6 pb-4 min-h-[260px] flex flex-col gap-5">
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-red-400 mb-2">
                {card.promptLabel}
              </p>
              <p className="text-lg font-semibold leading-snug text-zinc-50">{card.prompt}</p>
            </div>

            {revealed ? (
              <div className="border-t border-red-500/20 pt-4 space-y-3">
                <p className="text-[10px] uppercase tracking-[0.2em] text-emerald-400">
                  {card.answerLabel}
                </p>
                <p className="text-base leading-relaxed text-emerald-100">{card.answer}</p>
                {card.explanation && (
                  <p className="text-xs text-zinc-400 leading-relaxed">{card.explanation}</p>
                )}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setRevealed(true)}
                className="border-t border-red-500/20 pt-5 text-sm text-red-300 hover:text-red-200 transition-colors text-center"
              >
                Toca para revelar la respuesta
              </button>
            )}
          </div>

          {/* Battle stats */}
          <div className="px-5 pb-2 flex items-center justify-between text-[11px] text-zinc-500">
            <span className="inline-flex items-center gap-1">
              <span className="text-red-400">{'☠'}</span> Fallaste {card.failCount}x esta semana
            </span>
            <span>HP: {revealed ? '50%' : '100%'}</span>
          </div>

          {/* Actions */}
          <div className="px-5 pb-5 pt-3 flex gap-3">
            <Button
              variant="outline"
              className="flex-1 border-red-500/60 bg-red-950/40 text-red-200 hover:bg-red-900/60"
              onClick={() => handleResolve(false)}
              disabled={!revealed}
            >
              <XCircle className="size-4 mr-1.5" /> Sigo en duda
            </Button>
            <Button
              className="flex-1 bg-emerald-600 text-emerald-50 hover:bg-emerald-500"
              onClick={() => handleResolve(true)}
              disabled={!revealed}
            >
              <Swords className="size-4 mr-1.5" /> Lo derroté
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Intro / Victory / Empty screens
// ------------------------------------------------------------------

function IntroScreen({
  cardCount,
  weekStart,
  onStart,
}: {
  cardCount: number;
  weekStart: string | null;
  onStart: () => void;
}) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
      <div className="space-y-6 max-w-sm">
        <div className="text-6xl boss-pulse" aria-hidden="true">{'💀'}</div>
        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold tracking-tight text-red-400 boss-shake">
            BOSS BATTLE
          </h1>
          <p className="text-sm text-zinc-400">
            Los {cardCount} conceptos que más te tumbaron esta semana se han juntado.
            Vencerlos es dominarlos.
          </p>
          {weekStart && (
            <p className="text-[11px] uppercase tracking-widest text-zinc-500">
              Semana del {formatWeek(weekStart)}
            </p>
          )}
        </div>
        <Button
          size="lg"
          className="w-full bg-red-600 text-red-50 hover:bg-red-500 shadow-[0_0_30px_rgba(239,68,68,0.45)]"
          onClick={onStart}
        >
          <Swords className="size-5 mr-2" /> Iniciar batalla
        </Button>
        <p className="text-[11px] text-zinc-500">
          Pasar el boss desbloquea la insignia "Boss Slayer".
        </p>
      </div>
    </div>
  );
}

function VictoryScreen({ defeated, total }: { defeated: number; total: number }) {
  const flawless = defeated === total;
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
      <div className="space-y-6 max-w-sm">
        <div className="text-7xl boss-pulse">{flawless ? '🏆' : '⚔️'}</div>
        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold tracking-tight text-emerald-300">
            {flawless ? '¡VICTORIA TOTAL!' : '¡BOSS DERROTADO!'}
          </h1>
          <p className="text-sm text-zinc-400">
            Derrotaste {defeated} de {total} cartas. Tu insignia te espera.
          </p>
        </div>
        <div className="rounded-2xl border-2 border-yellow-500/60 bg-gradient-to-br from-yellow-900/30 to-amber-900/20 px-6 py-5 shadow-[0_0_40px_rgba(234,179,8,0.35)]">
          <p className="text-[11px] uppercase tracking-widest text-yellow-400 mb-1">
            Insignia desbloqueada
          </p>
          <p className="text-2xl font-bold text-yellow-200">
            {'🏅'} Boss Slayer
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <Link to="/stats">
            <Button className="w-full bg-emerald-600 hover:bg-emerald-500 text-emerald-50">
              Ver mis logros
            </Button>
          </Link>
          <Link to="/learn">
            <Button variant="outline" className="w-full border-zinc-700 text-zinc-300 bg-transparent hover:bg-zinc-800">
              Volver a aprender
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

function NoBossScreen() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
      <div className="space-y-4 max-w-sm">
        <div className="text-6xl">{'🛡️'}</div>
        <h2 className="text-xl font-semibold text-zinc-200">No hay boss esta semana</h2>
        <p className="text-sm text-zinc-400">
          No tenemos suficientes errores para invocar al boss. Sigue estudiando — el lunes
          empieza una nueva semana de tracking.
        </p>
        <Link to="/learn">
          <Button variant="outline" className="border-zinc-700 text-zinc-300 bg-transparent hover:bg-zinc-800">
            <ArrowLeft className="size-4 mr-2" /> Ir a aprender
          </Button>
        </Link>
      </div>
    </div>
  );
}

function formatWeek(iso: string): string {
  try {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('es-MX', { day: 'numeric', month: 'short' });
  } catch {
    return iso;
  }
}

// ------------------------------------------------------------------
// Main page
// ------------------------------------------------------------------

type Phase = 'intro' | 'battle' | 'victory';

export function BossBattle() {
  const [searchParams] = useSearchParams();
  const courseIdParam = searchParams.get('courseId');
  const courseId = courseIdParam ? Number(courseIdParam) : null;

  const [phase, setPhase] = useState<Phase>('intro');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [defeated, setDefeated] = useState(0);

  // Load collections (and filter to courseId if provided)
  const { data: collections, isLoading: collectionsLoading } = useQuery({
    queryKey: ['collections'],
    queryFn: getCollections,
  });

  const targetCollections: CollectionEntry[] = useMemo(() => {
    if (!collections) return [];
    return courseId ? collections.filter((c) => c.id === courseId) : collections;
  }, [collections, courseId]);

  // Fetch each collection's items (classes)
  const collectionDetailsQuery = useQuery({
    queryKey: ['boss-battle-collections', targetCollections.map((c) => c.id).sort()],
    queryFn: async () => Promise.all(targetCollections.map((c) => getCollection(c.id))),
    enabled: targetCollections.length > 0,
  });

  const classMetas: ClassMeta[] = useMemo(() => {
    const out: ClassMeta[] = [];
    if (!collectionDetailsQuery.data) return out;
    for (const detail of collectionDetailsQuery.data) {
      const courseName =
        collections?.find((c) => c.id === detail.id)?.name ?? detail.name;
      for (const item of detail.items) {
        out.push({ item, courseName });
      }
    }
    return out;
  }, [collectionDetailsQuery.data, collections]);

  // For each class: fetch boss-battle failures + content, build lookup, filter
  const battleQuery = useQuery({
    queryKey: ['boss-battle-deck', classMetas.map((m) => m.item.id).sort()],
    queryFn: async () => {
      const perClass = await Promise.all(
        classMetas.map(async (meta) => {
          const id = meta.item.id;
          const [bossRes, fcRes, qaRes, fibRes, tfRes, edRes] = await Promise.allSettled([
            getBossBattle(id),
            getFlashcards(id),
            getQA(id),
            getFillInBlank(id),
            getTrueFalse(id),
            getErrorDetection(id),
          ]);

          if (bossRes.status !== 'fulfilled' || bossRes.value.cards.length === 0) {
            return { meta, cards: [] as BossCard[], weekStart: null as string | null };
          }
          const lookup = buildCardLookup(
            meta,
            fcRes.status === 'fulfilled' ? fcRes.value.cards : [],
            qaRes.status === 'fulfilled' ? qaRes.value.pairs : [],
            fibRes.status === 'fulfilled' ? fibRes.value.items : [],
            tfRes.status === 'fulfilled' ? tfRes.value.items : [],
            edRes.status === 'fulfilled' ? edRes.value.items : []
          );
          const resolved: BossCard[] = [];
          for (const failing of bossRes.value.cards) {
            const found = lookup.get(failing.card_id);
            if (found) {
              resolved.push({ ...found, failCount: failing.fail_count });
            }
          }
          return { meta, cards: resolved, weekStart: bossRes.value.week_start };
        })
      );
      const weekStart = perClass.find((p) => p.weekStart)?.weekStart ?? null;
      // Combine & sort: highest fail_count first
      const all = perClass.flatMap((p) => p.cards);
      all.sort((a, b) => b.failCount - a.failCount);
      return { cards: all, weekStart };
    },
    enabled: classMetas.length > 0,
  });

  const isLoading =
    collectionsLoading ||
    collectionDetailsQuery.isLoading ||
    (classMetas.length > 0 && battleQuery.isLoading);
  const cards = battleQuery.data?.cards ?? [];
  const weekStart = battleQuery.data?.weekStart ?? null;

  // Record completion (one event per video that contributed cards) on victory.
  useEffect(() => {
    if (phase !== 'victory' || cards.length === 0) return;
    const videoIds = Array.from(new Set(cards.map((c) => c.videoId)));
    videoIds.forEach((vid) => {
      completeBossBattle(vid).catch(console.error);
    });
  }, [phase]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleResolve = (cardDefeated: boolean) => {
    if (cardDefeated) setDefeated((n) => n + 1);
    setCurrentIndex((prev) => {
      if (prev + 1 >= cards.length) {
        setPhase('victory');
        return prev;
      }
      return prev + 1;
    });
  };

  const handleStart = () => {
    setCurrentIndex(0);
    setDefeated(0);
    setPhase('battle');
  };

  // --- Loading
  if (isLoading) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-zinc-950 text-zinc-300">
        <Loader2 className="size-8 animate-spin text-red-400 mb-3" />
        <p className="text-sm">Invocando al boss…</p>
      </div>
    );
  }

  // --- Empty
  if (cards.length === 0) {
    return (
      <div className="fixed inset-0 z-50 bg-zinc-950 text-zinc-200">
        <BossTopBar progress={0} label="—" />
        <NoBossScreen />
      </div>
    );
  }

  const progress =
    phase === 'victory'
      ? 100
      : Math.round(((phase === 'battle' ? currentIndex : 0) / cards.length) * 100);
  const label =
    phase === 'victory'
      ? `${cards.length}/${cards.length}`
      : `${phase === 'battle' ? currentIndex + 1 : 0}/${cards.length}`;

  return (
    <div className="fixed inset-0 z-50 bg-zinc-950 text-zinc-200 flex flex-col overflow-hidden">
      <BossTopBar progress={progress} label={label} />
      <div className="flex-1 relative">
        {phase === 'intro' && (
          <IntroScreen cardCount={cards.length} weekStart={weekStart} onStart={handleStart} />
        )}
        {phase === 'battle' && cards[currentIndex] && (
          <BattleCard
            key={cards[currentIndex].id}
            card={cards[currentIndex]}
            index={currentIndex}
            total={cards.length}
            onResolve={handleResolve}
          />
        )}
        {phase === 'victory' && <VictoryScreen defeated={defeated} total={cards.length} />}
      </div>

      {/* Inline keyframes for the dramatic intro animations */}
      <style>{`
        @keyframes boss-shake {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-4px); }
          40% { transform: translateX(5px); }
          60% { transform: translateX(-3px); }
          80% { transform: translateX(2px); }
        }
        @keyframes boss-pulse {
          0%, 100% { transform: scale(1); filter: drop-shadow(0 0 8px rgba(239,68,68,0.5)); }
          50% { transform: scale(1.08); filter: drop-shadow(0 0 24px rgba(239,68,68,0.8)); }
        }
        .boss-shake { animation: boss-shake 0.6s ease-in-out 0.3s 2; }
        .boss-pulse { animation: boss-pulse 1.6s ease-in-out infinite; }
      `}</style>
    </div>
  );
}

function BossTopBar({ progress, label }: { progress: number; label: string }) {
  return (
    <div className="shrink-0 px-4 pt-3 pb-2 flex items-center gap-3 bg-zinc-950 border-b border-red-900/40">
      <Link to="/learn" className="text-zinc-400 hover:text-zinc-200">
        <ArrowLeft className="size-5" />
      </Link>
      <Skull className="size-4 text-red-400" />
      <span className="text-xs font-bold uppercase tracking-widest text-red-300">
        Boss Battle
      </span>
      <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-red-600 to-red-400 rounded-full transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
      <span className="text-xs text-zinc-400 shrink-0 tabular-nums">{label}</span>
    </div>
  );
}

export default BossBattle;
