// Isolated tests for the real WorkspaceModel. The runner supplies API model types;
// these fakes replace client I/O and AppKit dialogs without starting an application.
import AppKit
import Foundation
import SwiftUI
import UniformTypeIdentifiers

// Unrelated presentation dependencies for typechecking the real result/editor views.
enum Brand {
    static let accent = Color.indigo
    static let onAccent = Color.white
}
struct FixturePrompt { var prompt = "fixture prompt" }
struct FixturePrompts {
    var selected = "default"
    var current = FixturePrompt()
    mutating func update(_ name: String, prompt: String) { current.prompt = prompt }
}
enum Summarizer {
    static let prompt = "fixture prompt"
    static func prompts() -> FixturePrompts { FixturePrompts() }
    static func savePrompts(_ prompts: FixturePrompts) {}
}
@MainActor enum Theme {
    static let key = "fixture-theme"
    static func apply(_ value: String) {}
}
@MainActor func openSettings(tab: String) {}
struct StreamingMarkdown: View {
    let source: String
    let live: Bool
    let onSeek: ((Double) -> Void)?
    var body: some View { Text(source) }
}
struct PromptProfileEditor: View {
    @Binding var prompts: FixturePrompts
    @Binding var text: String
    var body: some View { TextEditor(text: $text) }
}
struct TranscriptChatView: View {
    let model: WorkspaceModel
    let taskID: Int
    let onCitation: (TranscriptCitation) -> Void
    var body: some View { EmptyView() }
}
extension View {
    func glassButton(prominent: Bool = false) -> some View { self }
    func glassCapsule() -> some View { self }
    func glassPanel(radius: CGFloat) -> some View { self }
}

@MainActor
final class UserDefaults {
    static let standard = UserDefaults()
    func string(forKey: String) -> String? { nil }
    func array(forKey: String) -> [Any]? { nil }
    func set(_ value: Any?, forKey: String) {}
}

@MainActor
final class TestApplication {
    final class Dock { var badgeLabel: String? }
    let dockTile = Dock()
    var currentEvent: NSEvent? { nil }
}
@MainActor let NSApp = TestApplication()

@MainActor
final class NSAlert {
    static var response = NSApplication.ModalResponse.alertThirdButtonReturn
    static var count = 0
    var messageText = ""
    var informativeText = ""
    final class Button { var keyEquivalent = "" }
    @discardableResult func addButton(withTitle: String) -> Button { Button() }
    func runModal() -> NSApplication.ModalResponse {
        Self.count += 1
        return Self.response
    }
}

@MainActor
final class NSSavePanel {
    static var last: NSSavePanel?
    static var destination: URL?
    var allowedContentTypes: [UTType] = []
    var allowsOtherFileTypes = true
    var isExtensionHidden = true
    var nameFieldStringValue = ""
    var url: URL?
    init() { Self.last = self; url = Self.destination }
    func begin(_ completion: (NSApplication.ModalResponse) -> Void) { completion(url == nil ? .cancel : .OK) }
}

@MainActor
final class TestClientState {
    static let shared = TestClientState()
    var calls: [String] = []
    var text = [1: "甲：第一段\n\n乙：第二段\n", 2: "另一条记录\n"]
    var srt = [1: "1\n00:00:00,000 --> 00:00:01,000\n甲：第一段\n\n2\n00:00:05,000 --> 00:00:09,000\n乙：第二段\n", 2: "1\n00:00:00,000 --> 00:00:02,000\n另一条记录\n"]
    var pauseWrite = false
    var writeGate: CheckedContinuation<Void, Never>?
    var failWrite = false
    var pauseDetail = false
    var detailGate: CheckedContinuation<Void, Never>?
    var pauseFile = false
    var fileGate: CheckedContinuation<Void, Never>?
    var failFile = false
    func write(_ call: String) async throws {
        calls.append(call)
        if pauseWrite { await withCheckedContinuation { writeGate = $0 } }
        if failWrite { throw TFailure(message: "synthetic write failure") }
    }
    func task(_ id: Int) -> TTask {
        TTask(id: id, name: "fixture.wav", title: nil, sourcePath: nil, mode: "offline", status: "done", progress: nil,
              engine: nil, durationS: nil, error: nil, createdAt: nil, stage: nil, running: false, cancelling: nil,
              resumable: nil, txtPath: nil, srtPath: nil, srcExists: false)
    }
}

