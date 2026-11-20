import Foundation

// Audio decoding is outside this suite; the controllable worker tests deletion/cancellation.
actor TranscriptionProbe {
    static let shared = TranscriptionProbe()
    var started = Set<Int>(), stopped = Set<Int>()
    func start(_ id: Int) { started.insert(id) }
    func stop(_ id: Int) { stopped.insert(id) }
}
final class MLXEngine {
    static func languageName(_ code: String) -> String? { nil }
    func process(_ rec: Rec, hooks: Hooks) async throws -> (txt: String, srt: String, duration: Double) {
        await hooks.plan?([Chunk(start: 0, end: 0.8), Chunk(start: 0.8, end: 2)])
        await TranscriptionProbe.shared.start(rec.id)
        for _ in 0..<200 {
            if hooks.cancelled() {
                await TranscriptionProbe.shared.stop(rec.id)
                throw URLError(.cancelled)
            }
            try await Task.sleep(for: .milliseconds(10))
        }
        fatalError("Deleted transcription was not cancelled")
    }
}
enum LocalModel { static let asr = "test-audio-model" }
enum AudioIO { static func duration(of url: URL) async throws -> Double { fatalError("Unexpected audio decoding") } }
enum Notifier { static func post(title: String, body: String) async { fatalError("Unexpected transcription notification") } }

@main
struct SummaryPipelineTests {
    static let client = TranscriptClient()
    static func check(_ condition: @autoclosure () -> Bool, _ name: String) {
        guard condition() else { fputs("FAIL \(name)\n", stderr); exit(1) }
        print("PASS \(name)")
    }
    static func until(_ predicate: (TSummary) -> Bool) async throws -> TSummary {
        for _ in 0..<150 {
            let summary = try await client.summary(1)
            if predicate(summary) { return summary }
            try await Task.sleep(for: .milliseconds(50))
        }
        fatalError("Timed out waiting for summary")
    }
    static func main() async throws {
        check(AppPaths.isTestRoot, "summary pipeline uses an isolated data root")
        AppPaths.prepareDataDirectory()
        let root = AppPaths.layout.dataDir
        var txt = root.appendingPathComponent("test.txt"), srt = root.appendingPathComponent("test.srt")
        try "今天检查总结的流式显示和三级列表。".write(to: txt, atomically: true, encoding: .utf8)
        try "1\n00:00:00,000 --> 00:00:02,000\n今天检查总结的流式显示和三级列表。\n".write(to: srt, atomically: true, encoding: .utf8)
        let record = Rec(id: 1, name: "流式验收", sourcePath: "/missing-test.wav", mode: "online", language: "zh", status: "done", createdAt: "2026-11-09T10:00:00Z", txtPath: txt.path, srtPath: srt.path)
        var shared = record
        shared.id = 2; shared.name = "旧版共用输出的另一条记录"
        try JSONEncoder().encode([record, shared]).write(to: root.appendingPathComponent("tasks.json"))

        let initial = try await client.enableSummary(1)
        check(initial.pending && initial.content == nil, "start returns a pending state immediately")
        let first = try await until { $0.pending && $0.content != nil }
        check(first.markdown.contains("总结"), "first streamed text is observable before completion")
        let second = try await until { $0.pending && $0.markdown.count > first.markdown.count }
        check(second.pending, "subsequent text arrives while the request is running")
        let done = try await until { !$0.pending }
        check(done.status == "done" && done.markdown.contains("具体说明"), "final streamed result is complete")
        let document = MarkdownDocument(done.markdown)
        check(document.blocks.compactMap { $0.list?.depth } == [0, 1, 2], "real network result retains three list levels")
        let saved = try JSONDecoder().decode([Rec].self, from: Data(contentsOf: root.appendingPathComponent("tasks.json")))
        check(saved[0].summary?["markdown"]?.first == done.markdown, "final Markdown is persisted")

        _ = try await client.enableSummary(1, prompt: "__old__")
        _ = try await until { $0.markdown.contains("旧请求") }
        _ = try await client.enableSummary(1, prompt: "__new__")
        let replacement = try await until { !$0.pending }
        check(replacement.status == "done" && replacement.markdown.contains("新请求"), "replacement request completes")
        try await Task.sleep(for: .milliseconds(1100))
        let stable = try await client.summary(1)
        check(stable.status == "done" && stable.markdown == replacement.markdown, "cancelled request cannot overwrite the replacement")

        _ = try await client.enableSummary(1, prompt: "__json__")
        let json = try await until { !$0.pending }
        check(json.status == "done" && json.markdown.contains("普通 JSON"), "provider without SSE remains supported")
        for prompt in ["__length__", "__json__ __length__"] {
            _ = try await client.enableSummary(1, prompt: prompt)
            let truncated = try await until { !$0.pending }
            check(truncated.status == "failed" && truncated.error?.contains("尚未完成") == true, "truncated output is explicitly incomplete: \(prompt)")
            check(!truncated.markdown.isEmpty, "truncated output preserves received text: \(prompt)")
            let persisted = try JSONDecoder().decode([Rec].self, from: Data(contentsOf: root.appendingPathComponent("tasks.json")))
            check(persisted[0].summaryStatus == "failed" && persisted[0].summaryError == truncated.error && persisted[0].summary?["markdown"]?.first == truncated.markdown, "incomplete state and text are persisted: \(prompt)")
            _ = try await client.enableSummary(1, prompt: "__new__")
            let retried = try await until { !$0.pending }
            check(retried.status == "done" && retried.error == nil && retried.markdown.contains("新请求"), "retry replaces incomplete result and clears error: \(prompt)")
        }
        _ = try await client.enableSummary(1, prompt: "__error__")
        let error = try await until { !$0.pending }
        check(error.status == "failed" && error.error?.contains("401") == true, "HTTP errors reach the summary state")
        for prompt in ["__disconnect__", "__stream_error__", "__filter__"] {
            _ = try await client.enableSummary(1, prompt: prompt)
            let interrupted = try await until { !$0.pending }
            check(interrupted.status == "failed" && interrupted.error != nil, "interrupted stream cannot be reported as complete: \(prompt)")
            check(!interrupted.markdown.isEmpty, "interrupted stream retains received text: \(prompt)")
        }
        (txt, srt) = try await editing(txt: txt, srt: srt)
        let longInput = String(repeating: "文稿内容。", count: 13000) + "结尾不可丢失"
        try longInput.write(to: txt, atomically: true, encoding: .utf8)
        try "".write(to: srt, atomically: true, encoding: .utf8)
        _ = try await client.enableSummary(1, prompt: "__full_input__")
        let full = try await until { !$0.pending }
        check(full.status == "done" && full.markdown.contains("全文已收到"), "long transcript reaches the provider without silent truncation")
        try "".write(to: txt, atomically: true, encoding: .utf8)
        do {
            _ = try await client.enableSummary(1)
            check(false, "empty transcript must be rejected")
        } catch { check(error.localizedDescription.contains("文稿为空"), "empty transcript is rejected before starting a request") }
        try "测试文稿".write(to: txt, atomically: true, encoding: .utf8)
        try await deletion(txt: txt)
    }

