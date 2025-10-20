import { Buffer } from 'node:buffer';

export type BcutTranscribeOptions = {
  language?: string | null;
  model?: string | null;
  prompt?: string | null;
  timeoutMs?: number;
  signal?: AbortSignal;
};

export type BcutTranscribeInput = {
  buffer: Buffer;
  filename: string;
  mimeType: string;
  options?: BcutTranscribeOptions;
};

export type BcutTranscribeResult = {
  text: string;
  metadata: {
    provider: 'bcut';
    jobId?: string;
    language?: string;
    duration?: number;
    model?: string;
    confidence?: number;
    raw?: unknown;
  };
};

function getEnv(name: string, fallback?: string): string {
  const v = process.env[name];
  if (v == null || v === '') {
    if (fallback !== undefined) return fallback;
    throw new Error(`Missing required env var: ${name}`);
  }
  return v;
}

function getOptionalEnv(name: string, fallback?: string): string | undefined {
  const v = process.env[name];
  if (v == null || v === '') return fallback;
  return v;
}

export async function bcutTranscribe(input: BcutTranscribeInput): Promise<BcutTranscribeResult> {
  const { buffer, filename, mimeType, options } = input;

  const baseUrl = getEnv('BCUT_BASE_URL');
  const apiKey = getEnv('BCUT_API_KEY');
  const path = getOptionalEnv('BCUT_TRANSCRIBE_PATH', '/v1/transcribe')!;
  const timeoutMs = options?.timeoutMs ?? Number(getOptionalEnv('BCUT_TIMEOUT_MS', '120000'));
  const language = options?.language ?? getOptionalEnv('BCUT_LANGUAGE');
  const model = options?.model ?? getOptionalEnv('BCUT_MODEL');
  const prompt = options?.prompt ?? getOptionalEnv('BCUT_PROMPT');

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const form = new FormData();
    const blob = new Blob([buffer], { type: mimeType || 'application/octet-stream' });
    form.append('file', blob, filename);
    if (language) form.append('language', language);
    if (model) form.append('model', model);
    if (prompt) form.append('prompt', prompt);

    const url = `${baseUrl.replace(/\/$/, '')}${path.startsWith('/') ? path : `/${path}`}`;

    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
      body: form,
      signal: options?.signal ?? controller.signal,
      // Do not cache POST requests
      cache: 'no-store',
    });

    const contentType = res.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');
    const raw = isJson ? await res.json().catch(() => null) : await res.text().catch(() => null);

    if (!res.ok) {
      const message = isJson && raw && typeof raw === 'object' && 'message' in raw ? (raw as any).message : res.statusText;
      const err = new Error(`BCut API error: ${res.status} ${message}`);
      (err as any).response = raw;
      throw err;
    }

    const data = raw as any;
    const text: string = (data?.text as string) ?? (data?.transcript as string) ?? '';

    return {
      text,
      metadata: {
        provider: 'bcut',
        jobId: (data?.job_id as string) ?? (data?.id as string),
        language: (data?.language as string) ?? language ?? undefined,
        duration: typeof data?.duration === 'number' ? (data.duration as number) : undefined,
        model: (data?.model as string) ?? model ?? undefined,
        confidence: typeof data?.confidence === 'number' ? (data.confidence as number) : undefined,
        raw: data,
      },
    };
  } finally {
    clearTimeout(timeout);
  }
}
