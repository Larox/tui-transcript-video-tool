/**
 * Stats.tsx — Full statistics page (SEB-90)
 *
 * Sections: header metrics, 30-day heatmap, recent sessions table, achievements.
 * Route: /stats
 */

import { useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { getStatsSummary, type DailySessionEntry } from '@/api/learning';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function heatColor(cards: number): string {
  if (cards === 0) return '#e5e7eb';       // gray-200
  if (cards <= 10) return '#86efac';       // green-300
  return '#16a34a';                        // green-600
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('es-MX', { month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

// ------------------------------------------------------------------
// Header metric cards
// ------------------------------------------------------------------

function MetricCard({ value, label, icon }: { value: string; label: string; icon?: string }) {
  return (
    <Card className="py-4">
      <CardContent className="px-5 text-center">
        <p className="text-3xl font-bold tabular-nums">
          {icon && <span className="mr-1">{icon}</span>}
          {value}
        </p>
        <p className="text-xs text-muted-foreground mt-1">{label}</p>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------
// 30-day heatmap
// ------------------------------------------------------------------

function Heatmap({ sessions }: { sessions: DailySessionEntry[] }) {
  // Build a lookup map date -> cards_reviewed
  const map = new Map<string, number>();
  for (const s of sessions) {
    map.set(s.date, s.cards_reviewed);
  }

  // Generate last 30 days
  const today = new Date();
  const days: Array<{ date: string; cards: number }> = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const iso = d.toISOString().split('T')[0];
    days.push({ date: iso, cards: map.get(iso) ?? 0 });
  }

  return (
    <div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(10, 1fr)',
          gap: '4px',
        }}
      >
        {days.map(({ date, cards }) => (
          <div
            key={date}
            title={`${formatDate(date)}: ${cards} tarjetas`}
            style={{
              width: '100%',
              paddingTop: '100%',
              borderRadius: '3px',
              backgroundColor: heatColor(cards),
              cursor: 'default',
            }}
          />
        ))}
      </div>
      <div className="flex items-center gap-2 mt-3 text-xs text-muted-foreground">
        <span>Menos</span>
        {[0, 5, 15].map((v) => (
          <div
            key={v}
            style={{ width: 12, height: 12, borderRadius: 2, backgroundColor: heatColor(v) }}
          />
        ))}
        <span>Más</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Recent sessions table
// ------------------------------------------------------------------

function RecentSessions({ sessions }: { sessions: DailySessionEntry[] }) {
  const last10 = [...sessions].reverse().slice(0, 10);

  if (last10.length === 0) {
    return <p className="text-sm text-muted-foreground">No hay sesiones registradas aún.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="text-left py-2 pr-4 font-medium">Fecha</th>
            <th className="text-right py-2 pr-4 font-medium">Tarjetas</th>
            <th className="text-right py-2 font-medium">Quiz</th>
          </tr>
        </thead>
        <tbody>
          {last10.map((s) => {
            const score =
              s.quizzes_total > 0
                ? `${s.quizzes_correct}/${s.quizzes_total} (${Math.round((s.quizzes_correct / s.quizzes_total) * 100)}%)`
                : '—';
            return (
              <tr key={s.date} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                <td className="py-2 pr-4 tabular-nums">{formatDate(s.date)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{s.cards_reviewed}</td>
                <td className="py-2 text-right tabular-nums">{score}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------
// Achievements
// ------------------------------------------------------------------

interface Achievement {
  id: string;
  label: string;
  icon: string;
  unlocked: boolean;
  requirement: string;
}

function buildAchievements(data: {
  total_sessions: number;
  longest_streak: number;
  total_cards_reviewed: number;
  total_quizzes_total: number;
  total_quizzes_correct: number;
}): Achievement[] {
  const quizRate =
    data.total_quizzes_total > 0
      ? data.total_quizzes_correct / data.total_quizzes_total
      : 0;

  return [
    {
      id: 'first-session',
      label: 'Primera sesión',
      icon: '✅',
      unlocked: data.total_sessions >= 1,
      requirement: 'Completa tu primera sesión de estudio',
    },
    {
      id: 'streak-3',
      label: 'Racha de 3 días',
      icon: '🔥',
      unlocked: data.longest_streak >= 3,
      requirement: 'Mantén una racha de 3 días',
    },
    {
      id: 'streak-7',
      label: 'Racha de 7 días',
      icon: '🔥🔥',
      unlocked: data.longest_streak >= 7,
      requirement: 'Mantén una racha de 7 días',
    },
    {
      id: '100-cards',
      label: '100 tarjetas',
      icon: '🎯',
      unlocked: data.total_cards_reviewed >= 100,
      requirement: 'Revisa 100 tarjetas en total',
    },
    {
      id: 'quiz-master',
      label: 'Maestro del quiz',
      icon: '🧠',
      unlocked: data.total_quizzes_total >= 50 && quizRate >= 0.8,
      requirement: '50+ quizzes con 80% de acierto',
    },
  ];
}

function AchievementBadge({ achievement }: { achievement: Achievement }) {
  return (
    <div
      className={`rounded-xl border p-4 flex items-center gap-3 transition-opacity ${
        achievement.unlocked ? '' : 'opacity-40'
      }`}
    >
      <span className="text-2xl shrink-0">{achievement.icon}</span>
      <div className="min-w-0">
        <p className={`text-sm font-semibold ${achievement.unlocked ? '' : 'text-muted-foreground'}`}>
          {achievement.label}
        </p>
        {!achievement.unlocked && (
          <p className="text-xs text-muted-foreground truncate">{achievement.requirement}</p>
        )}
      </div>
      {achievement.unlocked && (
        <span className="ml-auto text-xs text-green-600 font-medium shrink-0">Logrado</span>
      )}
    </div>
  );
}

// ------------------------------------------------------------------
// Main Stats page
// ------------------------------------------------------------------

export function Stats() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['stats-summary'],
    queryFn: getStatsSummary,
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <p className="text-sm text-destructive">
        Error al cargar estadísticas.
      </p>
    );
  }

  const quizPct =
    data.total_quizzes_total > 0
      ? Math.round((data.total_quizzes_correct / data.total_quizzes_total) * 100)
      : null;

  const achievements = buildAchievements(data);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Estadísticas</h1>
        <p className="text-sm text-muted-foreground mt-1">Tu progreso y logros de estudio</p>
      </div>

      {/* Header metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard value={String(data.current_streak)} label="Racha actual" icon="🔥" />
        <MetricCard value={String(data.total_sessions)} label="Sesiones totales" />
        <MetricCard value={String(data.total_cards_reviewed)} label="Tarjetas revisadas" />
        <MetricCard
          value={quizPct !== null ? `${quizPct}%` : '—'}
          label="Acierto en quizzes"
        />
      </div>

      {/* Heatmap */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Actividad — últimos 30 días</CardTitle>
        </CardHeader>
        <CardContent>
          <Heatmap sessions={data.sessions_last_30_days} />
        </CardContent>
      </Card>

      {/* Recent sessions table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Tendencia reciente</CardTitle>
        </CardHeader>
        <CardContent>
          <RecentSessions sessions={data.sessions_last_30_days} />
        </CardContent>
      </Card>

      {/* Achievements */}
      <div>
        <h2 className="text-base font-semibold mb-3">Logros</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {achievements.map((a) => (
            <AchievementBadge key={a.id} achievement={a} />
          ))}
        </div>
      </div>
    </div>
  );
}
