import { NextResponse } from 'next/server';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { Buffer } from 'node:buffer';
import { bcutTranscribe } from '../../../lib/bcut';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function getUploadDir(): string {
  const baseDir = process.cwd();
  const uploadDir = path.join(baseDir, 'data', 'uploads');
  return uploadDir;
}

function extnameSafe(filename: string): string {
  const ext = path.extname(filename);
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
    const contentType = req.headers.get('content-type') || '';
    if (!contentType.includes('multipart/form-data')) {
      return NextResponse.json({ error: 'Content-Type must be multipart/form-data' }, { status: 415 });
    }

    const form = await req.formData();
    const file = form.get('file');
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "Field 'file' is required and must be a file" }, { status: 400 });
    }

    const maxMb = Number(process.env.UPLOAD_MAX_MB || '100');
    const maxBytes = maxMb * 1024 * 1024;
    if (file.size > maxBytes) {
      return NextResponse.json({ error: `File too large. Max size is ${maxMb} MB` }, { status: 413 });
    }

    const { filepath, filename, buffer } = await saveUploadedFile(file);

    const language = (form.get('language') as string) || undefined;
    const model = (form.get('model') as string) || undefined;
    const prompt = (form.get('prompt') as string) || undefined;

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
  } catch (err: any) {
    // Avoid leaking secrets in error messages
    const message = err?.message || 'Unknown error';
    console.error('Transcription error:', message);
    return NextResponse.json({ error: 'Transcription failed', details: message }, { status: 500 });
  }
}
