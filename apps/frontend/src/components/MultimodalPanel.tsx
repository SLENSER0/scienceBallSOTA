import { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ImagePlus, Loader2, ScanEye } from 'lucide-react';
import { api, type MultimodalResult } from '../api';

// Multimodal deep-research (§ minimax-m3): attach a figure / micrograph / flowsheet /
// screenshot and get a structured OSS-vision analysis — the visual leg of research.
// Nothing is written to the graph; the analysis is meant to be read or pasted into a
// deep-research question or a manually-added article.

const DEFAULT_Q = 'Опиши, что изображено, и извлеки численные данные, оси, режимы и обозначения.';

export function MultimodalPanel() {
  const [question, setQuestion] = useState(DEFAULT_Q);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<MultimodalResult | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const run = async (file: File) => {
    setBusy(true);
    setError('');
    setResult(null);
    setPreview(URL.createObjectURL(file));
    try {
      setResult(await api.analyzeImage(file, question.trim() || DEFAULT_Q));
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel mt-5 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm text-nickel">
        <ScanEye size={15} className="text-copper" /> Мультимодальный анализ · рисунки, графики, шлифы
      </div>
      <p className="mb-3 text-[11px] text-faint">
        Загрузите изображение из статьи (график, микрофотография, схема флотации, скриншот) — OSS
        vision-модель <span className="font-mono text-copper">minimax/minimax-m3</span> опишет его и
        извлечёт численные данные. В граф ничего не пишется.
      </p>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        rows={2}
        placeholder="Вопрос к изображению…"
        className="mb-2 w-full resize-none rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
      />

      <div className="grid gap-3 lg:grid-cols-2">
        {/* Dropzone / preview */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void run(f);
          }}
          onClick={() => !busy && inputRef.current?.click()}
          className={`flex min-h-[180px] cursor-pointer flex-col items-center justify-center gap-2 overflow-hidden rounded-md border-2 border-dashed p-3 text-center transition ${
            drag ? 'border-copper bg-copper/10' : 'border-line hover:border-copper/50'
          } ${busy ? 'pointer-events-none opacity-70' : ''}`}
        >
          {preview ? (
            <img src={preview} alt="preview" className="max-h-[220px] max-w-full rounded object-contain" />
          ) : (
            <>
              <ImagePlus size={22} className="text-faint" />
              <div className="text-sm text-nickel">Перетащите изображение или нажмите</div>
              <div className="font-mono text-[10px] text-faint">PNG · JPG · WEBP · GIF (до 12 МБ)</div>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void run(f);
              e.target.value = '';
            }}
          />
        </div>

        {/* Analysis */}
        <div className="min-h-[180px] rounded-md border border-line bg-graphite/40 p-3">
          {busy ? (
            <div className="flex h-full items-center justify-center gap-2 font-mono text-xs text-faint">
              <Loader2 size={14} className="animate-spin text-copper" /> minimax-m3 читает изображение…
            </div>
          ) : error ? (
            <div className="text-sm text-contradiction">Ошибка: {error}</div>
          ) : result ? (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="chip text-copper-bright">{result.model}</span>
                <span className="truncate font-mono text-[10px] text-faint">{result.filename}</span>
              </div>
              <div className="md max-h-[320px] overflow-y-auto text-[13px]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.analysis}</ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-[11px] text-faint">
              анализ появится здесь
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
