export const ALLOWED_MIME_TYPES = new Set<string>([
  // Audio
  'audio/mpeg', // .mp3
  'audio/mp3',
  'audio/wav',
  'audio/x-wav',
  'audio/webm',
  'audio/ogg',
  'audio/m4a',
  'audio/aac',
  'audio/flac',
  // Video (some ASR providers accept video directly)
  'video/mp4',
  'video/webm',
  'video/ogg',
]);

export const ALLOWED_EXTENSIONS = new Set<string>([
  '.mp3',
  '.wav',
  '.webm',
  '.ogg',
  '.m4a',
  '.aac',
  '.flac',
  '.mp4',
]);