struct TranscriptCitation: Equatable {
    let index: Int
    let quote: String
}
struct TranscriptChatTurn: Identifiable, Equatable {
    enum Status { case generating, done, stopped, failed }
    let id: UUID = UUID()
    var question = ""
    var answer = ""
    var reasoning = ""
    var status: Status = .done
    var error: String?
    var citations: [TranscriptCitation] = []
}
struct TranscriptChatConversation { var turns: [TranscriptChatTurn] = []; var activeRequest: UUID? }

@MainActor
struct TranscriptClient {
    private var state: TestClientState { .shared }
    func tasks() async throws -> [TTask] { [state.task(1), state.task(2)] }
    func detail(_ id: Int) async throws -> TDetail {
        if state.pauseDetail { await withCheckedContinuation { state.detailGate = $0 } }
        return TDetail(task: state.task(id), chunks: [])
    }
    func status() async throws -> TStatus { TStatus(onlineEngines: [], keyFields: []) }
    func file(_ id: Int, kind: String) async throws -> String {
        if state.pauseFile { await withCheckedContinuation { state.fileGate = $0 } }
        if state.failFile { throw TFailure(message: "synthetic read failure") }
        return (kind == "txt" ? state.text[id] : state.srt[id]) ?? ""
    }
    func saveTranscript(_ id: Int, text: String) async throws {
        try await state.write("text:\(id)")
        state.text[id] = text
    }
    func saveCues(_ id: Int, srt: String) async throws {
        try await state.write("cues:\(id)")
        state.srt[id] = srt
        state.text[id] = parseSRT(srt).map(\.text).joined(separator: "\n")
    }
    func renameSpeakers(_ id: Int, replacements: [String: String]) async throws {
        try await state.write("rename:\(id)")
        // The backend's rename implementation is tested by the coordinator.
    }
    func cancel(_ id: Int) async throws {}
    func resume(_ id: Int) async throws {}
    func delete(_ id: Int) async throws {}
    func estimate(path: String, mode: String, engine: String) async throws -> TEstimate {
        TEstimate(ok: false, durationS: nil, estimatedCostUsd: nil, error: "test")
    }
    func create(path: String, mode: String, language: String, engine: String, speakers: Bool, hotwords: [String]? = nil) async throws -> Int { 3 }
    func deleteInactive(_ ids: [Int]) async -> (deleted: [Int], skipped: [Int]) { (ids, []) }
    func summary(_ id: Int) async throws -> TSummary {
        TSummary(enabled: false, status: "disabled", available: false, content: nil, reasoning: nil, error: nil)
    }
    func enableSummary(_ id: Int, prompt: String?) async throws -> TSummary { try await summary(id) }
    func chat(_ id: Int) async -> TranscriptChatConversation { TranscriptChatConversation() }
    func sendChat(_ id: Int, question: String) async throws -> TranscriptChatConversation { TranscriptChatConversation() }
    func retryChat(_ id: Int, turnID: UUID) async throws -> TranscriptChatConversation { TranscriptChatConversation() }
    func stopChat(_ id: Int) async {}
    func clearChat(_ id: Int) async {}
    func audioURL(_ id: Int) -> URL { URL(fileURLWithPath: "/unused-test-audio") }
}

