import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { FolderOpen } from 'lucide-react';
import { getConfig, putConfig, openPath, type Config, type ConfigUpdate } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function Config() {
  const queryClient = useQueryClient();
  const { data: config, isLoading, error } = useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
  });

  const [form, setForm] = useState<Partial<Config>>({});
  const [saved, setSaved] = useState(false);

  const mutation = useMutation({
    mutationFn: putConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const update: ConfigUpdate = {};
    if (form.deepgram_api_key !== undefined) update.deepgram_api_key = form.deepgram_api_key;
    if (form.google_service_account_json !== undefined) update.google_service_account_json = form.google_service_account_json;
    if (form.drive_folder_id !== undefined) update.drive_folder_id = form.drive_folder_id;
    if (form.naming_mode !== undefined) update.naming_mode = form.naming_mode;
    if (form.prefix !== undefined) update.prefix = form.prefix;
    if (form.markdown_output_dir !== undefined) update.markdown_output_dir = form.markdown_output_dir;
    mutation.mutate(update);
  };

  const values = { ...config, ...form };

  if (isLoading) return <div className="p-4">Loading...</div>;
  if (error) return <div className="p-4 text-destructive">Failed to load config: {(error as Error).message}</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Settings</CardTitle>
        <CardDescription>Configure your Deepgram API key and optional Google Docs export.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="deepgram">Deepgram API Key *</Label>
            <Input
              id="deepgram"
              type="password"
              placeholder="dg-..."
              value={values.deepgram_api_key ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, deepgram_api_key: e.target.value }))}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="google_json">Google Service Account JSON (optional)</Label>
            <div className="flex gap-2">
              <Input
                id="google_json"
                type="text"
                placeholder="/path/to/service-account.json"
                value={values.google_service_account_json ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, google_service_account_json: e.target.value }))}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                title="Open in file browser"
                disabled={!values.google_service_account_json?.trim()}
                onClick={async () => {
                  const path = values.google_service_account_json?.trim();
                  if (!path) return;
                  try {
                    await openPath(path);
                  } catch (e) {
                    alert((e as Error).message);
                  }
                }}
              >
                <FolderOpen className="size-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="drive_folder">Google Drive Folder ID (optional)</Label>
            <Input
              id="drive_folder"
              type="text"
              placeholder="1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
              value={values.drive_folder_id ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, drive_folder_id: e.target.value }))}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="md_dir">Markdown Output Directory</Label>
            <div className="flex gap-2">
              <Input
                id="md_dir"
                type="text"
                placeholder="./output"
                value={values.markdown_output_dir ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, markdown_output_dir: e.target.value }))}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                title="Open in file browser"
                onClick={async () => {
                  const path = values.markdown_output_dir?.trim() || './output';
                  try {
                    await openPath(path);
                  } catch (e) {
                    alert((e as Error).message);
                  }
                }}
              >
                <FolderOpen className="size-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-3">
            <Label>Naming Mode</Label>
            <RadioGroup
              value={values.naming_mode ?? 'sequential'}
              onValueChange={(v) => setForm((f) => ({ ...f, naming_mode: v }))}
              className="flex flex-col gap-2"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="sequential" id="mode_seq" />
                <Label htmlFor="mode_seq" className="font-normal cursor-pointer">
                  Sequential (Prefix_1, Prefix_2, ...)
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="original" id="mode_orig" />
                <Label htmlFor="mode_orig" className="font-normal cursor-pointer">
                  Original (Prefix_FileName)
                </Label>
              </div>
            </RadioGroup>
          </div>

          <div className="space-y-2">
            <Label htmlFor="prefix">Prefix</Label>
            <Input
              id="prefix"
              type="text"
              placeholder="Transcripcion"
              value={values.prefix ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, prefix: e.target.value }))}
            />
          </div>

          {config?.output_mode && (
            <p className="text-sm text-muted-foreground">
              Output: {config.output_mode === 'google_docs' ? 'Google Docs' : 'Local Markdown (.md)'}
            </p>
          )}

          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving...' : saved ? 'Saved!' : 'Save'}
          </Button>
          {mutation.isError && (
            <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
