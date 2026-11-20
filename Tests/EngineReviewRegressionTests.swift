import Foundation

// These substitutes prevent the isolated suite from reading preferences or configuration.
enum UserDefaults {
    static let standard = Selection()
    final class Selection {
        var model = "standard"
        func string(forKey: String) -> String? { model }
    }
}
enum ConfigEnv { static func read(_ key: String) -> String? { nil } }
enum AppPaths { static let serverPort = 8000 }
enum MLXEngine { static func languageName(_ code: String) -> String? { nil } }
struct TFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

@main
struct EngineReviewRegressionTests {
    static var checks = 0
    static func check(_ condition: @autoclosure () -> Bool, _ label: String) {
        precondition(condition(), label)
        checks += 1
        print("PASS \(label)")
    }

    @MainActor static func main() throws {
        let fm = FileManager.default
        let temporary = fm.temporaryDirectory.appendingPathComponent("asr-engine-review-" + UUID().uuidString)
        try fm.createDirectory(at: temporary, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: temporary) }
        try outputs(in: temporary)
        readiness()
        try responses()
        print("\(checks) isolated engine regression checks passed")
    }

    static func outputs(in temporary: URL) throws {
        let fm = FileManager.default
        let source = temporary.appendingPathComponent("meeting.wav")
        let notes = temporary.appendingPathComponent("meeting.txt")
        let captions = temporary.appendingPathComponent("meeting.srt")
        try Data("original audio".utf8).write(to: source)
        try Data("my notes".utf8).write(to: notes)
        try Data("edited captions".utf8).write(to: captions)
        let root = temporary.appendingPathComponent("outputs")
        func write(_ id: Int, _ source: URL, _ text: String) throws -> (txt: URL, srt: URL) {
            try TranscriptionOutput.write(source: source, taskID: id, root: root, text: text,
                                          subtitles: "captions: " + text, checkCancellation: {})
        }
        let first = try write(1, source, "first transcription")
        try Data("manually edited transcript".utf8).write(to: first.txt)
        let rerun = try write(1, source, "rerun")
        let other = try write(2, temporary.appendingPathComponent("meeting.mp4"), "other recording")
        let paths = [first.txt, first.srt, rerun.txt, rerun.srt, other.txt, other.srt]
        check(Set(paths).count == paths.count, "same stems, different tasks and reruns have unique output paths")
        check(first.txt.deletingLastPathComponent() != rerun.txt.deletingLastPathComponent(), "reruns own separate directories")
        check(first.txt.deletingLastPathComponent().deletingLastPathComponent() != other.txt.deletingLastPathComponent().deletingLastPathComponent(), "tasks own separate parent directories")
        check(first.txt.lastPathComponent == "meeting.txt" && first.srt.lastPathComponent == "meeting.srt", "output filenames remain readable")
        let oldText = try String(contentsOf: first.txt, encoding: .utf8)
        let oldNotes = try String(contentsOf: notes, encoding: .utf8)
        let oldCaptions = try String(contentsOf: captions, encoding: .utf8)
        check(oldText == "manually edited transcript", "rerun preserves edited previous transcription")
        check(oldNotes == "my notes" && oldCaptions == "edited captions", "source-adjacent user files remain intact")
        let rerunText = try String(contentsOf: rerun.txt, encoding: .utf8)
        let otherText = try String(contentsOf: other.txt, encoding: .utf8)
        check(rerunText == "rerun" && otherText == "other recording", "each task reads its own content")

        // Fail at entry, before TXT, before SRT, and after both writes.
        for stopAt in 1...4 {
            var calls = 0
            let cancelRoot = temporary.appendingPathComponent("cancel-\(stopAt)")
            do {
                _ = try TranscriptionOutput.write(source: source, taskID: 10, root: cancelRoot,
                    text: "cancelled", subtitles: "cancelled", checkCancellation: {
                        calls += 1
                        if calls == stopAt { throw CancellationError() }
                    })
                preconditionFailure("cancelled output must throw")
            } catch is CancellationError {
                let files = fm.enumerator(at: cancelRoot, includingPropertiesForKeys: nil)?.allObjects as? [URL] ?? []
                check(!files.contains { ["txt", "srt"].contains($0.pathExtension) }, "cancellation at boundary \(stopAt) leaves no output files")
            }
        }
        // Inject occupied destinations after allocation to exercise exclusive writes.
        for occupiedExtension in ["txt", "srt"] {
            let collisionRoot = temporary.appendingPathComponent("occupied-" + occupiedExtension)
            var calls = 0
            var occupied: URL?
            do {
                _ = try TranscriptionOutput.write(source: source, taskID: 20, root: collisionRoot,
                    text: "must not overwrite", subtitles: "must not overwrite", checkCancellation: {
                        calls += 1
                        if calls == (occupiedExtension == "txt" ? 2 : 3) {
                            let task = collisionRoot.appendingPathComponent("20")
                            let run = try fm.contentsOfDirectory(at: task, includingPropertiesForKeys: nil).first!
                            occupied = run.appendingPathComponent("meeting." + occupiedExtension)
                            try Data("existing user file".utf8).write(to: occupied!)
                        }
                    })
                preconditionFailure("occupied output must fail")
            } catch {
                let preserved = try String(contentsOf: occupied!, encoding: .utf8)
                check(preserved == "existing user file", "exclusive \(occupiedExtension) write preserves an occupied destination")
                let runFiles = try fm.contentsOfDirectory(at: occupied!.deletingLastPathComponent(), includingPropertiesForKeys: nil)
                check(runFiles == [occupied!], "failed \(occupiedExtension) output removes only files created by this run")
            }
        }

        // An occupied output root must fail without changing the existing file.
        let blocked = temporary.appendingPathComponent("blocked")
        try Data("keep me".utf8).write(to: blocked)
        do {
            _ = try TranscriptionOutput.write(source: source, taskID: 1, root: blocked,
                                             text: "new", subtitles: "new", checkCancellation: {})
            preconditionFailure("occupied root must fail")
        } catch {
            let kept = try String(contentsOf: blocked, encoding: .utf8)
            check(kept == "keep me", "allocation failure preserves existing files")
        }
    }

    @MainActor static func readiness() {
        let store = ModelStore()
        UserDefaults.standard.model = "lite"
        store.states = [LocalModel.asrLite: .ready, LocalModel.aligner: .ready, LocalModel.vad: .ready]
        check(store.offlineReady, "lite recognizer plus its dependencies enables offline transcription")
        check(store.selectedRecognizer == LocalModel.asrLite, "lite selection chooses lite recognizer")
        check(!store.requiredModels.contains { $0.repo == LocalModel.asr }, "lite download set does not require standard recognizer")
        check(!store.offlineReady(for: LocalModel.asr), "explicit recognizer readiness does not substitute lite")
        store.states[LocalModel.vad] = .missing
        check(!store.offlineReady, "offline transcription requires VAD")
        store.states = [LocalModel.asrLite: .ready]
        check(store.isReady(LocalModel.asrLite), "requested lite dictation recognizer is ready without subtitle dependencies")
        check(!store.offlineReady, "dictation readiness does not imply full offline readiness")
        UserDefaults.standard.model = "standard"
        store.states = [LocalModel.asr: .ready, LocalModel.aligner: .ready, LocalModel.vad: .ready]
        check(store.offlineReady && store.selectedRecognizer == LocalModel.asr, "standard recognizer remains usable")
        UserDefaults.standard.model = "lite"
        check(!store.offlineReady && store.selectedRecognizer == LocalModel.asrLite, "missing selected lite model does not silently use standard")

        check(Service.resolveCloud("auto")?.id == "dashscope", "auto cloud selection resolves to the documented default")
        check(Service.resolveCloud("unknown") == nil, "unknown cloud selection is rejected instead of silently using a fallback")
    }

    static func responses() throws {
        func response(_ reason: Any, text: String = "  transcript\n") -> [String: Any] {
            ["choices": [["finish_reason": reason, "message": ["content": text]]]]
        }
        let normal = try OpenRouterASR.responseText(response("stop"))
        check(normal == "transcript", "normal OpenRouter completion returns text")
        let compatible = try OpenRouterASR.responseText(response(NSNull()))
        check(compatible == "transcript", "compatible providers without a finish reason remain supported")
        let silence = try OpenRouterASR.responseText(response("stop", text: ""))
        check(silence.isEmpty, "empty completed transcription remains supported")
        for reason in ["length", "content_filter"] {
            var checkpointed = false
            do {
                _ = try OpenRouterASR.responseText(response(reason, text: "partial speech"))
                checkpointed = true
            } catch let error as TFailure {
                check(!error.message.isEmpty && !checkpointed, "\(reason) fails before a chunk can be checkpointed")
            }
            precondition(!checkpointed, "incomplete transcription must throw")
        }
        for malformed: [String: Any] in [[:], ["choices": []], ["choices": [["finish_reason": "stop", "message": [:]]]]] {
            do {
                _ = try OpenRouterASR.responseText(malformed)
                preconditionFailure("malformed response must throw")
            } catch is TFailure { check(true, "malformed provider result cannot become a successful empty chunk") }
        }
    }
}
