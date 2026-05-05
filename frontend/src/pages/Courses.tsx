import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Loader2, Plus, X } from 'lucide-react';
import { getCollections, createCollection, type CollectionEntry } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

function NewCourseDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      createCollection({ name: name.trim(), collection_type: 'course' }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['collections'] });
      setName('');
      onCreated(data.id);
    },
  });

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card rounded-xl border shadow-xl w-full max-w-sm mx-4 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Nueva Materia</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) mutation.mutate();
          }}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor="course-name">Nombre de la materia</Label>
            <Input
              id="course-name"
              placeholder="e.g. Cálculo Diferencial"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          {mutation.isError && (
            <p className="text-xs text-destructive">
              {(mutation.error as Error).message}
            </p>
          )}
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={mutation.isPending || !name.trim()}
            >
              {mutation.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin mr-2" />
                  Creando...
                </>
              ) : (
                'Crear'
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CourseCard({ course, onClick }: { course: CollectionEntry; onClick: () => void }) {
  const updatedAt = new Date(course.updated_at).toLocaleDateString('es-MX', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });

  return (
    <Card
      className="cursor-pointer hover:border-primary/60 hover:shadow-md transition-all py-0"
      onClick={onClick}
    >
      <CardHeader className="p-5 pb-3">
        <div className="flex items-start gap-3">
          <div className="size-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <BookOpen className="size-4 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <CardTitle className="text-sm font-semibold truncate leading-tight">
              {course.name}
            </CardTitle>
            {course.description && (
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                {course.description}
              </p>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-5 pb-5">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {course.item_count} clase{course.item_count !== 1 ? 's' : ''}
          </span>
          <span>Actualizado: {updatedAt}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function Courses() {
  const navigate = useNavigate();
  const [showModal, setShowModal] = useState(false);

  const { data: collections, isLoading, error } = useQuery({
    queryKey: ['collections'],
    queryFn: getCollections,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Mis Materias</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Organiza tus clases por materia
          </p>
        </div>
        <Button onClick={() => setShowModal(true)}>
          <Plus className="size-4 mr-2" />
          Nueva Materia
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">
          Error al cargar materias: {(error as Error).message}
        </p>
      )}

      {!isLoading && !error && collections && collections.length === 0 && (
        <div className="rounded-lg border-2 border-dashed p-12 text-center">
          <BookOpen className="mx-auto size-10 text-muted-foreground/40 mb-3" />
          <p className="text-muted-foreground font-medium">No hay materias todavía</p>
          <p className="text-xs text-muted-foreground mt-1">
            Crea tu primera materia para empezar a organizar tus clases.
          </p>
          <Button className="mt-4" onClick={() => setShowModal(true)}>
            <Plus className="size-4 mr-2" />
            Nueva Materia
          </Button>
        </div>
      )}

      {collections && collections.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {collections.map((course) => (
            <CourseCard
              key={course.id}
              course={course}
              onClick={() => navigate(`/courses/${course.id}`)}
            />
          ))}
        </div>
      )}

      <NewCourseDialog
        open={showModal}
        onClose={() => setShowModal(false)}
        onCreated={(id) => {
          setShowModal(false);
          navigate(`/courses/${id}`);
        }}
      />
    </div>
  );
}
