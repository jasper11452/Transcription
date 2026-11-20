import AppKit
import AVFoundation
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class WorkspaceModel: ObservableObject {
    enum Selection: Hashable { case new, task(Int) }

    @Published var tasks: [TTask] = []
    @Published var selection: Selection = .new
    @Published var selectedTaskIDs: Set<Int> = []
    @Published var detail: TDetail?
    @Published var search = "" { didSet { if oldValue.isEmpty, !search.isEmpty { loadBodies() } } }
    /// Transcript text per task, read when a search starts so the sidebar can match body text too.
    private var bodies: [Int: String] = [:]

    private func loadBodies() {
        let paths = tasks.compactMap { t in t.txtPath.map { (t.id, $0) } }
        Task.detached(priority: .userInitiated) {
            var out: [Int: String] = [:]
            for (id, path) in paths { out[id] = (try? String(contentsOfFile: path, encoding: .utf8))?.lowercased() }
            let loaded = out
            await MainActor.run { self.bodies = loaded; self.objectWillChange.send() }
        }
    }
    @Published var status: TStatus?
    enum Filter: CaseIterable { case all, active, failed, done
        var title: String { ["全部", "进行中", "失败", "完成"][Self.allCases.firstIndex(of: self)!] }
        func matches(_ t: TTask) -> Bool { self == .all || (self == .active && t.isActive) || (self == .failed && t.isFailed) || (self == .done && t.isDone) }
    }
    @Published var filter = Filter.all
    @Published var reachable = true

    // New task: every file the person dropped, each with what we learned about it
    struct StagedFile: Identifiable, Equatable {
        let url: URL
        var duration: Double?
        var cost: Double?
        var problem: String?          // set when the file has no readable audio
        var id: URL { url }
        var checked: Bool { duration != nil || problem != nil }
    }
    @Published var files: [StagedFile] = []
    @Published var speakers = false
    @Published var newError: String?
    @Published var batchMessage: String?
    @Published var submitting = false
    @Published var showImporter = false
    @Published var mode = "offline"          // online is always an explicit choice, so it is never remembered
    @Published var language: String { didSet { UserDefaults.standard.set(language, forKey: "wsLanguage") } }
    @Published var engine: String { didSet { UserDefaults.standard.set(engine, forKey: "wsEngine") } }
    @Published private(set) var hotWordGroups: [String] = []
    @Published var selectedHotWordGroups: Set<String> = [] {
        didSet { UserDefaults.standard.set(Array(selectedHotWordGroups), forKey: "selectedHotWordGroups") }
    }

    // Finished task
    @Published var txt = ""
    @Published var srtRaw = ""
    @Published var cues: [Cue] = []
    @Published private(set) var outputsFor: Int?
    @Published var actionError: String?
    @Published var transcriptDraft = ""
    @Published var cueDraft: [Cue] = []
    @Published private(set) var isSaving = false
    @Published private(set) var resolvingEdits = false
    @Published var chatConversation = TranscriptChatConversation()
    @Published var chatError: String?

    var editingLocked: Bool { isSaving || resolvingEdits }
    var hasUnsavedEdits: Bool {
        outputsFor != nil && (transcriptDraft != txt || cueDraft != cues)
    }

    func discardEdits() {
        guard !isSaving else { return }
        transcriptDraft = txt
        cueDraft = cues
    }

    /// Navigation and Quit share one decision, including waiting for a successful save.
    func resolveEdits(_ completion: @escaping (Bool) -> Void) {
        guard !editingLocked else { completion(false); return }
        guard hasUnsavedEdits else { completion(true); return }
        resolvingEdits = true
        let alert = NSAlert()
        alert.messageText = "要保存对这条记录的修改吗？"
        alert.informativeText = "不保存的修改会丢失。"
        alert.addButton(withTitle: "保存")
        alert.addButton(withTitle: "不保存")
        alert.addButton(withTitle: "取消").keyEquivalent = "\u{1b}"
        let response = alert.runModal()
        switch response {
        case .alertFirstButtonReturn:
            Task {
                let saved = await saveEdits()
                resolvingEdits = false
                completion(saved)
            }
        case .alertSecondButtonReturn:
            discardEdits()
            resolvingEdits = false
            completion(true)
        default:
            resolvingEdits = false
            completion(false)
        }
    }

    @discardableResult
    private func saveEdits() async -> Bool {
        guard let id = outputsFor else { return false }
        if transcriptDraft != txt { return await saveTranscript(transcriptDraft, for: id) }
        if cueDraft != cues { return await saveCues(cueDraft, for: id) }
        return true
    }

    let client = TranscriptClient()

    init() {
        language = UserDefaults.standard.string(forKey: "wsLanguage") ?? ""
        engine = UserDefaults.standard.string(forKey: "wsEngine") ?? "auto"
        loadHotWordGroups()
    }

    func loadHotWordGroups() {
        let glossary = Glossary(file: AppPaths.layout.glossary)
        let names = glossary.groups.map(\.name)
        hotWordGroups = names
        let saved = UserDefaults.standard.array(forKey: "selectedHotWordGroups") as? [String]
        selectedHotWordGroups = saved.map { Set($0).intersection(names) } ?? Set(names)
    }

    func setHotWordGroups(_ groups: Set<String>) {
        selectedHotWordGroups = groups.intersection(hotWordGroups)
    }

    private var currentHotwords: [String] {
        Glossary(file: AppPaths.layout.glossary).hotwords(in: selectedHotWordGroups)
    }

    // MARK: Polling

    func run() async {
        while !Task.isCancelled {
            await refresh()
            let busy = tasks.contains { $0.isActive }
            try? await Task.sleep(for: .seconds(busy ? 1 : 3))
        }
    }

    func refresh() async {
        do {
            tasks = try await client.tasks()
            selectedTaskIDs.formIntersection(Set(tasks.map(\.id)))
            if !search.isEmpty, Set(tasks.filter { $0.txtPath != nil }.map(\.id)) != Set(bodies.keys) { loadBodies() }
            reachable = true
            NSApp.dockTile.badgeLabel = tasks.first(where: \.running).map { "\(Int($0.percent))%" }
            if status == nil { status = try? await client.status() }
            if case .task(let id) = selection {
                let current = try await client.detail(id)
                guard selection == .task(id) else { return }
                detail = current
                if current.task.isDone, outputsFor != id { await loadOutputs(id) }
            } else {
                detail = nil
            }
        } catch {
            reachable = false
        }
    }

    func select(_ value: Selection, afterSelection: @escaping () -> Void = {}) {
        if value == selection {
            guard !editingLocked else { return }
            afterSelection()
            return
        }
        resolveEdits { [self] proceed in
            guard proceed else { return }
            selection = value
            if case .task(let id) = value { selectedTaskIDs = [id] } else { selectedTaskIDs = [] }
            detail = nil
            outputsFor = nil
            actionError = nil
            afterSelection()
            Task { await refresh() }
        }
    }

    func setTaskSelection(_ values: Set<Selection>) {
        let ids = Set(values.compactMap { if case .task(let id) = $0 { return id }; return nil })
        selectedTaskIDs = ids
        if ids.count == 1, let id = ids.first {
            select(.task(id))
        } else if ids.count > 1 {
            selection = .new
            detail = nil
            outputsFor = nil
        } else {
            select(.new)
        }
    }

    @discardableResult
    private func loadOutputs(_ id: Int, replacingDraft: Bool = false) async -> Bool {
        do {
            let text = try await client.file(id, kind: "txt")
            let srt = try await client.file(id, kind: "srt")
            guard selection == .task(id) else { return false }
            // Another initial refresh may have finished while these reads were suspended.
            guard outputsFor != id || replacingDraft else { return true }
            txt = text
            srtRaw = srt
            cues = parseSRT(srt)
            transcriptDraft = text
            cueDraft = cues
            bodies[id] = text.lowercased()
            outputsFor = id
            actionError = nil
            return true
        } catch {
            guard selection == .task(id) else { return false }
            actionError = "读取结果失败：\(error.localizedDescription)"
            return false
        }
    }

    // MARK: Grouping for the sidebar

    var groups: [(title: String, tasks: [TTask])] {
        let needle = search.trimmingCharacters(in: .whitespaces).lowercased()
        let visible = (needle.isEmpty ? tasks : tasks.filter {
            $0.displayTitle.lowercased().contains(needle) || $0.name.lowercased().contains(needle) || bodies[$0.id]?.contains(needle) == true
        }).filter(filter.matches)
        let calendar = Calendar.current
        var buckets: [String: [TTask]] = [:]
        for task in visible {
            let key: String
            if let date = task.date {
                if calendar.isDateInToday(date) { key = "今天" }
                else if calendar.isDateInYesterday(date) { key = "昨天" }
                else if calendar.dateComponents([.day], from: date, to: .now).day ?? 99 < 7 { key = "本周" }
                else { key = "更早" }
            } else { key = "更早" }
            buckets[key, default: []].append(task)
        }
        return ["今天", "昨天", "本周", "更早"].compactMap { key in buckets[key].map { (key, $0) } }
    }

    // MARK: New task

    var readyFiles: [StagedFile] { files.filter { $0.duration != nil } }
    var totalDuration: Double { readyFiles.compactMap(\.duration).reduce(0, +) }
    var totalCost: Double? { mode == "online" ? readyFiles.compactMap(\.cost).reduce(0, +) : nil }

    /// Adds files to the queue (dropping the same file twice is a no-op) and checks each one.
    func stage(_ urls: [URL]) {
        let known = Set(files.map(\.url))
        let fresh = urls.filter { !known.contains($0) }
        files += fresh.map { StagedFile(url: $0) }
        newError = nil
        Task { await updateInfo() }
    }

    func unstage(_ url: URL? = nil) {
        if let url { files.removeAll { $0.url == url } } else { files = [] }
        newError = nil
    }

    /// Reads duration (and cloud cost) per file; re-run when the engine changes.
    func updateInfo() async {
        for file in files {
            let url = file.url
            guard let result = try? await client.estimate(path: url.path, mode: mode, engine: engine),
                  let index = files.firstIndex(where: { $0.url == url }) else { continue }
            if result.ok, let duration = result.durationS {
                files[index].duration = duration
                files[index].cost = result.estimatedCostUsd
                files[index].problem = nil
            } else {
                files[index].duration = nil
                files[index].problem = WorkspaceModel.friendly(result.error)
            }
        }
    }

    func submit() async {
        let queue = readyFiles.map(\.url)
        guard !queue.isEmpty, !submitting else { return }
        let hotwordsSnapshot = currentHotwords
        submitting = true
        newError = nil
        defer { submitting = false }
        var firstID: Int?
        var failed: [URL] = []
        for url in queue {
            do {
                let id = try await client.create(path: url.path, mode: mode, language: language, engine: engine,
                                                 speakers: speakers && mode == "offline", hotwords: hotwordsSnapshot)
                if firstID == nil { firstID = id }
                files.removeAll { $0.url == url }
            } catch {
                failed.append(url)
                if newError == nil { newError = WorkspaceModel.friendly(error.localizedDescription) }
            }
        }
        if !failed.isEmpty, firstID != nil { newError = "有 \(failed.count) 个文件没能加入队列，还留在这里，稍后再点开始。" }
        await refresh()
        if let firstID, failed.isEmpty { select(.task(firstID)) }
    }

    /// Backend errors name paths and ffmpeg internals; say what happened and what to do.
    static func friendly(_ raw: String?) -> String {
        let text = raw ?? ""
        if text.contains("Invalid data") || text.contains("探测") || text.isEmpty {
            return "这个文件读不出声音，可能已损坏，或不是音频、视频文件。换一个文件试试。"
        }
        return text
    }

    // MARK: Task actions

    func cancel(_ id: Int) async { await perform { try await self.client.cancel(id) } }
    func resume(_ id: Int) async { await perform { try await self.client.resume(id) } }

    func delete(_ id: Int) async {
        if selection == .task(id) {
            let proceed = await withCheckedContinuation { continuation in
                resolveEdits { continuation.resume(returning: $0) }
            }
            guard proceed else { return }
        }
        await perform { try await self.client.delete(id) }
        if selection == .task(id) { select(.new) }
    }

    func deleteSelected() async {
        let ids = Array(selectedTaskIDs)
        guard !ids.isEmpty else { return }
        let result = await client.deleteInactive(ids)
        selectedTaskIDs.subtract(result.deleted)
        batchMessage = result.skipped.isEmpty
            ? "已删除 \(result.deleted.count) 个项目。"
            : "已删除 \(result.deleted.count) 个项目，跳过 \(result.skipped.count) 个正在转录的项目。"
        if case .task(let id) = selection, result.deleted.contains(id) { selection = .new; detail = nil; outputsFor = nil }
        await refresh()
    }

    func exportSelected(kind: String) {
        guard ["txt", "srt"].contains(kind), !selectedTaskIDs.isEmpty else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "导出到这里"
        panel.begin { [weak self] result in
            guard result == .OK, let folder = panel.url, let self else { return }
            Task { await self.writeBatchExports(kind: kind, folder: folder) }
        }
    }

    private func writeBatchExports(kind: String, folder: URL) async {
        let selected = tasks.filter { selectedTaskIDs.contains($0.id) }
        var exported = 0
        var skipped: [(String, String)] = []
        for task in selected {
            guard task.isDone else { skipped.append((task.displayTitle, "尚未完成")); continue }
            do {
                let content = try await client.file(task.id, kind: kind)
                let base = (task.displayTitle as NSString).deletingPathExtension
                var destination = folder.appendingPathComponent(base).appendingPathExtension(kind)
                var suffix = 2
                while FileManager.default.fileExists(atPath: destination.path) {
                    destination = folder.appendingPathComponent("\(base) (\(suffix))").appendingPathExtension(kind)
                    suffix += 1
                }
                try content.write(to: destination, atomically: true, encoding: .utf8)
                exported += 1
            } catch { skipped.append((task.displayTitle, error.localizedDescription)) }
        }
        batchMessage = skipped.isEmpty
            ? "已导出 \(exported) 个项目。"
            : "已导出 \(exported) 个项目，跳过或失败 \(skipped.count) 个：" + skipped.map { "\($0.0)（\($0.1)）" }.joined(separator: "、")
    }

    private func perform(_ action: () async throws -> Void) async {
        do { try await action(); actionError = nil } catch { actionError = error.localizedDescription }
        await refresh()
    }

    @discardableResult
    func saveTranscript(_ text: String, for id: Int) async -> Bool {
        await saveOutputs(for: id) { try await self.client.saveTranscript(id, text: text) }
    }

    @discardableResult
    func saveCues(_ edited: [Cue], for id: Int) async -> Bool {
        await saveOutputs(for: id) { try await self.client.saveCues(id, srt: serializeSRT(edited)) }
    }

    @discardableResult
    func renameSpeakers(_ replacements: [String: String], for id: Int) async -> Bool {
        await saveOutputs(for: id) { try await self.client.renameSpeakers(id, replacements: replacements) }
    }

    private func saveOutputs(for id: Int, _ save: () async throws -> Void) async -> Bool {
        guard !isSaving else { return false }
        isSaving = true
        defer { isSaving = false }
        do {
            try await save()
            guard selection == .task(id) else { return true }
            return await loadOutputs(id, replacingDraft: true)
        } catch {
            if selection == .task(id) { actionError = "保存失败：\(error.localizedDescription)" }
            return false
        }
    }

    // MARK: Export

    func export(kind: String, name: String) {
        guard ["txt", "srt"].contains(kind), let type = UTType(filenameExtension: kind) else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [type]
        panel.allowsOtherFileTypes = false
        panel.isExtensionHidden = false
        let base = (name as NSString).deletingPathExtension
        panel.nameFieldStringValue = base + "." + kind
        let content: String
        switch kind {
        case "srt": content = srtRaw
        default: content = txt
        }
        panel.begin { result in
            guard result == .OK, let url = panel.url else { return }
            let destination = url.pathExtension.lowercased() == kind ? url : url.appendingPathExtension(kind)
            try? content.write(to: destination, atomically: true, encoding: .utf8)
        }
    }

    func summarize(_ id: Int, prompt: String? = nil) async -> TSummary? {
        if selection == .task(id) { actionError = nil }
        do { return try await client.enableSummary(id, prompt: prompt) }
        catch {
            if selection == .task(id) { actionError = "生成总结失败：\(error.localizedDescription)" }
            return nil
        }
    }
    func loadSummary(_ id: Int) async -> TSummary? { try? await client.summary(id) }

    func loadChat(_ id: Int) async {
        chatConversation = await client.chat(id)
    }

    func sendChat(_ question: String, for id: Int) async {
        chatError = nil
        do { chatConversation = try await client.sendChat(id, question: question) }
        catch { chatError = error.localizedDescription }
    }

    func retryChat(_ turnID: UUID, for id: Int) async {
        chatError = nil
        do { chatConversation = try await client.retryChat(id, turnID: turnID) }
        catch { chatError = error.localizedDescription }
    }

    func stopChat(for id: Int) async {
        await client.stopChat(id)
        chatConversation = await client.chat(id)
    }

    func clearChat(for id: Int) async {
        await client.clearChat(id)
        chatConversation = TranscriptChatConversation()
    }

    func reveal(_ task: TTask) {
        let paths = [task.txtPath, task.srtPath, task.sourcePath].compactMap { $0 }.filter { FileManager.default.fileExists(atPath: $0) }
        if let first = paths.first { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: first)]) }
    }

    func audioURL(for task: TTask) -> URL {
        if let path = task.sourcePath, task.srcExists == true { return URL(fileURLWithPath: path) }
        return client.audioURL(task.id)
    }
}

