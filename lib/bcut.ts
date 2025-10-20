import { Buffer } from 'node:buffer';
import { config } from './config';

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



export async function bcutTranscribe(input: BcutTranscribeInput): Promise<BcutTranscribeResult> {
  const { buffer, filename, mimeType, options } = input;

  const baseUrl = config.bcut.baseUrl;
  const apiKey = config.bcut.apiKey;
  const path = config.bcut.transcribePath;
  const timeoutMs = options?.timeoutMs ?? config.bcut.timeoutMs;
  const language = options?.language ?? config.bcut.language;
  const model = options?.model ?? config.bcut.model;
  const prompt = options?.prompt ?? config.bcut.prompt;

  if (!baseUrl) {
    throw new Error('Missing required env var: BCUT_BASE_URL');
  }
  if (!apiKey) {
    throw new Error('Missing required env var: BCUT_API_KEY');
  }

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
    const raw: unknown = isJson ? await res.json().catch(() => null) : await res.text().catch(() => null);

    if (!res.ok) {
      let message = res.statusText;
      if (isJson && raw && typeof raw === 'object' && 'message' in raw) {
        const m = (raw as Record<string, unknown>).message;
        if (typeof m === 'string') message = m;
      }
      type BcutError = Error & { response?: unknown };
      const err: BcutError = new Error(`BCut API error: ${res.status} ${message}`);
      err.response = raw;
      throw err;
    }

    const data = raw as Record<string, unknown> | string | null;
    let text = '';
    if (data && typeof data === 'object') {
      const t = (data as Record<string, unknown>).text;
      const tr = (data as Record<string, unknown>).transcript;
      if (typeof t === 'string') text = t;
      else if (typeof tr === 'string') text = tr;
    }

    return {
      text,
      metadata: {
        provider: 'bcut',
        jobId:
          data && typeof data === 'object'
            ? (typeof (data as Record<string, unknown>).job_id === 'string'
                ? ((data as Record<string, unknown>).job_id as string)
                : typeof (data as Record<string, unknown>).id === 'string'
                ? ((data as Record<string, unknown>).id as string)
                : undefined)
            : undefined,
        language:
          (data && typeof data === 'object' && typeof (data as Record<string, unknown>).language === 'string'
            ? ((data as Record<string, unknown>).language as string)
            : language) ?? undefined,
        duration:
          data && typeof data === 'object' && typeof (data as Record<string, unknown>).duration === 'number'
            ? ((data as Record<string, unknown>).duration as number)
            : undefined,
        model:
          (data && typeof data === 'object' && typeof (data as Record<string, unknown>).model === 'string'
            ? ((data as Record<string, unknown>).model as string)
            : model) ?? undefined,
        confidence:
          data && typeof data === 'object' && typeof (data as Record<string, unknown>).confidence === 'number'
            ? ((data as Record<string, unknown>).confidence as number)
            : undefined,
        raw: data,
      },
    };
  } finally {
    clearTimeout(timeout);
  }
}
