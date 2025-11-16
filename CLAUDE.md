# CLAUDE.md - AI Assistant Development Guide

This document provides comprehensive guidance for AI assistants working with this Next.js 14 audio transcription application codebase.

## Table of Contents
- [Project Overview](#project-overview)
- [Technology Stack](#technology-stack)
- [Directory Structure](#directory-structure)
- [Development Workflow](#development-workflow)
- [Code Conventions](#code-conventions)
- [API Patterns](#api-patterns)
- [Key Files Reference](#key-files-reference)
- [Environment Configuration](#environment-configuration)
- [Common Tasks](#common-tasks)
- [Security Considerations](#security-considerations)
- [Best Practices](#best-practices)

---

## Project Overview

**Name**: 语音转写 Demo (Audio Transcription Demo)

**Purpose**: A production-ready Next.js application that provides audio/video transcription functionality using the BCut ASR (Automatic Speech Recognition) API.

**Key Features**:
- File upload with validation (audio/video files)
- Configurable transcription parameters (language, model, prompt)
- Rate limiting and file size restrictions
- Server-side file persistence
- Comprehensive error handling
- TypeScript strict mode with full type safety

**Architecture**: Next.js 14 App Router with server-side API routes and client-side React components

---

## Technology Stack

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Framework** | Next.js | 14.2.0 | React framework with App Router |
| **UI Library** | React | 18.2.0 | Component library |
| **Language** | TypeScript | 5.4.0 | Type-safe JavaScript |
| **Styling** | Tailwind CSS | 3.4.3 | Utility-first CSS framework |
| **Linting** | ESLint | 8.57.0 | Code quality enforcement |
| **Formatting** | Prettier | 3.2.5 | Code style consistency |
| **CSS Processing** | PostCSS | 8.4.35 | CSS transformations |
| **Runtime** | Node.js | Latest | Server runtime |

**Important Notes**:
- Uses strict TypeScript configuration (`strict: true`)
- No path aliases configured (uses relative imports)
- App Router only (no Pages Router)
- Client components explicitly marked with `"use client"`

---

## Directory Structure

```
/home/user/smart/
├── app/                              # Next.js 14 App Router
│   ├── api/
│   │   └── transcribe/
│   │       └── route.ts              # POST/GET transcription endpoint (163 lines)
│   ├── components/
│   │   ├── TranscriptionForm.tsx     # Main form component (160 lines, client)
│   │   └── ServerInfo.tsx            # Config display (78 lines, client)
│   ├── globals.css                   # Tailwind directives + CSS variables
│   ├── layout.tsx                    # Root layout with metadata
│   └── page.tsx                      # Home page
│
├── lib/                              # Shared utilities
│   ├── config.ts                     # Environment variable management
│   ├── constants.ts                  # File type allowlists
│   └── bcut.ts                       # BCut API adapter (135 lines)
│
├── data/
│   └── uploads/                      # User file storage (gitignored)
│
├── Configuration Files
│   ├── package.json                  # Dependencies and scripts
│   ├── tsconfig.json                 # TypeScript strict config
│   ├── tailwind.config.js            # Tailwind setup
│   ├── postcss.config.js             # PostCSS config
│   ├── next.config.ts                # Next.js config (minimal)
│   ├── .eslintrc.json                # ESLint + Prettier rules
│   ├── .prettierrc                   # Code formatting rules
│   ├── .env.example                  # Environment template
│   └── .gitignore                    # Git ignore rules
```

**Key Directories**:
- `app/`: All pages, layouts, and API routes (App Router convention)
- `app/components/`: Reusable React components (client-side)
- `app/api/`: Server-side API endpoints
- `lib/`: Shared utilities, helpers, and business logic
- `data/uploads/`: Persistent file storage (not in version control)

---

## Development Workflow

### Available Scripts

```bash
npm run dev          # Start development server (localhost:3000)
npm run build        # Production build (type checking + Next.js build)
npm run start        # Start production server
npm run lint         # Run ESLint checks
npm run format       # Auto-format all files with Prettier
npm run format:check # Check formatting without modifying files
npm run typecheck    # Run TypeScript compiler without emitting files
```

### Development Process

1. **Start Development**:
   ```bash
   npm install              # Install dependencies
   cp .env.example .env.local  # Configure environment
   npm run dev              # Start dev server
   ```

2. **Pre-Commit Checklist**:
   - [ ] Run `npm run typecheck` (no TypeScript errors)
   - [ ] Run `npm run lint` (no ESLint errors)
   - [ ] Run `npm run format:check` (code is formatted)
   - [ ] Test functionality manually
   - [ ] Check console for errors/warnings

3. **Production Build**:
   ```bash
   npm run build   # Creates .next/ directory
   npm run start   # Runs production server
   ```

### Git Workflow

- **Main Branch**: Default branch for PRs
- **Feature Branches**: Use `claude/` prefix for AI-generated branches
- **Commit Messages**: Descriptive, focused on "why" not "what"
- **Never commit**: `.env.local`, `node_modules/`, `.next/`, `data/uploads/`

---

## Code Conventions

### TypeScript Patterns

**1. Type-Safe Environment Variables** (lib/config.ts:1-18):
```typescript
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
```

**2. Discriminated Unions for API Responses**:
```typescript
// Success response
{ text: string; metadata: {...} }

// Error response
{ error: string; details?: string }

// Type guards used in components to differentiate
if ('error' in result) { /* handle error */ }
else { /* handle success */ }
```

**3. Const Assertions for Return Types**:
```typescript
return { filepath, filename, buffer } as const;
```

**4. Explicit Type Imports**:
```typescript
import type { BcutTranscribeResult } from '../../../lib/bcut';
```

### Naming Conventions

| Type | Convention | Examples |
|------|-----------|----------|
| **Components** | PascalCase | `TranscriptionForm.tsx`, `ServerInfo.tsx` |
| **Files (lib)** | camelCase | `bcut.ts`, `config.ts`, `constants.ts` |
| **Routes** | lowercase | `route.ts` |
| **Variables** | camelCase | `uploadDir`, `rateBuckets`, `bcutTranscribe` |
| **Constants** | SCREAMING_SNAKE_CASE | `ALLOWED_MIME_TYPES`, `RATE_LIMIT_WINDOW_MS` |
| **Types/Interfaces** | PascalCase | `BcutTranscribeInput`, `GetEnvOptions` |
| **Env Vars** | SCREAMING_SNAKE_CASE | `BCUT_API_KEY`, `UPLOAD_MAX_MB` |

### Code Style (Prettier)

```json
{
  "semi": true,              // Always use semicolons
  "singleQuote": true,       // Prefer 'single' over "double"
  "trailingComma": "all",    // Trailing commas everywhere
  "printWidth": 100,         // Max line length: 100 characters
  "tabWidth": 2              // 2 spaces per indent
}
```

**Key Rules**:
- Always use semicolons
- Single quotes for strings (except in JSX)
- Trailing commas in arrays, objects, function params
- 100-character line limit
- 2-space indentation

### Import Organization

**Order** (not enforced by tooling, but conventional):
1. Next.js imports (`next/*`)
2. React imports (`react`)
3. Node.js built-ins (`node:fs`, `node:path`, etc.)
4. Third-party libraries
5. Local utilities (relative imports: `../../../lib/*`)

**Example**:
```typescript
import { NextResponse } from 'next/server';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { bcutTranscribe } from '../../../lib/bcut';
import { config } from '../../../lib/config';
```

### Component Patterns

**1. Client Components** - Must have `"use client"` directive:
```typescript
'use client';

import { useState, useEffect } from 'react';

export default function TranscriptionForm() {
  const [state, setState] = useState<Type>(initialValue);
  // ...
}
```

**2. Server Components** - Default, no directive needed:
```typescript
// app/page.tsx - Server component by default
import TranscriptionForm from './components/TranscriptionForm';

export default function Home() {
  return (
    <main>
      <TranscriptionForm />
    </main>
  );
}
```

**3. State Management**:
- Use `useState` for local state
- No global state management (Redux, Zustand) - keep it simple
- Form state managed in components

**4. Effect Cleanup**:
```typescript
useEffect(() => {
  const controller = new AbortController();

  // Async operation...

  return () => {
    controller.abort(); // Cleanup on unmount
  };
}, [dependencies]);
```

---

## API Patterns

### Route Handlers (app/api/transcribe/route.ts)

**Route Configuration**:
```typescript
export const runtime = 'nodejs';        // Use Node.js runtime (not Edge)
export const dynamic = 'force-dynamic'; // No static generation
```

**Handler Signatures**:
```typescript
export async function GET(req: Request) {
  return NextResponse.json({ data: '...' });
}

export async function POST(req: Request) {
  // Multipart form data handling
  const formData = await req.formData();
  const file = formData.get('file') as File | null;

  // Response
  return NextResponse.json({ result: '...' }, { status: 200 });
}
```

### Response Patterns

**Success Response** (200):
```typescript
return NextResponse.json({
  text: 'transcribed text',
  metadata: {
    provider: 'bcut',
    jobId: 'abc123',
    language: 'zh',
    duration: 123.45,
    model: 'model-name',
    confidence: 0.99,
    raw: { /* original API response */ },
    file: { path: '...', name: '...', size: 1234, type: 'audio/mpeg' },
  },
});
```

**Error Responses**:
```typescript
// 400 Bad Request
return NextResponse.json(
  { error: 'Missing file' },
  { status: 400 }
);

// 413 Payload Too Large
return NextResponse.json(
  { error: `File size exceeds ${config.uploads.maxMb} MB limit` },
  { status: 413 }
);

// 415 Unsupported Media Type
return NextResponse.json(
  { error: 'Unsupported file type' },
  { status: 415 }
);

// 429 Too Many Requests
return NextResponse.json(
  { error: 'Rate limit exceeded' },
  { status: 429 }
);

// 500 Internal Server Error
return NextResponse.json(
  { error: 'Transcription failed', details: 'Generic error message' },
  { status: 500 }
);
```

**Important**: Never expose sensitive error details to clients. Sanitize error messages.

### File Upload Handling (route.ts:65-80)

**Pattern**:
```typescript
async function saveUploadedFile(file: File) {
  // 1. Ensure upload directory exists
  const uploadDir = getUploadDir();
  await fs.mkdir(uploadDir, { recursive: true });

  // 2. Sanitize and create unique filename
  const origName = file.name || 'upload';
  const ext = extnameSafe(origName);
  const base = sanitizeBaseName(origName.replace(new RegExp(`${ext}$`), '')) || 'upload';
  const unique = `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`;
  const filename = `${base}-${unique}${ext}`;
  const filepath = path.join(uploadDir, filename);

  // 3. Convert File to Buffer and save
  const arrayBuffer = await file.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  await fs.writeFile(filepath, buffer);

  return { filepath, filename, buffer } as const;
}
```

**Key Points**:
- Always sanitize filenames (route.ts:57-63)
- Add timestamp + random bytes for uniqueness
- Validate file types before saving
- Use Node.js `Buffer` for file operations

### Rate Limiting (route.ts:13-43)

**In-Memory Implementation**:
```typescript
const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute
const rateBuckets = new Map<string, { windowStart: number; count: number }>();

function isRateLimited(req: Request): boolean {
  const ip = getClientIp(req);
  const now = Date.now();
  const bucket = rateBuckets.get(ip);

  // First request from this IP
  if (!bucket) {
    rateBuckets.set(ip, { windowStart: now, count: 1 });
    return false;
  }

  // Window expired, reset
  if (now - bucket.windowStart > RATE_LIMIT_WINDOW_MS) {
    rateBuckets.set(ip, { windowStart: now, count: 1 });
    return false;
  }

  // Check limit
  if (bucket.count >= RATE_LIMIT_RPM) return true;
  bucket.count += 1;
  return false;
}
```

**IP Extraction** (route.ts:18-22):
```typescript
function getClientIp(req: Request): string {
  const xff = req.headers.get('x-forwarded-for');
  if (xff) return xff.split(',')[0].trim();
  return req.headers.get('x-real-ip') || 'local';
}
```

---

## Key Files Reference

### lib/config.ts (39 lines)

**Purpose**: Centralized environment variable management with type safety

**Exports**:
- `config.bcut`: BCut API settings (baseUrl, apiKey, transcribePath, timeoutMs, language, model, prompt)
- `config.uploads`: Upload settings (maxMb)
- `config.rateLimit`: Rate limiting (requestsPerMinute)

**Usage**:
```typescript
import { config } from '../../../lib/config';
const timeout = config.bcut.timeoutMs;
```

**Pattern**: Generic `getEnv<T>()` function with fallbacks, parsing, and required validation

---

### lib/constants.ts (27 lines)

**Purpose**: File type allowlists for upload validation

**Exports**:
- `ALLOWED_MIME_TYPES`: Set of allowed MIME types (audio/video)
- `ALLOWED_EXTENSIONS`: Set of allowed file extensions

**Allowed Types**:
- **Audio**: mp3, wav, webm, ogg, m4a, aac, flac
- **Video**: mp4, webm, ogg

**Usage**:
```typescript
import { ALLOWED_MIME_TYPES, ALLOWED_EXTENSIONS } from '../../../lib/constants';

if (!ALLOWED_MIME_TYPES.has(file.type)) {
  throw new Error('Unsupported file type');
}
```

---

### lib/bcut.ts (135 lines)

**Purpose**: BCut ASR API adapter with retry logic and error handling

**Key Exports**:
```typescript
export type BcutTranscribeInput = {
  buffer: Buffer;
  filename: string;
  mimeType: string;
};

export type BcutTranscribeOptions = {
  language?: string;
  model?: string;
  prompt?: string;
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
    raw: unknown;
  };
};

export async function bcutTranscribe(
  input: BcutTranscribeInput,
  options?: BcutTranscribeOptions
): Promise<BcutTranscribeResult>;
```

**Key Features**:
- FormData construction for multipart uploads
- Timeout handling with AbortController
- Bearer token authentication
- Response parsing (JSON/text fallback)
- Extracts text from multiple possible fields (`text` or `transcript`)
- Comprehensive error handling

**Usage**:
```typescript
import { bcutTranscribe } from '../../../lib/bcut';

const result = await bcutTranscribe(
  { buffer, filename, mimeType },
  { language: 'zh', model: 'default', prompt: 'hint text' }
);
console.log(result.text);
```

---

### app/api/transcribe/route.ts (163 lines)

**Purpose**: Main API endpoint for transcription

**Handlers**:
1. **GET**: Health check + server configuration
2. **POST**: File upload + transcription processing

**Flow** (POST):
1. Rate limiting check (429 if exceeded)
2. Parse multipart form data
3. Validate file presence (400 if missing)
4. Validate file type (415 if unsupported)
5. Validate file size (413 if too large)
6. Validate prompt length (400 if > 1000 chars)
7. Save file to disk
8. Call BCut API via `bcutTranscribe()`
9. Return result (200) or error (500)

**Security**:
- IP-based rate limiting
- File type validation (MIME + extension)
- File size limits
- Filename sanitization
- No sensitive error details exposed

---

### app/components/TranscriptionForm.tsx (160 lines)

**Purpose**: Client-side form for audio/video upload and transcription

**State Management**:
```typescript
const [file, setFile] = useState<File | null>(null);
const [language, setLanguage] = useState('');
const [model, setModel] = useState('');
const [prompt, setPrompt] = useState('');
const [result, setResult] = useState<TranscriptionResult | null>(null);
const [loading, setLoading] = useState(false);
const [error, setError] = useState('');
const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
```

**Form Submission**:
```typescript
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();

  // Client-side validation
  if (!file) {
    setError('Please select a file');
    return;
  }

  // FormData construction
  const formData = new FormData();
  formData.append('file', file);
  if (language) formData.append('language', language);
  if (model) formData.append('model', model);
  if (prompt) formData.append('prompt', prompt);

  // API call
  setLoading(true);
  setError('');
  const res = await fetch('/api/transcribe', {
    method: 'POST',
    body: formData,
  });

  // Handle response...
};
```

**Key Features**:
- File size validation before upload
- Fetches server config on mount
- Displays results with metadata
- Error handling with user-friendly messages
- Loading states during API calls

---

### app/components/ServerInfo.tsx (78 lines)

**Purpose**: Display server configuration (max upload, rate limits, allowed types)

**Fetches**: GET /api/transcribe on component mount

**Display**:
- Max upload size (MB)
- Rate limit (requests/minute)
- Supported file types (comma-separated)
- Error message if config fetch fails

---

### app/page.tsx (15 lines)

**Purpose**: Home page (server component)

**Structure**:
```typescript
export default function Home() {
  return (
    <main className="...">
      <h1>语音转写 Demo</h1>
      <p>上传音频或视频文件，使用 BCut ASR 接口进行转写。</p>
      <ServerInfo />
      <TranscriptionForm />
    </main>
  );
}
```

---

### app/layout.tsx (16 lines)

**Purpose**: Root layout with metadata

**Metadata**:
```typescript
export const metadata = {
  title: '语音转写 Demo',
  description: 'Next.js 14 + BCut ASR',
};
```

**Structure**:
```typescript
export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
```

---

### app/globals.css

**Purpose**: Global styles with Tailwind directives

**Structure**:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* CSS variables for theming */
  }
}
```

---

## Environment Configuration

### Required Variables

```bash
BCUT_BASE_URL=https://api.bcut.ai   # BCut API base URL (required)
BCUT_API_KEY=your_api_key_here      # API authentication key (required)
```

### Optional Variables

```bash
# BCut Settings
BCUT_TRANSCRIBE_PATH=/v1/transcribe  # Default: /v1/transcribe
BCUT_LANGUAGE=                       # Default: undefined (e.g., zh, en, auto)
BCUT_MODEL=                          # Default: undefined
BCUT_PROMPT=                         # Default: undefined
BCUT_TIMEOUT_MS=120000               # Default: 120000 (2 minutes)

# Upload Settings
UPLOAD_MAX_MB=100                    # Default: 100 MB

# Rate Limiting
RATE_LIMIT_RPM=60                    # Default: 60 requests/minute
```

### Setup Process

1. Copy template: `cp .env.example .env.local`
2. Fill in required values (`BCUT_BASE_URL`, `BCUT_API_KEY`)
3. Adjust optional values as needed
4. Never commit `.env.local` to version control

---

## Common Tasks

### Adding a New API Route

1. **Create route file**: `app/api/your-route/route.ts`
2. **Define runtime and caching**:
   ```typescript
   export const runtime = 'nodejs';
   export const dynamic = 'force-dynamic';
   ```
3. **Implement handlers**:
   ```typescript
   export async function GET(req: Request) {
     return NextResponse.json({ data: '...' });
   }

   export async function POST(req: Request) {
     const body = await req.json();
     return NextResponse.json({ result: '...' });
   }
   ```
4. **Add error handling** with appropriate status codes
5. **Test** with `curl` or Postman

---

### Adding a New Component

1. **Create file**: `app/components/YourComponent.tsx`
2. **Add client directive if needed**: `'use client';`
3. **Define component**:
   ```typescript
   'use client';

   import { useState } from 'react';

   export default function YourComponent() {
     const [state, setState] = useState<Type>(initialValue);

     return (
       <div className="...">
         {/* JSX */}
       </div>
     );
   }
   ```
4. **Import in parent**: `import YourComponent from './components/YourComponent';`
5. **Run type check**: `npm run typecheck`
6. **Format**: `npm run format`

---

### Adding a New Utility Function

1. **Choose location**:
   - General utilities: `lib/utils.ts` (create if needed)
   - Domain-specific: `lib/your-domain.ts`
2. **Define with types**:
   ```typescript
   export function yourFunction(param: Type): ReturnType {
     // Implementation
     return result;
   }
   ```
3. **Export**: `export { yourFunction };`
4. **Import**: `import { yourFunction } from '../../../lib/utils';`
5. **Test**: Write test cases or manual testing

---

### Modifying File Type Allowlist

1. **Edit**: `lib/constants.ts`
2. **Add MIME types**:
   ```typescript
   export const ALLOWED_MIME_TYPES = new Set<string>([
     // Existing...
     'audio/new-type',
   ]);
   ```
3. **Add extensions**:
   ```typescript
   export const ALLOWED_EXTENSIONS = new Set<string>([
     // Existing...
     '.newext',
   ]);
   ```
4. **Update documentation**: README.md, CLAUDE.md
5. **Test**: Upload file with new type

---

### Adding Environment Variables

1. **Add to `.env.example`** with description:
   ```bash
   # Description of what this does
   NEW_VAR_NAME=default_value
   ```
2. **Update `lib/config.ts`**:
   ```typescript
   export const config = {
     // Existing...
     newSection: {
       varName: getEnv<string>({ name: 'NEW_VAR_NAME', fallback: 'default' }),
     },
   };
   ```
3. **Use in code**:
   ```typescript
   import { config } from '../../../lib/config';
   const value = config.newSection.varName;
   ```
4. **Update documentation**: README.md, CLAUDE.md

---

### Debugging API Routes

1. **Add console logs**:
   ```typescript
   console.log('Request headers:', req.headers);
   console.log('Request body:', body);
   ```
2. **Check dev server output** in terminal
3. **Use Network tab** in browser DevTools
4. **Test with curl**:
   ```bash
   curl -X POST http://localhost:3000/api/transcribe \
     -F "file=@test.mp3" \
     -F "language=zh"
   ```
5. **Remove logs** before committing

---

### Running Type Checks

```bash
npm run typecheck           # Full project type check
npx tsc --noEmit file.ts    # Check specific file
```

**Fix common errors**:
- Missing types: Add `@types/package-name`
- Type mismatches: Add proper type annotations
- Null checks: Use optional chaining `?.` or nullish coalescing `??`

---

### Formatting Code

```bash
npm run format              # Format all files
npm run format:check        # Check without modifying
npx prettier --write file.ts # Format specific file
```

---

### Linting

```bash
npm run lint                # Run ESLint
npm run lint -- --fix       # Auto-fix issues
```

**Common fixes**:
- Unused variables: Remove or prefix with `_`
- Missing dependencies: Add to `useEffect` dependency array
- Prefer const: Change `let` to `const` where possible

---

## Security Considerations

### File Upload Security

1. **Dual Validation** (route.ts:90-103):
   - MIME type check: `ALLOWED_MIME_TYPES.has(file.type)`
   - Extension check: `ALLOWED_EXTENSIONS.has(ext)`
   - Both must pass

2. **Filename Sanitization** (route.ts:57-63):
   - Remove special characters
   - Replace spaces with hyphens
   - Limit length to 80 characters
   - Pattern: `[a-zA-Z0-9._-]` only

3. **Unique Filenames** (route.ts:72):
   - Timestamp: `Date.now()`
   - Random bytes: `crypto.randomBytes(4).toString('hex')`
   - Format: `{basename}-{timestamp}-{random}{ext}`

4. **File Size Limits**:
   - Client-side check before upload (TranscriptionForm.tsx)
   - Server-side validation (route.ts)
   - Configurable via `UPLOAD_MAX_MB`

### API Security

1. **Rate Limiting** (route.ts:13-43):
   - IP-based tracking
   - Sliding window algorithm
   - Configurable via `RATE_LIMIT_RPM`

2. **Authentication**:
   - BCut API: Bearer token (config.bcut.apiKey)
   - No user authentication (add if needed)

3. **Error Handling**:
   - Never expose sensitive details
   - Generic error messages to clients
   - Detailed logs on server (console.error)

4. **CORS**:
   - Not configured (same-origin only)
   - Add headers if needed for external clients

### Environment Security

1. **Never commit**:
   - `.env.local`
   - `.env` files with secrets
   - API keys in code

2. **Validate on startup**:
   - Required env vars throw errors early (config.ts:11-12)
   - Prevents runtime failures

3. **Use `.env.example`**:
   - Template for required variables
   - No actual secrets
   - Safe to commit

### Data Security

1. **File Storage**:
   - Local disk (`data/uploads/`)
   - Not version controlled (`.gitignore`)
   - Consider cloud storage for production

2. **No Database**:
   - No user data stored
   - In-memory rate limiting (resets on restart)
   - Add persistent storage if needed

---

## Best Practices

### TypeScript

- **Enable strict mode**: Always use `"strict": true`
- **Avoid `any`**: Use proper types or `unknown`
- **Use type imports**: `import type { Type } from '...'` when only importing types
- **Define return types**: Explicit function return types improve readability
- **Use const assertions**: `as const` for literal types

### React

- **Client vs Server**:
  - Default to server components (faster, smaller bundle)
  - Use `"use client"` only when needed (hooks, events, browser APIs)

- **State Management**:
  - Keep state close to where it's used
  - Avoid prop drilling (if needed, consider Context)
  - Use `useState` for local state, not global

- **Effects**:
  - Always include cleanup functions
  - Correct dependency arrays (no missing dependencies)
  - Avoid infinite loops (be careful with object dependencies)

- **Forms**:
  - Use controlled components (`value` + `onChange`)
  - Prevent default on submit: `e.preventDefault()`
  - Validate on both client and server

### Next.js

- **App Router**:
  - Server components by default
  - Client components for interactivity
  - API routes in `app/api/`

- **Performance**:
  - Use dynamic imports for large components
  - Optimize images with `next/image`
  - Minimize client-side JavaScript

- **Caching**:
  - Use `force-dynamic` for real-time data
  - Cache static content when possible
  - Understand default caching behavior

### Error Handling

- **Always handle errors**:
  - Try-catch in async functions
  - Error boundaries for React components (add if needed)
  - Graceful degradation

- **User-friendly messages**:
  - Clear, actionable error messages
  - No technical jargon for end users
  - Suggest solutions when possible

- **Logging**:
  - `console.error()` for server errors
  - `console.log()` sparingly (remove before production)
  - Consider structured logging for production

### Performance

- **Bundle Size**:
  - Minimize dependencies
  - Use dynamic imports for code splitting
  - Check bundle size: `npm run build`

- **Network**:
  - Minimize API calls
  - Use loading states
  - Implement caching where appropriate

- **File Operations**:
  - Stream large files when possible
  - Clean up temporary files
  - Monitor disk usage

### Code Quality

- **Before Committing**:
  - Run `npm run typecheck`
  - Run `npm run lint`
  - Run `npm run format:check`
  - Test functionality manually

- **Code Reviews**:
  - Check for security issues
  - Verify error handling
  - Ensure tests pass (add tests when needed)
  - Review for maintainability

- **Documentation**:
  - Comment complex logic
  - Update README.md when adding features
  - Keep CLAUDE.md current
  - Document API changes

### Git Practices

- **Commit Messages**:
  - Format: `type(scope): description`
  - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
  - Be descriptive but concise

- **Branch Management**:
  - Keep branches focused and small
  - Merge frequently to avoid conflicts
  - Delete branches after merging

- **Never Commit**:
  - Secrets or API keys
  - `node_modules/`
  - Build artifacts (`.next/`)
  - User data (`data/uploads/`)
  - IDE-specific files (`.vscode/`, `.idea/`)

---

## Troubleshooting

### Common Issues

**1. TypeScript Errors**:
- Run `npm run typecheck` to see all errors
- Check for missing type definitions: `npm install --save-dev @types/package-name`
- Verify imports are correct

**2. Build Failures**:
- Clear cache: `rm -rf .next`
- Reinstall: `rm -rf node_modules && npm install`
- Check Node.js version compatibility

**3. API Route Not Working**:
- Verify route file location: `app/api/[route]/route.ts`
- Check runtime export: `export const runtime = 'nodejs'`
- Inspect browser Network tab for errors

**4. Environment Variables Not Loading**:
- File must be named `.env.local`
- Restart dev server after changes
- Verify variable names match (case-sensitive)

**5. File Upload Fails**:
- Check file type is in allowlist (lib/constants.ts)
- Verify file size under limit
- Ensure `data/uploads/` directory exists

---

## Additional Resources

- **Next.js 14 Docs**: https://nextjs.org/docs
- **React Docs**: https://react.dev
- **TypeScript Handbook**: https://www.typescriptlang.org/docs
- **Tailwind CSS**: https://tailwindcss.com/docs
- **Node.js API**: https://nodejs.org/docs/latest/api/

---

## Version History

- **v1.0.0** (2025-11-16): Initial comprehensive documentation for AI assistants

---

## Notes for AI Assistants

When working with this codebase:

1. **Always run type checks** before committing code
2. **Follow the established patterns** (see Code Conventions section)
3. **Validate environment setup** before running commands
4. **Use relative imports** (no path aliases configured)
5. **Add proper error handling** to all async operations
6. **Keep components small and focused** (single responsibility)
7. **Document complex logic** with comments
8. **Test changes manually** before marking complete
9. **Never commit sensitive data** (API keys, .env files)
10. **Update this file** if you add new patterns or conventions

**Quick Reference**:
- Config: `lib/config.ts`
- Constants: `lib/constants.ts`
- BCut API: `lib/bcut.ts`
- Main API: `app/api/transcribe/route.ts`
- Form: `app/components/TranscriptionForm.tsx`

**Remember**: This is a production-ready codebase with strict type checking and quality standards. Maintain the same level of rigor in all changes.
