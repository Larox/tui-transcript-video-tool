import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, BookOpen, CheckCircle2, FileText, Loader2, Plus, Sparkles, Video, XCircle } from 'lucide-react';
import { getCollection, type CollectionItemEntry } from '@/api/client';
import { startGeneration } from '@/api/learning';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { MateriaFiles } from '@/components/MateriaFiles';
import { useState } from 'react';

type Tab = 'clases' | 'archivos';

const TABS: { id: Tab; label: string; icon: typeof BookOpen }[] = [
  { id: 'clases', label: 'Clases', icon: BookOpen },
  { id: 'archivos', label: 'Archivos', icon: FileText },
];

function statusBadge(item: CollectionItemEntry) {
  if (item.output_path) {
    return (
      <Badge className="bg-green-100 text-green-700 border-green-200">
        Transcrito
      </Badge>
    );
  }
  return (
    <Badge className="bg-gray-100 text-gray-500 border-gray-200">
      Pendiente
    </Badge>
  );
}

function ClassCard({
  item,
  index,
  onClick,
}: {
  item: CollectionItemEntry;
  index: number;
  onClick: () => void;
}) {
  const date = new Date(item.processed_at).toLocaleDateString('es-MX', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });

  return (
    <Card
      className="cursor-pointer hover:border-primary/60 hover:shadow-md transition-all py-0"
      onClick={onClick}
    >
      <CardContent className="px-5 py-4 flex items-center gap-4">
        <div className="size-8 rounded-full bg-muted flex items-center justify-center shrink-0 text-xs font-mono text-muted-foreground">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{item.output_title}</p>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">
            {item.source_path.split('/').pop()}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {statusBadge(item)}
          <span className="text-xs text-muted-foreground">{date}</span>
        </div>
      </CardContent>
    </Card>
  );
}

type GenStatus = 'pending' | 'running' | 'done' | 'error';
interface ClassGenState { id: number; name: string; status: GenStatus }

export function CourseDetail() {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const [genStates, setGenStates] = useState<ClassGenState[] | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('clases');

  const id = Number(courseId);

  const { data: collection, isLoading, error } = useQuery({
    queryKey: ['collection', id],
    queryFn: () => getCollection(id),
    enabled: !isNaN(id),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !collection) {
    return (
      <div className="space-y-4">
        <Link
          to="/courses"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Mis Materias
        </Link>
        <p className="text-sm text-destructive">
          {error ? (error as Error).message : 'Materia no encontrada'}
        </p>
      </div>
    );
  }

  const handleGenerateAll = async () => {
    if (!collection || collection.items.length === 0) return;
    const items = collection.items;
    const initial = items.map((item) => ({ id: item.id, name: item.output_title, status: 'pending' as GenStatus }));
    setGenStates(initial);

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      setGenStates((prev) => prev!.map((s) => s.id === item.id ? { ...s, status: 'running' } : s));
      await new Promise<void>((resolve) => {
        const cancel = startGeneration(
          item.id,
          (event) => {
            if (event.type === 'complete') {
              setGenStates((prev) => prev!.map((s) => s.id === item.id ? { ...s, status: 'done' } : s));
              cancel();
              resolve();
            }
          },
          () => {
            setGenStates((prev) => prev!.map((s) => s.id === item.id ? { ...s, status: 'error' } : s));
            resolve();
          }
        );
      });
    }
  };

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
          <div className="flex items-start gap-3">
            <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <BookOpen className="size-5 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">{collection.name}</h1>
              {collection.description && (
                <p className="text-sm text-muted-foreground mt-1">
                  {collection.description}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {collection.items.length > 0 && (
              <Button
                variant="outline"
                onClick={handleGenerateAll}
                disabled={genStates !== null && genStates.some((s) => s.status === 'running')}
              >
                <Sparkles className="size-4 mr-2" />
                Generar Todo
              </Button>
            )}
            <Button onClick={() => navigate(`/upload?courseId=${id}`)}>
              <Plus className="size-4 mr-2" />
              Subir Clase
            </Button>
          </div>
        </div>
      </div>

      {/* Batch generation progress */}
      {genStates && (
        <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
          <div className="flex items-center justify-between mb-1">
            <p className="text-sm font-medium">Generando material de estudio</p>
            {genStates.every((s) => s.status === 'done' || s.status === 'error') && (
              <button type="button" onClick={() => setGenStates(null)} className="text-xs text-muted-foreground hover:text-foreground">
                Cerrar
              </button>
            )}
          </div>
          {genStates.map((s) => (
            <div key={s.id} className="flex items-center gap-2 text-sm">
              {s.status === 'done' && <CheckCircle2 className="size-4 text-green-500 shrink-0" />}
              {s.status === 'running' && <Loader2 className="size-4 animate-spin text-primary shrink-0" />}
              {s.status === 'error' && <XCircle className="size-4 text-destructive shrink-0" />}
              {s.status === 'pending' && <div className="size-4 rounded-full border-2 border-muted shrink-0" />}
              <span className={s.status === 'done' ? 'text-muted-foreground line-through' : s.status === 'running' ? 'font-medium' : 'text-muted-foreground'}>
                {s.name}
              </span>
            </div>
          ))}
        </div>
      )}

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

        {activeTab === 'clases' && (
          <>
            {collection.items.length === 0 ? (
              <div className="rounded-lg border-2 border-dashed p-12 text-center">
                <Video className="mx-auto size-10 text-muted-foreground/40 mb-3" />
                <p className="text-muted-foreground font-medium">No hay clases todavía</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Sube tu primera clase para empezar a estudiar.
                </p>
                <Button
                  className="mt-4"
                  onClick={() => navigate(`/upload?courseId=${id}`)}
                >
                  <Plus className="size-4 mr-2" />
                  Subir Clase
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  {collection.items.length} clase{collection.items.length !== 1 ? 's' : ''}
                </p>
                {collection.items.map((item, idx) => (
                  <ClassCard
                    key={item.id}
                    item={item}
                    index={idx}
                    onClick={() => navigate(`/classes/${item.id}`)}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {activeTab === 'archivos' && <MateriaFiles collectionId={collection.id} />}
      </div>
    </div>
  );
}
