/**
 * Learn.tsx — Doomscrolling-style learning interface (SEB-77)
 *
 * TikTok/Reels-style vertical scroll with flashcard and Q&A quiz cards.
 * Route: /learn (optional ?courseId=X to filter by course)
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Brain, ArrowLeft, CheckCircle2, XCircle, ChevronLeft, ChevronRight, Loader2, BookOpen } from 'lucide-react';
import { getCollections, getCollection, type CollectionEntry, type CollectionItemEntry } from '@/api/client';
import { getFlashcards, getQA, getFillInBlank, getTrueFalse, getErrorDetection, logActivity, type Flashcard, type QAPair, type FillInBlankItem as ApiFillInBlankItem, type TrueFalseItem as ApiTrueFalseItem, type ErrorDetectionItem as ApiErrorDetectionItem } from '@/api/learning';
import { Button } from '@/components/ui/button';

// ------------------------------------------------------------------
// Card type definitions
// ------------------------------------------------------------------

interface FlashcardItem {
  type: 'flashcard';
  id: string;
  concept: string;
  definition: string;
  courseName: string;
  className: string;
  starred: boolean;
}

interface QuizItem {
  type: 'quiz';
  id: string;
  question: string;
  correctAnswer: string;
  options: string[];
  courseName: string;
  className: string;
  starred: boolean;
}

interface FillInBlankItem {
  type: 'fill_in_blank';
  id: string;
  sentence: string;
  answer: string;
  hint: string;
  courseName: string;
  className: string;
  starred: boolean;
}

interface TrueFalseItem {
  type: 'true_false';
  id: string;
  statement: string;
  isTrue: boolean;
  explanation: string;
  courseName: string;
  className: string;
  starred: boolean;
}

interface ErrorDetectionItem {
  type: 'error_detection';
  id: string;
  statement: string;
  error: string;
  correction: string;
  explanation: string;
  courseName: string;
  className: string;
  starred: boolean;
}

type DeckCard = FlashcardItem | QuizItem | FillInBlankItem | TrueFalseItem | ErrorDetectionItem;

// ------------------------------------------------------------------
// Data loading hook
// ------------------------------------------------------------------

interface ClassMeta {
  item: CollectionItemEntry;
  courseName: string;
}

function shuffle<T>(arr: T[]): T[] {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function buildDeck(
  classMeta: ClassMeta,
  flashcards: Flashcard[],
  qaPairs: QAPair[],
  fillInBlanks: ApiFillInBlankItem[],
  allAnswers: string[],
  trueFalseItems: ApiTrueFalseItem[],
  errorDetectionItems: ApiErrorDetectionItem[]
): DeckCard[] {
  const cards: DeckCard[] = [];
  const { item, courseName } = classMeta;
  const className = item.output_title;

  // FlashcardCards
  for (let i = 0; i < flashcards.length; i++) {
    const fc = flashcards[i];
    cards.push({
      type: 'flashcard',
      id: `fc-${item.id}-${i}`,
      concept: fc.concept,
      definition: fc.definition,
      courseName,
      className,
      starred: fc.starred ?? false,
    });
  }

  // QuizCards — need at least 2 distractors from other Q&A answers
  const classAnswers = qaPairs.map((p) => p.answer);
  const distractorPool = allAnswers.filter((a) => !classAnswers.includes(a));

  for (let i = 0; i < qaPairs.length; i++) {
    const pair = qaPairs[i];
    // Distractors from other pairs in same class + global pool
    const sameClassDistractors = classAnswers.filter((_, idx) => idx !== i);
    const combined = [...sameClassDistractors, ...distractorPool];
    const uniqueDistractors = [...new Set(combined)];

    if (uniqueDistractors.length < 2) {
      // Not enough distractors — skip quiz, add as flashcard instead
      cards.push({
        type: 'flashcard',
        id: `qa-fc-${item.id}-${i}`,
        concept: pair.question,
        definition: pair.answer,
        courseName,
        className,
        starred: pair.starred ?? false,
      });
      continue;
    }

    const pickedDistractors = shuffle(uniqueDistractors).slice(0, Math.min(3, uniqueDistractors.length));
    const options = shuffle([pair.answer, ...pickedDistractors]);

    cards.push({
      type: 'quiz',
      id: `quiz-${item.id}-${i}`,
      question: pair.question,
      correctAnswer: pair.answer,
      options,
      courseName,
      className,
      starred: pair.starred ?? false,
    });
  }

  // FillInBlankCards
  for (let i = 0; i < fillInBlanks.length; i++) {
    const fib = fillInBlanks[i];
    cards.push({
      type: 'fill_in_blank',
      id: `fib-${fib.id}-${i}`,
      sentence: fib.sentence,
      answer: fib.answer,
      hint: fib.hint,
      courseName,
      className,
      starred: fib.starred ?? false,
    });
  }

  // TrueFalseCards
  for (let i = 0; i < trueFalseItems.length; i++) {
    const tf = trueFalseItems[i];
    cards.push({
      type: 'true_false',
      id: `tf-${tf.id}-${i}`,
      statement: tf.statement,
      isTrue: tf.is_true,
      explanation: tf.explanation,
      courseName,
      className,
      starred: tf.starred ?? false,
    });
  }

  // ErrorDetectionCards
  for (let i = 0; i < errorDetectionItems.length; i++) {
    const ed = errorDetectionItems[i];
    cards.push({
      type: 'error_detection',
      id: `ed-${ed.id}-${i}`,
      statement: ed.statement,
      error: ed.error,
      correction: ed.correction,
      explanation: ed.explanation,
      courseName,
      className,
      starred: ed.starred ?? false,
    });
  }

  // Sort: starred cards first (each group shuffled separately)
  const starredCards = cards.filter((c) => c.starred);
  const regularCards = cards.filter((c) => !c.starred);
  return [...shuffle(starredCards), ...shuffle(regularCards)];
}

// ------------------------------------------------------------------
// Individual card components
// ------------------------------------------------------------------

interface SwipeState {
  dragging: boolean;
  startX: number;
  deltaX: number;
}

function FlashcardCard({
  card,
  onSwipeLeft,
  onSwipeRight,
}: {
  card: FlashcardItem;
  onSwipeLeft: () => void;
  onSwipeRight: () => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const [swipe, setSwipe] = useState<SwipeState>({ dragging: false, startX: 0, deltaX: 0 });
  const [exiting, setExiting] = useState<'left' | 'right' | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const handlePointerDown = (e: React.PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setSwipe({ dragging: true, startX: e.clientX, deltaX: 0 });
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!swipe.dragging) return;
    setSwipe((prev) => ({ ...prev, deltaX: e.clientX - prev.startX }));
  };

  const handlePointerUp = () => {
    if (!swipe.dragging) return;
    const { deltaX } = swipe;
    setSwipe({ dragging: false, startX: 0, deltaX: 0 });
    if (deltaX > 80) {
      triggerSwipe('right');
    } else if (deltaX < -80) {
      triggerSwipe('left');
    }
  };

  const triggerSwipe = (dir: 'left' | 'right') => {
    setExiting(dir);
    setTimeout(() => {
      if (dir === 'left') onSwipeLeft();
      else onSwipeRight();
    }, 300);
  };

  const rotation = swipe.dragging ? (swipe.deltaX / 20).toFixed(1) : exiting === 'left' ? '-15' : exiting === 'right' ? '15' : '0';
  const translateX = swipe.dragging ? swipe.deltaX : exiting === 'left' ? -400 : exiting === 'right' ? 400 : 0;
  const opacity = exiting ? 0 : 1;

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-4 select-none">
      {/* Swipe hint overlays */}
      {swipe.deltaX > 30 && (
        <div className="absolute top-1/2 left-6 -translate-y-1/2 z-20 pointer-events-none">
          <div className="bg-green-500 text-white rounded-full px-4 py-2 font-bold text-sm shadow-lg">
            Lo tengo
          </div>
        </div>
      )}
      {swipe.deltaX < -30 && (
        <div className="absolute top-1/2 right-6 -translate-y-1/2 z-20 pointer-events-none">
          <div className="bg-orange-500 text-white rounded-full px-4 py-2 font-bold text-sm shadow-lg">
            Repasar
          </div>
        </div>
      )}

      <div
        ref={cardRef}
        className="w-full max-w-sm"
        style={{
          transform: `translateX(${translateX}px) rotate(${rotation}deg)`,
          opacity,
          transition: swipe.dragging ? 'none' : 'transform 0.3s ease, opacity 0.3s ease',
          touchAction: 'pan-y',
          cursor: swipe.dragging ? 'grabbing' : 'grab',
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {/* Card */}
        <div
          className="bg-card border rounded-2xl shadow-xl overflow-hidden min-h-[360px] flex flex-col"
          onClick={() => !swipe.dragging && setRevealed((r) => !r)}
        >
          {/* Header */}
          <div className="bg-primary/10 px-5 py-3 flex items-center gap-2">
            <BookOpen className="size-4 text-primary shrink-0" />
            <span className="text-xs font-medium text-primary truncate">{card.courseName}</span>
            <span className="text-xs text-muted-foreground truncate">· {card.className}</span>
            {card.starred && (
              <span className="ml-auto text-sm" title="Importante para el examen">⭐</span>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 flex flex-col items-center justify-center px-6 py-8 gap-6">
            <div className="text-center">
              <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Concepto</p>
              <p className="text-xl font-bold leading-snug">{card.concept}</p>
            </div>

            {!revealed ? (
              <div className="text-center">
                <p className="text-sm text-muted-foreground">Toca para revelar definición</p>
              </div>
            ) : (
              <div className="w-full border-t pt-5 text-center">
                <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Definición</p>
                <p className="text-base leading-relaxed text-foreground">{card.definition}</p>
              </div>
            )}
          </div>

          {/* Footer actions */}
          <div className="px-5 pb-5 flex items-center justify-between gap-3">
            <Button
              variant="outline"
              size="sm"
              className="flex-1 border-orange-300 text-orange-600 hover:bg-orange-50"
              onClick={(e) => { e.stopPropagation(); triggerSwipe('left'); }}
            >
              <XCircle className="size-4 mr-1.5" />
              Repasar
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="flex-1 border-green-300 text-green-600 hover:bg-green-50"
              onClick={(e) => { e.stopPropagation(); triggerSwipe('right'); }}
            >
              <CheckCircle2 className="size-4 mr-1.5" />
              Lo tengo
            </Button>
          </div>
        </div>
      </div>

      {/* Arrow buttons for non-touch */}
      <div className="absolute bottom-6 left-0 right-0 flex justify-center gap-4 pointer-events-none">
        <div className="flex gap-3 pointer-events-auto">
          <button
            className="size-10 rounded-full bg-background border shadow flex items-center justify-center text-muted-foreground hover:text-foreground"
            onClick={() => triggerSwipe('left')}
            title="Repasar (←)"
          >
            <ChevronLeft className="size-5" />
          </button>
          <button
            className="size-10 rounded-full bg-background border shadow flex items-center justify-center text-muted-foreground hover:text-foreground"
            onClick={() => triggerSwipe('right')}
            title="Lo tengo (→)"
          >
            <ChevronRight className="size-5" />
          </button>
        </div>
      </div>
    </div>
  );
}

function QuizCard({
  card,
  onAnswer,
}: {
  card: QuizItem;
  onAnswer: (correct: boolean) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [answered, setAnswered] = useState(false);

  const handleSelect = (option: string) => {
    if (answered) return;
    setSelected(option);
    setAnswered(true);
    const correct = option === card.correctAnswer;
    setTimeout(() => onAnswer(correct), 1200);
  };

  const getOptionStyle = (option: string) => {
    if (!answered) return 'border-border hover:border-primary hover:bg-primary/5 cursor-pointer';
    if (option === card.correctAnswer) return 'border-green-500 bg-green-50 text-green-800 cursor-default';
    if (option === selected && option !== card.correctAnswer)
      return 'border-red-400 bg-red-50 text-red-800 cursor-default';
    return 'border-border text-muted-foreground cursor-default opacity-60';
  };

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="bg-card border rounded-2xl shadow-xl overflow-hidden">
          {/* Header */}
          <div className="bg-primary/10 px-5 py-3 flex items-center gap-2">
            <Brain className="size-4 text-primary shrink-0" />
            <span className="text-xs font-medium text-primary truncate">{card.courseName}</span>
            <span className="text-xs text-muted-foreground truncate">· {card.className}</span>
            {card.starred && (
              <span className="ml-auto text-sm" title="Importante para el examen">⭐</span>
            )}
          </div>

          {/* Question */}
          <div className="px-6 pt-6 pb-4">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Pregunta</p>
            <p className="text-lg font-semibold leading-snug">{card.question}</p>
          </div>

          {/* Options */}
          <div className="px-5 pb-6 space-y-2.5">
            {card.options.map((option, i) => (
              <button
                key={i}
                onClick={() => handleSelect(option)}
                className={`w-full text-left px-4 py-3 rounded-xl border text-sm transition-colors ${getOptionStyle(option)}`}
              >
                <span className="font-mono text-xs text-muted-foreground mr-2">
                  {String.fromCharCode(65 + i)}.
                </span>
                {option}
              </button>
            ))}
          </div>

          {/* Feedback */}
          {answered && (
            <div className={`mx-5 mb-5 px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 ${
              selected === card.correctAnswer
                ? 'bg-green-100 text-green-700'
                : 'bg-red-100 text-red-700'
            }`}>
              {selected === card.correctAnswer ? (
                <><CheckCircle2 className="size-4 shrink-0" /> Correcto</>
              ) : (
                <><XCircle className="size-4 shrink-0" /> Incorrecto</>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FillInBlankCard({
  card,
  onAnswer,
}: {
  card: FillInBlankItem;
  onAnswer: (correct: boolean) => void;
}) {
  const [input, setInput] = useState('');
  const [checked, setChecked] = useState(false);
  const [correct, setCorrect] = useState(false);
  const [exiting, setExiting] = useState<'left' | 'right' | null>(null);

  const handleCheck = () => {
    if (checked) return;
    const isCorrect = input.trim().toLowerCase() === card.answer.trim().toLowerCase();
    setCorrect(isCorrect);
    setChecked(true);
  };

  const triggerAdvance = (isCorrect: boolean) => {
    const dir = isCorrect ? 'right' : 'left';
    setExiting(dir);
    setTimeout(() => onAnswer(isCorrect), 300);
  };

  const handleNext = () => {
    triggerAdvance(correct);
  };

  const translateX = exiting === 'left' ? -400 : exiting === 'right' ? 400 : 0;
  const opacity = exiting ? 0 : 1;

  // Parts of sentence split around ___
  const parts = card.sentence.split('___');

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-4">
      <div
        className="w-full max-w-sm"
        style={{
          transform: `translateX(${translateX}px)`,
          opacity,
          transition: exiting ? 'transform 0.3s ease, opacity 0.3s ease' : 'none',
        }}
      >
        <div className="bg-card border rounded-2xl shadow-xl overflow-hidden">
          {/* Header */}
          <div className="bg-primary/10 px-5 py-3 flex items-center gap-2">
            <Brain className="size-4 text-primary shrink-0" />
            <span className="text-xs font-medium text-primary truncate">{card.courseName}</span>
            <span className="text-xs text-muted-foreground truncate">· {card.className}</span>
            {card.starred && (
              <span className="ml-auto text-sm" title="Importante para el examen">⭐</span>
            )}
          </div>

          {/* Content */}
          <div className="px-6 pt-6 pb-4">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-4">Completar</p>
            <p className="text-base leading-relaxed font-medium">
              {parts[0]}
              <span className="inline-block border-b-2 border-primary min-w-[80px] text-center text-primary font-semibold mx-1">
                {checked ? card.answer : '        '}
              </span>
              {parts[1]}
            </p>
          </div>

          {/* Input */}
          {!checked && (
            <div className="px-5 pb-4 space-y-3">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
                placeholder="Escribe la respuesta..."
                className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                autoFocus
              />
              {card.hint && (
                <p className="text-xs text-muted-foreground">Pista: {card.hint}</p>
              )}
              <Button onClick={handleCheck} className="w-full" disabled={!input.trim()}>
                Verificar
              </Button>
            </div>
          )}

          {/* Feedback */}
          {checked && (
            <div className="px-5 pb-5 space-y-3">
              <div className={`px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 ${
                correct ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {correct ? (
                  <><CheckCircle2 className="size-4 shrink-0" /> Correcto</>
                ) : (
                  <><XCircle className="size-4 shrink-0" /> Respuesta: {card.answer}</>
                )}
              </div>
              <Button onClick={handleNext} className="w-full">
                Siguiente
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TrueFalseCard({
  card,
  onAnswer,
}: {
  card: TrueFalseItem;
  onAnswer: (correct: boolean) => void;
}) {
  const [answered, setAnswered] = useState<boolean | null>(null); // null = not yet answered
  const [exiting, setExiting] = useState<'left' | 'right' | null>(null);

  const handleAnswer = (userSaysTrue: boolean) => {
    if (answered !== null) return;
    const correct = userSaysTrue === card.isTrue;
    setAnswered(correct);
  };

  const handleNext = () => {
    const correct = answered ?? false;
    const dir = correct ? 'right' : 'left';
    setExiting(dir);
    setTimeout(() => onAnswer(correct), 300);
  };

  const translateX = exiting === 'left' ? -400 : exiting === 'right' ? 400 : 0;
  const opacity = exiting ? 0 : 1;

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-4">
      <div
        className="w-full max-w-sm"
        style={{
          transform: `translateX(${translateX}px)`,
          opacity,
          transition: exiting ? 'transform 0.3s ease, opacity 0.3s ease' : 'none',
        }}
      >
        <div className="bg-card border rounded-2xl shadow-xl overflow-hidden">
          {/* Header */}
          <div className="bg-primary/10 px-5 py-3 flex items-center gap-2">
            <Brain className="size-4 text-primary shrink-0" />
            <span className="text-xs font-medium text-primary truncate">{card.courseName}</span>
            <span className="text-xs text-muted-foreground truncate">· {card.className}</span>
            {card.starred && (
              <span className="ml-auto text-sm" title="Importante para el examen">⭐</span>
            )}
          </div>

          {/* Statement */}
          <div className="px-6 pt-6 pb-4">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Verdadero o Falso</p>
            <p className="text-lg font-semibold leading-snug">{card.statement}</p>
          </div>

          {/* Buttons */}
          {answered === null && (
            <div className="px-5 pb-6 flex gap-3">
              <button
                onClick={() => handleAnswer(true)}
                className="flex-1 py-4 rounded-xl border-2 border-green-400 bg-green-50 text-green-700 font-bold text-base hover:bg-green-100 transition-colors"
              >
                Verdadero ✓
              </button>
              <button
                onClick={() => handleAnswer(false)}
                className="flex-1 py-4 rounded-xl border-2 border-red-400 bg-red-50 text-red-700 font-bold text-base hover:bg-red-100 transition-colors"
              >
                Falso ✗
              </button>
            </div>
          )}

          {/* Feedback */}
          {answered !== null && (
            <div className="px-5 pb-5 space-y-3">
              <div className={`px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 ${
                answered ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {answered ? (
                  <><CheckCircle2 className="size-4 shrink-0" /> Correcto — es {card.isTrue ? 'verdadero' : 'falso'}</>
                ) : (
                  <><XCircle className="size-4 shrink-0" /> Incorrecto — es {card.isTrue ? 'verdadero' : 'falso'}</>
                )}
              </div>
              {card.explanation && (
                <p className="text-xs text-muted-foreground leading-relaxed px-1">{card.explanation}</p>
              )}
              <Button onClick={handleNext} className="w-full">
                Siguiente
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ErrorDetectionCard({
  card,
  onAnswer,
}: {
  card: ErrorDetectionItem;
  onAnswer: (correct: boolean) => void;
}) {
  const [input, setInput] = useState('');
  const [checked, setChecked] = useState(false);
  const [correct, setCorrect] = useState(false);
  const [exiting, setExiting] = useState<'left' | 'right' | null>(null);

  const handleCheck = () => {
    if (checked) return;
    const isCorrect = input.trim().toLowerCase() === card.correction.trim().toLowerCase();
    setCorrect(isCorrect);
    setChecked(true);
  };

  const triggerAdvance = (isCorrect: boolean) => {
    const dir = isCorrect ? 'right' : 'left';
    setExiting(dir);
    setTimeout(() => onAnswer(isCorrect), 300);
  };

  const handleNext = () => {
    triggerAdvance(correct);
  };

  const translateX = exiting === 'left' ? -400 : exiting === 'right' ? 400 : 0;
  const opacity = exiting ? 0 : 1;

  const highlightError = (statement: string, errorText: string) => {
    const idx = statement.indexOf(errorText);
    if (idx === -1) return <span>{statement}</span>;
    return (
      <>
        {statement.slice(0, idx)}
        <span className="underline decoration-red-400 decoration-wavy">{errorText}</span>
        {statement.slice(idx + errorText.length)}
      </>
    );
  };

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-4">
      <div
        className="w-full max-w-sm"
        style={{
          transform: `translateX(${translateX}px)`,
          opacity,
          transition: exiting ? 'transform 0.3s ease, opacity 0.3s ease' : 'none',
        }}
      >
        <div className="bg-card border rounded-2xl shadow-xl overflow-hidden">
          {/* Header */}
          <div className="bg-primary/10 px-5 py-3 flex items-center gap-2">
            <Brain className="size-4 text-primary shrink-0" />
            <span className="text-xs font-medium text-primary truncate">{card.courseName}</span>
            <span className="text-xs text-muted-foreground truncate">· {card.className}</span>
            {card.starred && (
              <span className="ml-auto text-sm" title="Importante para el examen">⭐</span>
            )}
          </div>

          {/* Content */}
          <div className="px-6 pt-6 pb-4">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-4">Detectar el Error</p>
            <p className="text-base leading-relaxed font-medium">
              {highlightError(card.statement, card.error)}
            </p>
          </div>

          {/* Input */}
          {!checked && (
            <div className="px-5 pb-4 space-y-3">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
                placeholder="¿Cuál es la corrección?"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                autoFocus
              />
              <Button onClick={handleCheck} className="w-full" disabled={!input.trim()}>
                Verificar
              </Button>
            </div>
          )}

          {/* Feedback */}
          {checked && (
            <div className="px-5 pb-5 space-y-3">
              <div className={`px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 ${
                correct ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {correct ? (
                  <><CheckCircle2 className="size-4 shrink-0" /> Correcto</>
                ) : (
                  <><XCircle className="size-4 shrink-0" /> Corrección: {card.correction}</>
                )}
              </div>
              {card.explanation && (
                <p className="text-xs text-muted-foreground leading-relaxed px-1">{card.explanation}</p>
              )}
              <Button onClick={handleNext} className="w-full">
                Siguiente
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Results screen
// ------------------------------------------------------------------

function ResultsScreen({
  totalCards,
  flashcardsReviewed,
  quizCorrect,
  quizTotal,
  fillInCorrect,
  fillInTotal,
  trueFalseCorrect,
  trueFalseTotal,
  errorDetectionCorrect,
  errorDetectionTotal,
  onRestart,
}: {
  totalCards: number;
  flashcardsReviewed: number;
  quizCorrect: number;
  quizTotal: number;
  fillInCorrect: number;
  fillInTotal: number;
  trueFalseCorrect: number;
  trueFalseTotal: number;
  errorDetectionCorrect: number;
  errorDetectionTotal: number;
  onRestart: () => void;
}) {
  const combinedCorrect = quizCorrect + fillInCorrect + trueFalseCorrect + errorDetectionCorrect;
  const combinedTotal = quizTotal + fillInTotal + trueFalseTotal + errorDetectionTotal;
  const percentage = combinedTotal > 0 ? Math.round((combinedCorrect / combinedTotal) * 100) : null;

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="text-5xl">🎉</div>
        <div>
          <h2 className="text-2xl font-bold">Sesión completada</h2>
          <p className="text-muted-foreground mt-1 text-sm">Has repasado {totalCards} tarjetas</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-card border rounded-xl p-4">
            <p className="text-3xl font-bold text-primary">{flashcardsReviewed}</p>
            <p className="text-xs text-muted-foreground mt-1">Flashcards repasadas</p>
          </div>
          {quizTotal > 0 && (
            <div className="bg-card border rounded-xl p-4">
              <p className="text-3xl font-bold text-primary">
                {quizCorrect}/{quizTotal}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Quiz correctos</p>
            </div>
          )}
          {fillInTotal > 0 && (
            <div className="bg-card border rounded-xl p-4">
              <p className="text-3xl font-bold text-primary">
                {fillInCorrect}/{fillInTotal}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Completar correctos</p>
            </div>
          )}
          {trueFalseTotal > 0 && (
            <div className="bg-card border rounded-xl p-4">
              <p className="text-3xl font-bold text-primary">
                {trueFalseCorrect}/{trueFalseTotal}
              </p>
              <p className="text-xs text-muted-foreground mt-1">V/F correctos</p>
            </div>
          )}
          {errorDetectionTotal > 0 && (
            <div className="bg-card border rounded-xl p-4">
              <p className="text-3xl font-bold text-primary">
                {errorDetectionCorrect}/{errorDetectionTotal}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Errores correctos</p>
            </div>
          )}
          {percentage !== null && (
            <div className="bg-card border rounded-xl p-4 col-span-2">
              <p className="text-3xl font-bold" style={{ color: percentage >= 70 ? '#16a34a' : percentage >= 40 ? '#ea580c' : '#dc2626' }}>
                {percentage}%
              </p>
              <p className="text-xs text-muted-foreground mt-1">Precisión general</p>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <Button onClick={onRestart} className="w-full">
            Repetir sesión
          </Button>
          <Link to="/courses">
            <Button variant="outline" className="w-full">
              Volver a mis materias
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Empty state
// ------------------------------------------------------------------

function EmptyState({ courseId }: { courseId: number | null }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
      <BookOpen className="size-12 text-muted-foreground mb-4" />
      <h2 className="text-xl font-semibold">Sin contenido todavía</h2>
      <p className="text-muted-foreground mt-2 text-sm max-w-xs">
        No hay flashcards ni preguntas generadas.{' '}
        {courseId
          ? 'Ve a las clases de esta materia y genera el material de estudio primero.'
          : 'Ve a tus materias y genera el material de estudio para algunas clases.'}
      </p>
      <Link to={courseId ? `/courses/${courseId}` : '/courses'} className="mt-6">
        <Button>
          <ArrowLeft className="size-4 mr-2" />
          Ir a mis materias
        </Button>
      </Link>
    </div>
  );
}

// ------------------------------------------------------------------
// Main Learn page
// ------------------------------------------------------------------

export function Learn() {
  const [searchParams] = useSearchParams();
  const courseIdParam = searchParams.get('courseId');
  const courseId = courseIdParam ? Number(courseIdParam) : null;

  // State
  const [deck, setDeck] = useState<DeckCard[] | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [flashcardsReviewed, setFlashcardsReviewed] = useState(0);
  const [quizCorrect, setQuizCorrect] = useState(0);
  const [quizTotal, setQuizTotal] = useState(0);
  const [fillInCorrect, setFillInCorrect] = useState(0);
  const [fillInTotal, setFillInTotal] = useState(0);
  const [trueFalseCorrect, setTrueFalseCorrect] = useState(0);
  const [trueFalseTotal, setTrueFalseTotal] = useState(0);
  const [errorDetectionCorrect, setErrorDetectionCorrect] = useState(0);
  const [errorDetectionTotal, setErrorDetectionTotal] = useState(0);
  const [finished, setFinished] = useState(false);
  const [deckSeed, setDeckSeed] = useState(0); // used to re-shuffle

  // Fetch all collections for the "all courses" case
  const { data: allCollections, isLoading: collectionsLoading } = useQuery({
    queryKey: ['collections'],
    queryFn: getCollections,
  });

  // Determine which collections to load
  const collectionsToLoad: CollectionEntry[] = courseId
    ? (allCollections?.filter((c) => c.id === courseId) ?? [])
    : (allCollections ?? []);

  // Fetch detail for each collection to get its items (classes)
  const collectionQueries = useQuery({
    queryKey: ['collection-detail-batch', collectionsToLoad.map((c) => c.id).sort()],
    queryFn: async () => {
      return Promise.all(collectionsToLoad.map((c) => getCollection(c.id)));
    },
    enabled: collectionsToLoad.length > 0,
  });

  const isLoading = collectionsLoading || collectionQueries.isLoading;

  // Build the class list from fetched collections
  const classMetas: ClassMeta[] = [];
  if (collectionQueries.data) {
    for (const colDetail of collectionQueries.data) {
      const courseName = allCollections?.find((c) => c.id === colDetail.id)?.name ?? colDetail.name;
      for (const item of colDetail.items) {
        classMetas.push({ item, courseName });
      }
    }
  }

  // Fetch content for all classes once we have their ids
  const classIds = classMetas.map((cm) => cm.item.id);

  const contentQuery = useQuery({
    queryKey: ['learn-content', classIds.sort().join(','), deckSeed],
    queryFn: async () => {
      const results = await Promise.all(
        classMetas.map(async (cm) => {
          const [fcRes, qaRes, fibRes, tfRes, edRes] = await Promise.allSettled([
            getFlashcards(cm.item.id),
            getQA(cm.item.id),
            getFillInBlank(cm.item.id),
            getTrueFalse(cm.item.id),
            getErrorDetection(cm.item.id),
          ]);
          return {
            meta: cm,
            flashcards: fcRes.status === 'fulfilled' ? fcRes.value.cards : [],
            qaPairs: qaRes.status === 'fulfilled' ? qaRes.value.pairs : [],
            fillInBlanks: fibRes.status === 'fulfilled' ? fibRes.value.items : [],
            trueFalseItems: tfRes.status === 'fulfilled' ? tfRes.value.items : [],
            errorDetectionItems: edRes.status === 'fulfilled' ? edRes.value.items : [],
          };
        })
      );
      return results;
    },
    enabled: classMetas.length > 0,
  });

  // Build deck when content is ready
  useEffect(() => {
    if (!contentQuery.data) return;

    // Collect all answers globally for distractors
    const allAnswers = contentQuery.data.flatMap((r) => r.qaPairs.map((p) => p.answer));

    const allCards: DeckCard[] = [];
    for (const result of contentQuery.data) {
      const cards = buildDeck(result.meta, result.flashcards, result.qaPairs, result.fillInBlanks, allAnswers, result.trueFalseItems, result.errorDetectionItems);
      allCards.push(...cards);
    }

    // Starred cards across all classes come first, each group shuffled separately
    const starredAll = allCards.filter((c) => c.starred);
    const regularAll = allCards.filter((c) => !c.starred);
    setDeck([...shuffle(starredAll), ...shuffle(regularAll)]);
    setCurrentIndex(0);
    setFlashcardsReviewed(0);
    setQuizCorrect(0);
    setQuizTotal(0);
    setFillInCorrect(0);
    setFillInTotal(0);
    setTrueFalseCorrect(0);
    setTrueFalseTotal(0);
    setErrorDetectionCorrect(0);
    setErrorDetectionTotal(0);
    setFinished(false);
  }, [contentQuery.data]);

  // Log the session when it finishes (fire-and-forget, separate call per activity type)
  useEffect(() => {
    if (!finished) return;
    if (flashcardsReviewed > 0) logActivity('flashcard', flashcardsReviewed, flashcardsReviewed);
    if (quizTotal > 0) logActivity('quiz', quizTotal, quizCorrect);
    if (fillInTotal > 0) logActivity('fill_in_blank', fillInTotal, fillInCorrect);
    if (trueFalseTotal > 0) logActivity('true_false', trueFalseTotal, trueFalseCorrect);
    if (errorDetectionTotal > 0) logActivity('error_detection', errorDetectionTotal, errorDetectionCorrect);
  }, [finished]); // eslint-disable-line react-hooks/exhaustive-deps

  const advance = useCallback(() => {
    setCurrentIndex((prev) => {
      if (deck && prev + 1 >= deck.length) {
        setFinished(true);
        return prev;
      }
      return prev + 1;
    });
  }, [deck]);

  const handleFlashcardSwipeLeft = useCallback(() => {
    setFlashcardsReviewed((n) => n + 1);
    advance();
  }, [advance]);

  const handleFlashcardSwipeRight = useCallback(() => {
    setFlashcardsReviewed((n) => n + 1);
    advance();
  }, [advance]);

  const handleQuizAnswer = useCallback((correct: boolean) => {
    setQuizTotal((n) => n + 1);
    if (correct) setQuizCorrect((n) => n + 1);
    advance();
  }, [advance]);

  const handleFillInAnswer = useCallback((correct: boolean) => {
    setFillInTotal((n) => n + 1);
    if (correct) setFillInCorrect((n) => n + 1);
    advance();
  }, [advance]);

  const handleTrueFalseAnswer = useCallback((correct: boolean) => {
    setTrueFalseTotal((n) => n + 1);
    if (correct) setTrueFalseCorrect((n) => n + 1);
    advance();
  }, [advance]);

  const handleErrorDetectionAnswer = useCallback((correct: boolean) => {
    setErrorDetectionTotal((n) => n + 1);
    if (correct) setErrorDetectionCorrect((n) => n + 1);
    advance();
  }, [advance]);

  const handleRestart = () => {
    setDeckSeed((s) => s + 1);
  };

  // Loading state
  if (isLoading || (classMetas.length > 0 && contentQuery.isLoading)) {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center bg-background z-50">
        <Loader2 className="size-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground text-sm">Preparando tu sesión de estudio...</p>
      </div>
    );
  }

  // Empty state — no collections or no content
  const hasContent = deck && deck.length > 0;

  if (!isLoading && !contentQuery.isLoading && !hasContent) {
    return (
      <div className="fixed inset-0 bg-background z-50">
        <EmptyState courseId={courseId} />
      </div>
    );
  }

  if (!deck) return null;

  const progress = finished ? 100 : Math.round((currentIndex / deck.length) * 100);
  const currentCard = deck[currentIndex];

  return (
    <div className="fixed inset-0 bg-background z-50 flex flex-col overflow-hidden">
      {/* Top bar */}
      <div className="shrink-0 px-4 pt-3 pb-2 flex items-center gap-3">
        <Link to="/courses" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-5" />
        </Link>
        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-xs text-muted-foreground shrink-0 tabular-nums">
          {finished ? deck.length : currentIndex + 1}/{deck.length}
        </span>
      </div>

      {/* Card area */}
      <div className="flex-1 relative">
        {finished ? (
          <ResultsScreen
            totalCards={deck.length}
            flashcardsReviewed={flashcardsReviewed}
            quizCorrect={quizCorrect}
            quizTotal={quizTotal}
            fillInCorrect={fillInCorrect}
            fillInTotal={fillInTotal}
            trueFalseCorrect={trueFalseCorrect}
            trueFalseTotal={trueFalseTotal}
            errorDetectionCorrect={errorDetectionCorrect}
            errorDetectionTotal={errorDetectionTotal}
            onRestart={handleRestart}
          />
        ) : currentCard.type === 'flashcard' ? (
          <FlashcardCard
            key={currentCard.id}
            card={currentCard}
            onSwipeLeft={handleFlashcardSwipeLeft}
            onSwipeRight={handleFlashcardSwipeRight}
          />
        ) : currentCard.type === 'quiz' ? (
          <QuizCard
            key={currentCard.id}
            card={currentCard}
            onAnswer={handleQuizAnswer}
          />
        ) : currentCard.type === 'fill_in_blank' ? (
          <FillInBlankCard
            key={currentCard.id}
            card={currentCard}
            onAnswer={handleFillInAnswer}
          />
        ) : currentCard.type === 'true_false' ? (
          <TrueFalseCard
            key={currentCard.id}
            card={currentCard}
            onAnswer={handleTrueFalseAnswer}
          />
        ) : (
          <ErrorDetectionCard
            key={currentCard.id}
            card={currentCard}
            onAnswer={handleErrorDetectionAnswer}
          />
        )}
      </div>
    </div>
  );
}