@main
struct WorkspaceEditingRegressionTests {
    @MainActor static func expect(_ value: Bool, _ message: String) {
        precondition(value, message)
    }
    @MainActor static func waitFor(_ predicate: () -> Bool) async {
        for _ in 0..<1000 {
            if predicate() { return }
            await Task.yield()
        }
        preconditionFailure("Test continuation was never reached")
    }
    @MainActor static func loaded(_ id: Int = 1) async -> WorkspaceModel {
        let model = WorkspaceModel()
        model.selection = .task(id)
        await model.refresh()
        expect(model.outputsFor == id, "Fixture must load")
        expect(!model.hasUnsavedEdits, "Loaded outputs must start clean")
        return model
    }
    @MainActor static func resolve(_ model: WorkspaceModel) async -> Bool {
        await withCheckedContinuation { continuation in
            model.resolveEdits { continuation.resume(returning: $0) }
        }
    }
    @MainActor static func main() async {
        let state = TestClientState.shared
        let model = await loaded()
        model.transcriptDraft = "Edited A"
        state.pauseWrite = true
        let save = Task { await model.saveTranscript("Edited A", for: 1) }
        await waitFor { state.writeGate != nil }
        expect(model.editingLocked, "A suspended save must lock editing")
        model.select(.task(2))
        expect(model.selection == .task(1), "Navigation cannot remove a saving editor")
        model.discardEdits()
        expect(model.transcriptDraft == "Edited A", "Revert cannot run during save")
        // Force a selection change to simulate an external state update while I/O awaits.
        model.selection = .task(2)
        model.txt = "B stays visible"
        model.actionError = "B error"
        state.writeGate?.resume(); state.writeGate = nil
        expect(await save.value, "The explicit save must succeed")
        expect(state.calls.last == "text:1", "Destination must stay bound to A")
        expect(state.text[1] == "Edited A" && state.text[2] == "另一条记录\n", "B must never be overwritten")
        expect(model.txt == "B stays visible" && model.actionError == "B error", "A success must not update B")
        expect(!model.editingLocked, "Save must release its lock")
        state.pauseWrite = false
        print("PASS explicit save destination, navigation lock, stale success")

        state.failWrite = true
        state.pauseWrite = true
        model.selection = .task(1)
        let failing = Task { await model.saveCues([], for: 1) }
        await waitFor { state.writeGate != nil }
        model.selection = .task(2)
        model.actionError = "B error"
        state.writeGate?.resume(); state.writeGate = nil
        expect(!(await failing.value), "Write failure must be reported")
        expect(model.actionError == "B error", "A failure must not appear on B")
        state.failWrite = false
        state.pauseWrite = false
        print("PASS stale save failure")

        let renameModel = await loaded()
        let previousCalls = state.calls.count
        let stamps = renameModel.cues.map(\.stamp)
        expect(await renameModel.renameSpeakers(["甲": "主持人"], for: 1), "Rename must succeed")
        expect(Array(state.calls.dropFirst(previousCalls)) == ["rename:1"], "Rename must use only the dedicated operation")
        expect(renameModel.cues.map(\.stamp) == stamps, "UI reload must retain backend cue timestamps")
        print("PASS dedicated rename operation")

        let draftModel = await loaded()
        draftModel.transcriptDraft = "Unsaved prose"
        NSAlert.response = .alertThirdButtonReturn
        var staged = false
        draftModel.select(.new) { staged = true }
        expect(draftModel.selection == .task(1) && !staged, "Cancel must cancel navigation and staging")
        expect(draftModel.transcriptDraft == "Unsaved prose", "Cancel must retain prose")
        expect(!(await resolve(draftModel)), "Quit guard must respect Cancel too")
        NSAlert.response = .alertSecondButtonReturn
        expect(await resolve(draftModel), "Discard must allow leaving")
        expect(!draftModel.hasUnsavedEdits, "Discard must reset prose")
        draftModel.cueDraft[0].text = "字幕修改"
        expect(draftModel.hasUnsavedEdits, "Subtitle edits must be tracked")
        NSAlert.response = .alertThirdButtonReturn
        expect(!(await resolve(draftModel)), "Subtitle Cancel must retain editor")
        expect(draftModel.cueDraft[0].text == "字幕修改", "Subtitle Cancel must retain content")
        NSAlert.response = .alertFirstButtonReturn
        state.failWrite = true
        expect(!(await resolve(draftModel)), "Failed save must prevent leaving")
        expect(draftModel.hasUnsavedEdits && draftModel.cueDraft[0].text == "字幕修改", "Failed save must retain draft")
        expect(!draftModel.editingLocked, "Failed save must release both locks")
        state.failWrite = false
        expect(await resolve(draftModel), "Successful subtitle save must allow leaving")
        expect(!draftModel.hasUnsavedEdits && state.calls.last == "cues:1", "Subtitle Save must persist the correct draft")
        draftModel.transcriptDraft = "Saved on navigation"
        draftModel.select(.new) { staged = true }
        await waitFor { staged }
        expect(draftModel.selection == .new && state.text[1] == "Saved on navigation", "Navigation must wait for prose save")
        print("PASS shared Save/Discard/Cancel guard for prose, subtitles, navigation and quit")

        let staleDetail = WorkspaceModel()
        staleDetail.selection = .task(1)
        state.pauseDetail = true
        let refreshing = Task { await staleDetail.refresh() }
        await waitFor { state.detailGate != nil }
        staleDetail.selection = .task(2)
        state.detailGate?.resume(); state.detailGate = nil
        await refreshing.value
        expect(staleDetail.detail == nil && staleDetail.outputsFor == nil, "Stale detail must not install A on B")
        state.pauseDetail = false
        print("PASS stale detail response")

        let staleRead = WorkspaceModel()
        staleRead.selection = .task(1)
        state.pauseFile = true
        let reading = Task { await staleRead.refresh() }
        await waitFor { state.fileGate != nil }
        staleRead.selection = .task(2)
        staleRead.actionError = "B error"
        state.failFile = true
        state.fileGate?.resume(); state.fileGate = nil
        await reading.value
        expect(staleRead.actionError == "B error", "A read failure must not replace B's error")
        state.pauseFile = false
        state.failFile = false
        print("PASS stale output read failure")

        let overlapping = WorkspaceModel()
        overlapping.selection = .task(1)
        state.pauseFile = true
        let slowRefresh = Task { await overlapping.refresh() }
        await waitFor { state.fileGate != nil }
        state.pauseFile = false
        await overlapping.refresh()
        overlapping.transcriptDraft = "Typed after the first load"
        state.fileGate?.resume(); state.fileGate = nil
        await slowRefresh.value
        expect(overlapping.transcriptDraft == "Typed after the first load" && overlapping.hasUnsavedEdits,
               "An overlapping initial output read cannot reset a live draft")
        print("PASS overlapping initial loads retain edits")

        draftModel.export(kind: "srt", name: "recording.wav")
        expect(NSSavePanel.last?.allowedContentTypes.first?.preferredFilenameExtension == "srt", "SRT export must permit SRT")
        expect(NSSavePanel.last?.allowsOtherFileTypes == false, "SRT export cannot offer unrelated formats")
        expect(NSSavePanel.last?.nameFieldStringValue == "recording.srt", "SRT export must keep its extension")
        draftModel.export(kind: "txt", name: "recording.wav")
        expect(NSSavePanel.last?.allowedContentTypes.first?.preferredFilenameExtension == "txt", "TXT export must permit TXT")
        expect(NSSavePanel.last?.nameFieldStringValue == "recording.txt", "TXT export must keep its extension")
        let lastPanel = NSSavePanel.last
        draftModel.export(kind: "pdf", name: "recording.wav")
        expect(NSSavePanel.last === lastPanel, "Unsupported export must not silently write TXT")
        // The runner executes in a temporary directory; only synthetic fixture output is written.
        let exportBase = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("fixture-export")
        NSSavePanel.destination = exportBase
        draftModel.export(kind: "srt", name: "recording.wav")
        let exportedSRT = try! String(contentsOf: exportBase.appendingPathExtension("srt"), encoding: .utf8)
        expect(exportedSRT == draftModel.srtRaw, "SRT export must write SRT content and preserve its extension")
        draftModel.export(kind: "txt", name: "recording.wav")
        let exportedTXT = try! String(contentsOf: exportBase.appendingPathExtension("txt"), encoding: .utf8)
        expect(exportedTXT == draftModel.txt, "TXT export must write prose and preserve its extension")
        print("PASS export kind, content and extension restrictions")
    }
}
