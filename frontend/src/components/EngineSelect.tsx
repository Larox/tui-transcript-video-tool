import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  listLocalModels,
  type Engine,
  type LocalModelInfo,
  type WhisperModelName,
} from '@/api/client';

export interface EngineSelectProps {
  engine: Engine;
  whisperModel: WhisperModelName | undefined;
  onEngineChange: (engine: Engine) => void;
  onWhisperModelChange: (model: WhisperModelName | undefined) => void;
  disabled?: boolean;
}

export function EngineSelect({
  engine,
  whisperModel,
  onEngineChange,
  onWhisperModelChange,
  disabled,
}: EngineSelectProps) {
  const { data: localModels = [] } = useQuery<LocalModelInfo[]>({
    queryKey: ['local-models'],
    queryFn: listLocalModels,
    enabled: engine === 'whisper_local',
  });
  const downloaded = localModels.filter((m) => m.downloaded);

  return (
    <div className="flex items-center gap-2">
      <Select
        value={engine}
        onValueChange={(v) => {
          onEngineChange(v as Engine);
          if (v === 'deepgram') onWhisperModelChange(undefined);
        }}
        disabled={disabled}
      >
        <SelectTrigger className="w-[140px] h-8">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="deepgram">Deepgram</SelectItem>
          <SelectItem value="whisper_local">Local Whisper</SelectItem>
        </SelectContent>
      </Select>

      {engine === 'whisper_local' && (
        <>
          <Select
            value={whisperModel ?? ''}
            onValueChange={(v) => onWhisperModelChange(v as WhisperModelName)}
            disabled={disabled || downloaded.length === 0}
          >
            <SelectTrigger className="w-[120px] h-8">
              <SelectValue
                placeholder={
                  downloaded.length === 0 ? 'No models' : 'Pick model'
                }
              />
            </SelectTrigger>
            <SelectContent>
              {downloaded.map((m) => (
                <SelectItem key={m.name} value={m.name}>
                  {m.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {downloaded.length === 0 && (
            <Link
              to="/config"
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Download models in Settings
            </Link>
          )}
        </>
      )}
    </div>
  );
}