    static func editing(txt originalTXT: URL, srt originalSRT: URL) async throws -> (URL, URL) {
        var txt = originalTXT, srt = originalSRT
        let first = "甲：好。", second = "乙：这是一段明显更长的说明，请保留它的时间范围。"
        let original = "\(first)\n\(second)\n"
        let cues = [Cue(id: 0, stamp: "00:00:00,000 --> 00:00:01,000", start: 0, text: first),
                    Cue(id: 1, stamp: "00:00:01,000 --> 00:00:08,000", start: 1, text: second)]
        try original.write(to: txt, atomically: true, encoding: .utf8)
        try serializeSRT(cues).write(to: srt, atomically: true, encoding: .utf8)
        try await client.renameSpeakers(1, replacements: ["甲": "乙", "乙": "很长的新说话人名称"])
        let detail = try await client.detail(1)
        txt = URL(fileURLWithPath: detail.task.txtPath!)
        srt = URL(fileURLWithPath: detail.task.srtPath!)
        let untouched = try await client.file(2, kind: "txt")
        check(untouched == original, "editing a legacy shared output cannot change another record")
        check(txt != originalTXT && srt != originalSRT, "legacy shared files are detached before editing")
        let edited = parseSRT(try String(contentsOf: srt, encoding: .utf8))
        check(edited.map(\.stamp) == cues.map(\.stamp), "speaker rename keeps subtitle time ranges")
        check(edited.map(\.text) == ["乙：好。", "很长的新说话人名称：这是一段明显更长的说明，请保留它的时间范围。"], "speaker rename keeps cue boundaries and applies simultaneous replacements")
        let renamed = try String(contentsOf: txt, encoding: .utf8)
        check(renamed == "乙：好。\n很长的新说话人名称：这是一段明显更长的说明，请保留它的时间范围。\n", "speaker rename keeps transcript paragraphs")

        let previousSRT = try Data(contentsOf: srt)
        try FileManager.default.removeItem(at: txt)
        try FileManager.default.createDirectory(at: txt, withIntermediateDirectories: false)
        var changed = edited
        changed[0].text = "这个修改不能只写进字幕。"
        do {
            try await client.saveCues(1, srt: serializeSRT(changed))
            check(false, "partial output save must fail")
        } catch {}
        let afterFailure = try Data(contentsOf: srt)
        check(afterFailure == previousSRT, "failed paired save leaves the original subtitle intact")
        try FileManager.default.removeItem(at: txt)
        try renamed.write(to: txt, atomically: true, encoding: .utf8)
        try await client.saveCues(1, srt: serializeSRT(changed))
        let savedText = try String(contentsOf: txt, encoding: .utf8)
        check(savedText.contains(changed[0].text), "successful paired save updates both outputs")
        return (txt, srt)
    }

    static func deletion(txt: URL) async throws {
        _ = try await client.enableSummary(1, prompt: "__old__")
        _ = try await until { $0.markdown.contains("旧请求") }
        try await client.delete(1)
        try await Task.sleep(for: .milliseconds(900))
        let removed = try await client.summary(1)
        check(removed.content == nil && removed.status == "disabled", "deleted summary cannot remain live or be resurrected")
        do {
            _ = try await client.enableSummary(1)
            check(false, "deleted record must not start a summary")
        } catch { check(error.localizedDescription.contains("任务不存在"), "deleted record rejects new requests") }
        try await client.delete(2)
        let id = try await client.create(path: txt.path, mode: "offline", language: "zh", engine: "auto")
        check(id > 2, "a new task never reuses an ID from a deleted active task")
        for _ in 0..<100 {
            if await TranscriptionProbe.shared.started.contains(id) { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        let records = try JSONDecoder().decode([Rec].self, from: Data(contentsOf: AppPaths.layout.dataDir.appendingPathComponent("tasks.json")))
        check(records.first(where: { $0.id == id })?.segments == [Chunk(start: 0, end: 0.8), Chunk(start: 0.8, end: 2)], "audio segment plan is persisted before checkpoint processing")
        try await client.delete(id)
        for _ in 0..<100 {
            if await TranscriptionProbe.shared.stopped.contains(id) { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        let stopped = await TranscriptionProbe.shared.stopped.contains(id)
        check(stopped, "deleting a running transcription stops its worker")
    }
}
