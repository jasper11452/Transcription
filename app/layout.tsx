import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: '语音转写 Demo',
  description: '基于 Next.js 14 + TypeScript + Tailwind 的语音转写演示',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="antialiased text-gray-900 bg-white">{children}</body>
    </html>
  );
}
