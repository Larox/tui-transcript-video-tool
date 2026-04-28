import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { FolderSearch } from 'lucide-react';
import {
  createDirectory,
  pickDirectory,
  type DirectoryEntry,
} from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface DirectoryFormProps {
  onSubmit: (entry: DirectoryEntry) => void;
  onCancel: () => void;
  /** Optional name suffix used to disambiguate input ids when this form is rendered multiple times on the same page. */
  idPrefix?: string;
}

export function DirectoryForm({ onSubmit, onCancel, idPrefix = 'dir' }: DirectoryFormProps) {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');

  const mutation = useMutation({
    mutationFn: () => createDirectory(name.trim(), path.trim()),
    onSuccess: (entry) => {
      onSubmit(entry);
      setName('');
      setPath('');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !path.trim()) return;
    mutation.mutate();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-name`} className="text-xs">
          Name
        </Label>
        <Input
          id={`${idPrefix}-name`}
          type="text"
          placeholder="e.g. Lecture Notes"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="h-8 text-sm"
          autoFocus
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-path`} className="text-xs">
          Directory Path
        </Label>
        <div className="flex gap-2">
          <Input
            id={`${idPrefix}-path`}
            type="text"
            placeholder="/Users/you/Documents/transcripts"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="h-8 text-sm flex-1"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 shrink-0"
            onClick={async () => {
              try {
                const picked = await pickDirectory();
                if (picked) setPath(picked);
              } catch (err) {
                alert((err as Error).message);
              }
            }}
          >
            <FolderSearch className="size-3.5 mr-1.5" />
            Browse
          </Button>
        </div>
      </div>
      <div className="flex gap-2 items-center">
        <Button
          type="submit"
          size="sm"
          disabled={mutation.isPending || !name.trim() || !path.trim()}
        >
          {mutation.isPending ? 'Adding...' : 'Add'}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        {mutation.isError && (
          <span className="text-xs text-destructive">
            {(mutation.error as Error).message}
          </span>
        )}
      </div>
    </form>
  );
}
