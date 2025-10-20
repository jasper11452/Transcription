import TranscriptionForm from './components/TranscriptionForm';

export default function Home() {
  return (
    <main className="min-h-screen p-8 md:p-12">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-3xl font-bold">音频转写演示</h1>
        <p className="text-gray-600">上传音频/视频文件，调用后端 /api/transcribe 接口进行转写。</p>
        <TranscriptionForm />
      </div>
    </main>
  );
}
