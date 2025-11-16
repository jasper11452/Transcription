import { NextResponse } from 'next/server';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { Buffer } from 'node:buffer';
import { bcutTranscribe } from '../../../lib/bcut';
import { config } from '../../../lib/config';
import { ALLOWED_MIME_TYPES, ALLOWED_EXTENSIONS } from '../../../lib/constants';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// Simple in-memory rate limiter keyed by IP
const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute buckets
const RATE_LIMIT_RPM = config.rateLimit.requestsPerMinute;
const rateBuckets = new Map<string, { windowStart: number; count: number }>();

function getClientIp(req: Request): string {
  const xff = req.headers.get('x-forwarded-for');
  if (xff) return xff.split(',')[0].trim();
  return req.headers.get('x-real-ip') || 'local';
}

function isRateLimited(req: Request): boolean {
  try {
    const ip = getClientIp(req);
    const now = Date.now();
    const bucket = rateBuckets.get(ip);
    if (!bucket) {
      rateBuckets.set(ip, { windowStart: now, count: 1 });
      return false;
    }
    if (now - bucket.windowStart > RATE_LIMIT_WINDOW_MS) {
      rateBuckets.set(ip, { windowStart: now, count: 1 });

      // Clean up old entries to prevent memory leak
      // Only run cleanup if we have too many buckets
      if (rateBuckets.size > 1000) {
        const staleThreshold = now - RATE_LIMIT_WINDOW_MS * 5; // 5 minutes old
        rateBuckets.forEach((value, key) => {
          if (value.windowStart < staleThreshold) {
            rateBuckets.delete(key);
          }
        });
      }

      return false;
    }
    if (bucket.count >= RATE_LIMIT_RPM) return true;
    bucket.count += 1;
    return false;
  } catch {
    return false;
  }
}

function getUploadDir(): string {
  const baseDir = process.cwd();
  const uploadDir = path.join(baseDir, 'data', 'uploads');
  return uploadDir;
}

function extnameSafe(filename: string): string {
  const ext = path.extname(filename).toLowerCase();
  if (ext) return ext;
  return '';
}

function sanitizeBaseName(name: string): string {
  return name
    .replace(/\s+/g, '-')
    .replace(/[^a-zA-Z0-9._-]/g, '')
    .replace(/-+/g, '-')
    .slice(0, 80);
}

async function saveUploadedFile(file: File) {
  const uploadDir = getUploadDir();
  await fs.mkdir(uploadDir, { recursive: true });

  const origName = file.name || 'upload';
  const ext = extnameSafe(origName);
  const base = sanitizeBaseName(origName.replace(new RegExp(`${ext}$`), '')) || 'upload';
  const unique = `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`;
  const filename = `${base}-${unique}${ext}`;
  const filepath = path.join(uploadDir, filename);

  const arrayBuffer = await file.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  await fs.writeFile(filepath, buffer);

  return { filepath, filename, buffer } as const;
}

export async function POST(req: Request) {
  try {
    if (isRateLimited(req)) {
      return NextResponse.json({ error: 'Too many requests' }, { status: 429 });
    }

    const contentType = req.headers.get('content-type') || '';
    if (!contentType.includes('multipart/form-data')) {
      return NextResponse.json({ error: 'Content-Type must be multipart/form-data' }, { status: 415 });
    }

    const form = await req.formData();
    const file = form.get('file');
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "Field 'file' is required and must be a file" }, { status: 400 });
    }

    const ext = extnameSafe(file.name || '');
    const type = file.type || '';
    const extOk = ext ? ALLOWED_EXTENSIONS.has(ext) : false;
    const typeOk = type ? ALLOWED_MIME_TYPES.has(type) : false;

    // Require both extension and MIME type to be valid for stronger validation
    if (!ext || !extOk) {
      return NextResponse.json({ error: 'Invalid or missing file extension' }, { status: 415 });
    }
    if (!type || !typeOk) {
      return NextResponse.json({
        error: 'Invalid or missing MIME type. File type does not match extension.'
      }, { status: 415 });
    }

    const maxMb = config.uploads.maxMb;
    const maxBytes = maxMb * 1024 * 1024;
    if (file.size > maxBytes) {
      return NextResponse.json({ error: `File too large. Max size is ${maxMb} MB` }, { status: 413 });
    }

    const { filepath, filename, buffer } = await saveUploadedFile(file);

    const languageRaw = form.get('language') as string | null;
    const modelRaw = form.get('model') as string | null;
    const promptRaw = form.get('prompt') as string | null;

    const language = languageRaw ? String(languageRaw).trim() || undefined : undefined;
    const model = modelRaw ? String(modelRaw).trim() || undefined : undefined;
    const prompt = promptRaw ? String(promptRaw).slice(0, 1000) : undefined;

    const result = await bcutTranscribe({
      buffer,
      filename,
      mimeType: file.type || 'application/octet-stream',
      options: { language, model, prompt },
    });

    return NextResponse.json(
      {
        text: result.text,
        metadata: {
          ...result.metadata,
          file: {
            path: filepath,
            name: filename,
            size: file.size,
            type: file.type,
          },
        },
      },
      { status: 200 }
    );
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    console.error('Transcription error:', message);
    return NextResponse.json({ error: 'Transcription failed', details: message }, { status: 500 });
  }
}

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    maxUploadMB: config.uploads.maxMb,
    rateLimitRPM: config.rateLimit.requestsPerMinute,
    allowed: {
      mimeTypes: Array.from(ALLOWED_MIME_TYPES),
      extensions: Array.from(ALLOWED_EXTENSIONS),
    },
  });
}
