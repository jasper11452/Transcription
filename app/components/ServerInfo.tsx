"use client";

import { useEffect, useState } from "react";

type ServerInfo = {
  status: string;
  maxUploadMB: number;
  rateLimitRPM: number;
  allowed: {
    mimeTypes: string[];
    extensions: string[];
  };
};

export default function ServerInfo() {
  const [info, setInfo] = useState<ServerInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch("/api/transcribe", { method: "GET", cache: "no-store" });
        const data = (await res.json()) as ServerInfo | { error: string };
        if (!alive) return;
        if ("error" in data) {
          setError(data.error);
        } else {
          setInfo(data);
        }
      } catch (e: unknown) {
        if (!alive) return;
        const msg = e instanceof Error ? e.message : "无法获取服务配置";
        setError(msg);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <div className="rounded-md border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
        服务信息加载失败：{error}
      </div>
    );
  }

  if (!info) {
    return <div className="text-sm text-gray-500">正在加载服务信息...</div>;
  }

  return (
    <div className="rounded-md border border-gray-200 bg-white p-4 text-sm">
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <div>
          <span className="text-gray-500">最大上传：</span>
          <span className="font-medium">{info.maxUploadMB} MB</span>
        </div>
        <div>
          <span className="text-gray-500">速率限制：</span>
          <span className="font-medium">{info.rateLimitRPM} 次/分钟</span>
        </div>
      </div>
      <div className="mt-2 text-gray-500">
        <div className="mb-1">支持的类型：</div>
        <div className="flex flex-wrap gap-2">
          {info.allowed.extensions.map((ext) => (
            <span key={ext} className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
              {ext}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
