import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { getConfig, putConfig, type Config, type ConfigUpdate } from '../api/client';
import './Config.css';

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

  if (isLoading) return <div className="config-page">Loading...</div>;
  if (error) return <div className="config-page error">Failed to load config: {(error as Error).message}</div>;

  return (
    <div className="config-page">
      <h2>Settings</h2>
      <p className="config-desc">Configure your Deepgram API key and optional Google Docs export.</p>

      <form onSubmit={handleSubmit} className="config-form">
        <div className="field">
          <label htmlFor="deepgram">Deepgram API Key *</label>
          <input
            id="deepgram"
            type="password"
            placeholder="dg-..."
            value={values.deepgram_api_key ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, deepgram_api_key: e.target.value }))}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="google_json">Google Service Account JSON (optional)</label>
          <input
            id="google_json"
            type="text"
            placeholder="/path/to/service-account.json"
            value={values.google_service_account_json ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, google_service_account_json: e.target.value }))}
          />
        </div>

        <div className="field">
          <label htmlFor="drive_folder">Google Drive Folder ID (optional)</label>
          <input
            id="drive_folder"
            type="text"
            placeholder="1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
            value={values.drive_folder_id ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, drive_folder_id: e.target.value }))}
          />
        </div>

        <div className="field">
          <label htmlFor="md_dir">Markdown Output Directory</label>
          <input
            id="md_dir"
            type="text"
            placeholder="./output"
            value={values.markdown_output_dir ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, markdown_output_dir: e.target.value }))}
          />
        </div>

        <div className="field">
          <label>Naming Mode</label>
          <div className="radio-group">
            <label className="radio">
              <input
                type="radio"
                name="naming"
                value="sequential"
                checked={(values.naming_mode ?? 'sequential') === 'sequential'}
                onChange={() => setForm((f) => ({ ...f, naming_mode: 'sequential' }))}
              />
              Sequential (Prefix_1, Prefix_2, ...)
            </label>
            <label className="radio">
              <input
                type="radio"
                name="naming"
                value="original"
                checked={values.naming_mode === 'original'}
                onChange={() => setForm((f) => ({ ...f, naming_mode: 'original' }))}
              />
              Original (Prefix_FileName)
            </label>
          </div>
        </div>

        <div className="field">
          <label htmlFor="prefix">Prefix</label>
          <input
            id="prefix"
            type="text"
            placeholder="Transcripcion"
            value={values.prefix ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, prefix: e.target.value }))}
          />
        </div>

        {config?.output_mode && (
          <p className="output-mode">
            Output: {config.output_mode === 'google_docs' ? 'Google Docs' : 'Local Markdown (.md)'}
          </p>
        )}

        <button type="submit" className="btn-primary" disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving...' : saved ? 'Saved!' : 'Save'}
        </button>
        {mutation.isError && (
          <p className="form-error">{(mutation.error as Error).message}</p>
        )}
      </form>
    </div>
  );
}