// MARK: - Audio

@MainActor
final class PlayerModel: ObservableObject {
    @Published var playing = false
    @Published var time = 0.0
    @Published var duration = 0.0
    @Published var rate: Float = 1 { didSet { if playing { player?.rate = rate } } }
    private var player: AVPlayer?
    private var observer: Any?
    private var loaded: URL?

    func load(_ url: URL) {
        guard loaded != url else { return }
        unload()
        loaded = url
        let item = AVPlayerItem(url: url)
        let player = AVPlayer(playerItem: item)
        self.player = player
        observer = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 0.25, preferredTimescale: 600), queue: .main) { [weak self] value in
            Task { @MainActor in self?.time = value.seconds }
        }
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.playing = false }
        }
        Task { duration = (try? await item.asset.load(.duration).seconds) ?? 0 }
    }

    func unload() {
        if let observer { player?.removeTimeObserver(observer) }
        player?.pause()
        player = nil; observer = nil; loaded = nil
        playing = false; time = 0; duration = 0
    }

    func toggle() {
        guard let player else { return }
        if playing { player.pause() } else { player.playImmediately(atRate: rate) }
        playing.toggle()
    }

    func seek(_ seconds: Double, play: Bool = false) {
        player?.seek(to: CMTime(seconds: seconds, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        time = seconds
        if play, !playing { player?.playImmediately(atRate: rate); playing = true }
    }

    func skip(_ delta: Double) { seek(min(max(0, time + delta), max(duration, 0))) }
}
