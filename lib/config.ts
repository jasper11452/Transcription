type GetEnvOptions<T> = {
  name: string;
  fallback?: T;
  parse?: (raw: string) => T;
  required?: boolean;
};

function getEnv<T = string>({ name, fallback, parse, required }: GetEnvOptions<T>): T {
  const raw = process.env[name];
  if (!raw || raw.length === 0) {
    if (required && fallback === undefined) {
      throw new Error(`Missing required env var: ${name}`);
    }
    return fallback as T;
  }
  if (parse) return parse(raw);
  return raw as unknown as T;
}

export const config = {
  // BCut API
  bcut: {
    baseUrl: getEnv<string>({ name: 'BCUT_BASE_URL', fallback: '' }),
    apiKey: getEnv<string>({ name: 'BCUT_API_KEY', fallback: '' }),
    transcribePath: getEnv<string>({ name: 'BCUT_TRANSCRIBE_PATH', fallback: '/v1/transcribe' }),
    timeoutMs: getEnv<number>({ name: 'BCUT_TIMEOUT_MS', fallback: 120000, parse: Number }),
    language: getEnv<string | undefined>({ name: 'BCUT_LANGUAGE', fallback: undefined }),
    model: getEnv<string | undefined>({ name: 'BCUT_MODEL', fallback: undefined }),
    prompt: getEnv<string | undefined>({ name: 'BCUT_PROMPT', fallback: undefined }),
  },
  // Uploads
  uploads: {
    maxMb: getEnv<number>({ name: 'UPLOAD_MAX_MB', fallback: 100, parse: Number }),
  },
  // Simple in-memory rate limit
  rateLimit: {
    requestsPerMinute: getEnv<number>({ name: 'RATE_LIMIT_RPM', fallback: 60, parse: Number }),
  },
};
