import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  BookOpen,
  ChevronRight,
  GraduationCap,
  Loader2,
  Plus,
  Search,
  Trash2,
  Users,
  X,
  FileText,
  Tag,
} from 'lucide-react';
import {
  getCollections,
  getCollection,
  createCollection,
  deleteCollection,
  addCollectionItems,
  removeCollectionItem,
  getVideos,
  searchTranscripts,
  getTags,
  createTag,
  addVideoTag,
  type CollectionEntry,
  type CollectionItemEntry,
  type VideoEntry,
  type SearchResultEntry,
  type TagEntry,
} from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';

const COLLECTION_TYPES: Record<string, { label: string; icon: typeof BookOpen }> = {
  course: { label: 'Course', icon: GraduationCap },
  mentorship: { label: 'Mentorship', icon: Users },
  tutorship: { label: 'Tutorship', icon: BookOpen },
  academic: { label: 'Academic', icon: GraduationCap },
  other: { label: 'Other', icon: BookOpen },
};

function TypeBadge({ type }: { type: string }) {
  const config = COLLECTION_TYPES[type] || COLLECTION_TYPES.other;
  const Icon = config.icon;
  return (
    <Badge variant="secondary" className="gap-1 text-xs">
      <Icon className="size-3" />
      {config.label}
    </Badge>
  );
}

function TagPill({ tag, onRemove }: { tag: TagEntry; onRemove?: () => void }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
      style={{ backgroundColor: tag.color + '20', color: tag.color, border: `1px solid ${tag.color}40` }}
    >
      {tag.name}
      {onRemove && (
        <button type="button" onClick={onRemove} className="hover:opacity-70">
          <X className="size-3" />
        </button>
      )}
    </span>
  );
}

