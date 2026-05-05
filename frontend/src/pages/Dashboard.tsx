import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Loader2 } from 'lucide-react';
import { getDashboardAlerts, dismissAlert, getStatsSummary, type AlertEntry, type Urgency } from '@/api/learning';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const URGENCY_ORDER: Record<Urgency, number> = { high: 0, medium: 1, low: 2 };

function urgencyBadge(urgency: Urgency) {
  if (urgency === 'high') {
    return (
      <Badge className="bg-red-100 text-red-700 border-red-200">
        <AlertTriangle className="size-3" />
        Alta
      </Badge>
    );
  }
  if (urgency === 'medium') {
    return (
      <Badge className="bg-yellow-100 text-yellow-700 border-yellow-200">
        <Clock className="size-3" />
        Media
      </Badge>
    );
  }
  return (
    <Badge className="bg-gray-100 text-gray-600 border-gray-200">
      Baja
    </Badge>
  );
}

function formatExtractedDate(raw: string): string {
  try {
    const d = new Date(raw);
    return d.toLocaleDateString('es-MX', { month: 'long', day: 'numeric' });
  } catch {
    return raw;
  }
}

function AlertCard({
  alert,
  onDismiss,
  dismissing,
}: {
  alert: AlertEntry;
  onDismiss: () => void;
  dismissing: boolean;
}) {
  return (
    <Card className="py-4">
      <CardContent className="px-4 flex items-start gap-4">
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            {urgencyBadge(alert.urgency)}
            {alert.extracted_date && (
              <span className="text-xs text-muted-foreground">
                Vence: {formatExtractedDate(alert.extracted_date)}
              </span>
            )}
          </div>
          <p className="text-sm leading-relaxed">{alert.text}</p>
          <p className="text-xs text-muted-foreground">Clase #{alert.video_id}</p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0 text-muted-foreground hover:text-foreground"
          onClick={onDismiss}
          disabled={dismissing}
          title="Dismiss alert"
        >
          {dismissing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <CheckCircle2 className="size-4" />
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

function StreakWidget() {
  const { data } = useQuery({
    queryKey: ['stats-summary'],
    queryFn: getStatsSummary,
    staleTime: 60_000,
  });

  if (!data) return null;

  const { current_streak, today_items, daily_goal } = data;
  const progress = Math.min(today_items / daily_goal, 1);
  const goalMet = today_items >= daily_goal;

  return (
    <Card className="py-3">
      <CardContent className="px-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-lg">🔥</span>
            <span className="text-xl font-bold tabular-nums">{current_streak}</span>
            <span className="text-xs text-muted-foreground">
              {current_streak === 1 ? 'día' : 'días'}
            </span>
          </div>
          <div className="flex-1 space-y-1">
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${progress * 100}%`,
                  backgroundColor: goalMet ? '#16a34a' : '#f97316',
                }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {goalMet
                ? '¡Meta completada!'
                : `Te faltan ${daily_goal - today_items} tarjetas hoy`}
              {' '}·{' '}{today_items}/{daily_goal}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-alerts'],
    queryFn: getDashboardAlerts,
  });

  const [dismissing, setDismissing] = useState<Set<number>>(new Set());
  // Optimistic: track locally dismissed ids
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());

  const handleDismiss = async (alert: AlertEntry) => {
    setDismissing((prev) => new Set(prev).add(alert.id));
    // Optimistic removal
    setDismissed((prev) => new Set(prev).add(alert.id));
    try {
      await dismissAlert(alert.video_id, alert.id);
      queryClient.invalidateQueries({ queryKey: ['dashboard-alerts'] });
    } catch {
      // Revert on failure
      setDismissed((prev) => {
        const next = new Set(prev);
        next.delete(alert.id);
        return next;
      });
    } finally {
      setDismissing((prev) => {
        const next = new Set(prev);
        next.delete(alert.id);
        return next;
      });
    }
  };

  const alerts = (data?.alerts ?? [])
    .filter((a) => !dismissed.has(a.id))
    .sort(
      (a, b) =>
        URGENCY_ORDER[a.urgency] - URGENCY_ORDER[b.urgency] ||
        (a.extracted_date ?? '').localeCompare(b.extracted_date ?? '')
    );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Tareas y compromisos pendientes en todas tus materias
        </p>
      </div>

      <StreakWidget />

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">
          Error al cargar alertas: {(error as Error).message}
        </p>
      )}

      {!isLoading && !error && alerts.length === 0 && (
        <div className="rounded-lg border-2 border-dashed p-12 text-center">
          <CheckCircle2 className="mx-auto size-10 text-green-500/60 mb-3" />
          <p className="text-muted-foreground font-medium">No hay alertas pendientes — ¡todo al día!</p>
          <p className="text-xs text-muted-foreground mt-1">
            Las tareas y fechas importantes de tus clases aparecerán aquí.
          </p>
        </div>
      )}

      {alerts.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {alerts.length} alerta{alerts.length !== 1 ? 's' : ''} pendiente{alerts.length !== 1 ? 's' : ''}
          </p>
          {alerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onDismiss={() => handleDismiss(alert)}
              dismissing={dismissing.has(alert.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
