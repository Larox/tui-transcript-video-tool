import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { getConfig, putConfig, type Config, type ConfigUpdate } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { LocalModelsPanel } from '@/components/LocalModelsPanel';

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
    if (form.naming_mode !== undefined) update.naming_mode = form.naming_mode;
    if (form.prefix !== undefined) update.prefix = form.prefix;
    if (form.anthropic_api_key !== undefined) update.anthropic_api_key = form.anthropic_api_key;
    mutation.mutate(update);
  };

  const values = { ...config, ...form };

  if (isLoading) return <div className="p-4">Loading...</div>;
  if (error) return <div className="p-4 text-destructive">Failed to load config: {(error as Error).message}</div>;

  return (
    <div className="space-y-6">
    <Card>
      <CardHeader>
        <CardTitle>Settings</CardTitle>
        <CardDescription>Configure API keys and output preferences.</CardDescription>
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
            <Label htmlFor="anthropic-key">Anthropic API Key (optional)</Label>
            <Input
              id="anthropic-key"
              type="password"
              placeholder={config?.anthropic_api_key ? '(set — enter to change)' : 'sk-ant-...'}
              value={values.anthropic_api_key ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, anthropic_api_key: e.target.value }))}
            />
            <p className="text-xs text-muted-foreground">
              Used to extract Key Moments from transcripts via Claude. Leave blank to skip.
            </p>
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

          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving...' : saved ? 'Saved!' : 'Save'}
          </Button>
          {mutation.isError && (
            <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
          )}
        </form>
      </CardContent>
    </Card>
    <LocalModelsPanel />
    </div>
  );
}