function SearchBar() {
  const [query, setQuery] = useState('');
  const [showResults, setShowResults] = useState(false);

  const { data: results, isLoading } = useQuery({
    queryKey: ['search', query],
    queryFn: () => searchTranscripts(query),
    enabled: query.length >= 2,
  });

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search transcripts..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShowResults(true);
          }}
          onFocus={() => query.length >= 2 && setShowResults(true)}
          onBlur={() => setTimeout(() => setShowResults(false), 200)}
          className="pl-10"
        />
      </div>
      {showResults && query.length >= 2 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-lg max-h-80 overflow-y-auto">
          {isLoading && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            </div>
          )}
          {results && results.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">No results found.</p>
          )}
          {results?.map((r: SearchResultEntry) => (
            <div
              key={r.video_id}
              className="px-4 py-3 hover:bg-accent cursor-pointer border-b last:border-b-0"
            >
              <p className="text-sm font-medium">{r.output_title}</p>
              <p
                className="text-xs text-muted-foreground mt-1 [&_mark]:bg-yellow-200 [&_mark]:text-foreground"
                dangerouslySetInnerHTML={{ __html: r.excerpt }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AddVideoSheet({
  collectionId,
  open,
  onClose,
}: {
  collectionId: number;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: videos, isLoading } = useQuery({
    queryKey: ['videos'],
    queryFn: getVideos,
    enabled: open,
  });

  const addMutation = useMutation({
    mutationFn: (videoIds: number[]) => addCollectionItems(collectionId, videoIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collection', collectionId] });
      queryClient.invalidateQueries({ queryKey: ['collections'] });
      onClose();
    },
  });

  const [selected, setSelected] = useState<Set<number>>(new Set());

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="flex flex-col w-full sm:max-w-md gap-4">
        <SheetHeader>
          <SheetTitle>Add Transcripts</SheetTitle>
          <SheetDescription>Select transcripts to add to this collection</SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto space-y-1">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          )}
          {videos?.map((v: VideoEntry) => (
            <button
              key={v.id}
              type="button"
              onClick={() => toggle(v.id)}
              className={`w-full text-left rounded-md border px-3 py-2 text-sm transition-colors ${
                selected.has(v.id) ? 'border-primary bg-primary/5' : 'hover:bg-accent'
              }`}
            >
              <p className="font-medium truncate">{v.output_title}</p>
              <p className="text-xs text-muted-foreground truncate mt-0.5">
                {v.source_path.split('/').pop()}
              </p>
            </button>
          ))}
          {videos && videos.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">
              No transcripts available. Process some videos first.
            </p>
          )}
        </div>
        {selected.size > 0 && (
          <Button
            onClick={() => addMutation.mutate([...selected])}
            disabled={addMutation.isPending}
          >
            {addMutation.isPending ? 'Adding...' : `Add ${selected.size} transcript(s)`}
          </Button>
        )}
      </SheetContent>
    </Sheet>
  );
}

function TagManager({ videoId }: { videoId: number }) {
  const queryClient = useQueryClient();
  const { data: allTags } = useQuery({
    queryKey: ['tags'],
    queryFn: getTags,
  });
  const [showAdd, setShowAdd] = useState(false);
  const [newTagName, setNewTagName] = useState('');

  const createTagMutation = useMutation({
    mutationFn: (name: string) => createTag(name),
    onSuccess: (tag) => {
      queryClient.invalidateQueries({ queryKey: ['tags'] });
      addTagMutation.mutate(tag.id);
      setNewTagName('');
      setShowAdd(false);
    },
  });

  const addTagMutation = useMutation({
    mutationFn: (tagId: number) => addVideoTag(videoId, tagId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collection'] });
    },
  });

  return (
    <div className="flex flex-wrap items-center gap-1">
      {showAdd ? (
        <div className="flex items-center gap-1">
          {allTags && allTags.length > 0 && (
            <select
              className="h-6 rounded border bg-background px-1 text-xs"
              onChange={(e) => {
                if (e.target.value) {
                  addTagMutation.mutate(Number(e.target.value));
                  e.target.value = '';
                }
              }}
              defaultValue=""
            >
              <option value="" disabled>
                Existing...
              </option>
              {allTags.map((t: TagEntry) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
          <Input
            placeholder="New tag"
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && newTagName.trim()) {
                createTagMutation.mutate(newTagName.trim());
              }
            }}
            className="h-6 w-24 text-xs px-1"
          />
          <button type="button" onClick={() => setShowAdd(false)}>
            <X className="size-3 text-muted-foreground" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowAdd(true)}
          className="inline-flex items-center gap-0.5 rounded-full border border-dashed px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Tag className="size-3" />
          tag
        </button>
      )}
    </div>
  );
}

function CollectionDetailView({
  collectionId,
  onBack,
}: {
  collectionId: number;
  onBack: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: collection, isLoading } = useQuery({
    queryKey: ['collection', collectionId],
    queryFn: () => getCollection(collectionId),
  });
  const [showAddVideos, setShowAddVideos] = useState(false);

  const removeMutation = useMutation({
    mutationFn: (videoId: number) => removeCollectionItem(collectionId, videoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collection', collectionId] });
      queryClient.invalidateQueries({ queryKey: ['collections'] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!collection) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronRight className="size-4 rotate-180" />
          Back
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">{collection.name}</h2>
            <TypeBadge type={collection.collection_type} />
          </div>
          {collection.description && (
            <p className="text-sm text-muted-foreground mt-1">{collection.description}</p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowAddVideos(true)}>
          <Plus className="size-4 mr-1.5" />
          Add Transcripts
        </Button>
      </div>

      {collection.items.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed p-8 text-center">
          <FileText className="mx-auto size-8 text-muted-foreground/50 mb-3" />
          <p className="text-muted-foreground text-sm">No transcripts in this collection yet.</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => setShowAddVideos(true)}
          >
            <Plus className="size-4 mr-1.5" />
            Add Transcripts
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {collection.items.map((item: CollectionItemEntry, idx: number) => (
            <Card key={item.id}>
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <span className="text-xs text-muted-foreground font-mono pt-1 shrink-0 w-6 text-right">
                    {idx + 1}.
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{item.output_title}</p>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {item.source_path.split('/').pop()}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      {item.tags.map((t: TagEntry) => (
                        <TagPill key={t.id} tag={t} />
                      ))}
                      <TagManager videoId={item.id} />
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0">
                    {new Date(item.processed_at).toLocaleDateString()}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="shrink-0 size-7 text-muted-foreground hover:text-destructive"
                    title="Remove from collection"
                    onClick={() => removeMutation.mutate(item.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <AddVideoSheet
        collectionId={collectionId}
        open={showAddVideos}
        onClose={() => setShowAddVideos(false)}
      />
    </div>
  );
}

export function Collections() {
  const queryClient = useQueryClient();
  const { data: collections, isLoading, error } = useQuery({
    queryKey: ['collections'],
    queryFn: getCollections,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createType, setCreateType] = useState('course');
  const [createDesc, setCreateDesc] = useState('');
  const [activeCollectionId, setActiveCollectionId] = useState<number | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      createCollection({
        name: createName.trim(),
        collection_type: createType,
        description: createDesc.trim(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collections'] });
      setShowCreate(false);
      setCreateName('');
      setCreateType('course');
      setCreateDesc('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCollection,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['collections'] }),
  });

  if (activeCollectionId !== null) {
    return (
      <CollectionDetailView
        collectionId={activeCollectionId}
        onBack={() => setActiveCollectionId(null)}
      />
    );
  }

  return (
    <div className="space-y-6">
      <SearchBar />

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Collections</h2>
          <p className="text-sm text-muted-foreground">
            Organize your transcripts by course, mentorship, or topic.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="size-4 mr-1.5" />
          New Collection
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardHeader className="p-4">
            <CardTitle className="text-sm">Create Collection</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (createName.trim()) createMutation.mutate();
              }}
              className="space-y-3"
            >
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="coll-name" className="text-xs">
                    Name
                  </Label>
                  <Input
                    id="coll-name"
                    placeholder="e.g. ML Fundamentals"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    className="h-8 text-sm"
                    autoFocus
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="coll-type" className="text-xs">
                    Type
                  </Label>
                  <Select value={createType} onValueChange={setCreateType}>
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(COLLECTION_TYPES).map(([value, cfg]) => (
                        <SelectItem key={value} value={value}>
                          {cfg.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="coll-desc" className="text-xs">
                  Description (optional)
                </Label>
                <Input
                  id="coll-desc"
                  placeholder="What is this collection about?"
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  className="h-8 text-sm"
                />
              </div>
              <div className="flex gap-2 items-center">
                <Button
                  type="submit"
                  size="sm"
                  disabled={createMutation.isPending || !createName.trim()}
                >
                  {createMutation.isPending ? 'Creating...' : 'Create'}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setShowCreate(false);
                    setCreateName('');
                    setCreateDesc('');
                  }}
                >
                  Cancel
                </Button>
                {createMutation.isError && (
                  <span className="text-xs text-destructive">
                    {(createMutation.error as Error).message}
                  </span>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Loading collections...</p>}
      {error && (
        <p className="text-sm text-destructive">
          Failed to load collections: {(error as Error).message}
        </p>
      )}

      {collections && collections.length === 0 && !showCreate && (
        <div className="rounded-lg border-2 border-dashed p-8 text-center">
          <BookOpen className="mx-auto size-8 text-muted-foreground/50 mb-3" />
          <p className="text-muted-foreground text-sm">No collections yet.</p>
          <p className="text-muted-foreground text-xs mt-1">
            Create a collection to organize your transcripts by course, mentorship, or topic.
          </p>
        </div>
      )}

      {collections && collections.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {collections.map((c: CollectionEntry) => (
            <Card
              key={c.id}
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => setActiveCollectionId(c.id)}
            >
              <CardHeader className="p-4">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-sm font-semibold truncate">
                        {c.name}
                      </CardTitle>
                      <TypeBadge type={c.collection_type} />
                    </div>
                    {c.description && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {c.description}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground mt-2">
                      {c.item_count} {c.item_count === 1 ? 'transcript' : 'transcripts'}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="shrink-0 size-7 text-muted-foreground hover:text-destructive"
                    title="Delete collection"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (
                        confirm(
                          `Delete "${c.name}"? Transcripts will not be deleted.`
                        )
                      )
                        deleteMutation.mutate(c.id);
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
