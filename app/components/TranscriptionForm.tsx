"use client";

import { useEffect, useMemo, useState } from "react";
import { ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES } from "../../lib/constants";

type ApiResponse =
  | { error: string; details?: string }
  | {
      text: string;
      metadata: Record<string, unknown>;
    };

type ServerInfo = {
  status: string;
  maxUploadMB: number;
  rateLimitRPM: number;
  allowed: { mimeTypes: string[]; extensions: string[] };
};

export default function TranscriptionForm() {
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("");
  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch("/api/transcribe", { method: "GET", cache: "no-store" });
        const data = (await res.json()) as ServerInfo | { error: string };
        if (!alive) return;
        if ("error" in data) return;
        setServerInfo(data);
      } catch {
        // ignore
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const accept = useMemo(() => {
    const mimes = serverInfo?.allowed?.mimeTypes ?? Array.from(ALLOWED_MIME_TYPES);
    const exts = serverInfo?.allowed?.extensions ?? Array.from(ALLOWED_EXTENSIONS);
    return [...mimes, ...exts].join(",");
  }, [serverInfo]);

  const maxUploadMB = serverInfo?.maxUploadMB ?? 100;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResult(null);
    if (!file) return;

    // client-side size guard for better UX
    const maxBytes = maxUploadMB * 1024 * 1024;
    if (file.size > maxBytes) {
      setResult({ error: `文件过大，最大支持 ${maxUploadMB} MB` });
      return;
    }

    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (language.trim()) fd.append("language", language.trim());
      if (model.trim()) fd.append("model", model.trim());
      if (prompt.trim()) fd.append("prompt", prompt.trim());

      const res = await fetch("/api/transcribe", { method: "POST", body: fd });
      const data = (await res.json()) as ApiResponse;
      setResult(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '请求失败';
      setResult({ error: message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-2xl space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1">音频/视频文件</label>
        <input
          type="file"
          accept={accept}
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
          required
        />
        <p className="text-xs text-gray-500 mt-1">支持: {accept}</p>
        <p className="text-xs text-gray-500 mt-1">最大上传大小：{maxUploadMB} MB</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">语言(可选)</label>
          <input
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            placeholder="如: zh, en, auto"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">模型(可选)</label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="如: large-v3"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="md:col-span-1">
          <label className="block text-sm font-medium mb-1">提示词(可选)</label>
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="最多1000字"
            maxLength={1000}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={!file || loading}
        className="inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-white text-sm font-semibold shadow-sm hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "处理中..." : "开始转写"}
      </button>

      {result && "error" in result && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          错误: {result.error}
          {"details" in result && result.details ? <div className="mt-1">{String(result.details)}</div> : null}
        </div>
      )}

      {result && !("error" in result) && (
        <div className="rounded-md border border-gray-200 bg-white p-4">
          <h3 className="font-semibold mb-2">识别结果</h3>
          <pre className="whitespace-pre-wrap break-words text-sm bg-gray-50 p-3 rounded-md max-h-80 overflow-auto">{result.text}</pre>

          <details className="mt-3 text-sm">
            <summary className="cursor-pointer select-none">元数据</summary>
            <pre className="whitespace-pre-wrap break-words bg-gray-50 p-3 rounded-md overflow-auto">{JSON.stringify(result.metadata, null, 2)}</pre>
          </details>
        </div>
      )}
    </form>
  );
}
