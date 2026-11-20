import AppKit
import SwiftUI

// MARK: - Catalog

struct ModelSpec: Identifiable, Hashable {
    let repo: String
    let title: String
    let role: String
    let bytes: Int64          // approximate, until the download reports the real size
    let required: Bool
    var id: String { repo }
}

let modelCatalog: [ModelSpec] = [
    .init(repo: "mlx-community/Qwen3-ASR-1.7B-8bit", title: "Qwen3-ASR 1.7B", role: "语音识别", bytes: 2_470_000_000, required: true),
    .init(repo: "mlx-community/Qwen3-ForcedAligner-0.6B-8bit", title: "Qwen3 ForcedAligner 0.6B", role: "字幕时间对齐", bytes: 1_272_000_000, required: true),
    .init(repo: "mlx-community/silero-vad-v6", title: "Silero VAD", role: "语音检测", bytes: 1_300_000, required: true),
    .init(repo: "mlx-community/diar_streaming_sortformer_4spk-v2.1-fp16", title: "Sortformer", role: "区分说话人（可选）", bytes: 236_000_000, required: false),
    .init(repo: "mlx-community/Qwen3-ASR-0.6B-8bit", title: "Qwen3-ASR 0.6B", role: "轻量识别，更快更省内存，准确率略低（可选）", bytes: 900_000_000, required: false),
]

enum DownloadSource: String, CaseIterable, Identifiable {
    case auto, official, mirror
    var id: String { rawValue }
    var title: String { self == .auto ? "自动选择" : self == .official ? "官方（Hugging Face）" : "镜像（hf-mirror.com）" }
    var endpoint: String { self == .mirror ? "https://hf-mirror.com" : "https://huggingface.co" }
}

enum ModelState: Equatable {
    case unknown
    case missing
    case ready
    case downloading
    case paused
    case failed(String)
}

private func format(_ bytes: Int64) -> String { ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file) }

// MARK: - Store

@MainActor
final class ModelStore: ObservableObject {
    static let shared = ModelStore()

    @Published private(set) var states: [String: ModelState] = [:]
    @Published private(set) var sizes: [String: Int64] = [:]       // real sizes once known
    @Published private(set) var downloaded: [String: Int64] = [:]
    @Published private(set) var speed: Double = 0                  // bytes per second
    @Published private(set) var freeBytes: Int64 = 0
    @Published private(set) var activeSource: DownloadSource?
    @Published private(set) var checked = false
    @Published private(set) var preparing = false          // choosing a download source
    @Published var presenting = false
    @Published var source: DownloadSource {
        didSet { UserDefaults.standard.set(source.rawValue, forKey: "downloadSource") }
    }

    private var queue: [String] = []
    private var current: Task<Void, Never>?
    private var wantPaused = false
    private var samples: [(Date, Int64)] = []
    private var stallSince: Date?
    private var ticker: Task<Void, Never>?
    private var switched = false

    init() {
        source = DownloadSource(rawValue: UserDefaults.standard.string(forKey: "downloadSource") ?? "") ?? .auto
    }

    // MARK: Queries

    func state(_ repo: String) -> ModelState { states[repo] ?? .unknown }
    func isReady(_ repo: String) -> Bool { state(repo) == .ready }
    var selectedRecognizer: String { UserDefaults.standard.string(forKey: "localModel") == "lite" ? LocalModel.asrLite : LocalModel.asr }
    var requiredModels: [ModelSpec] { modelCatalog.filter { [selectedRecognizer, LocalModel.aligner, LocalModel.vad].contains($0.repo) } }
    func offlineReady(for recognizer: String) -> Bool { [recognizer, LocalModel.aligner, LocalModel.vad].allSatisfy { isReady($0) } }
    var offlineReady: Bool { offlineReady(for: selectedRecognizer) }
    var isDownloading: Bool { current != nil || preparing }
    var anyProgress: Bool { states.values.contains(.downloading) || states.values.contains(.paused) }

    func size(_ spec: ModelSpec) -> Int64 { sizes[spec.repo] ?? spec.bytes }
    func missingBytes(of specs: [ModelSpec]) -> Int64 {
        specs.filter { !isReady($0.repo) }.reduce(0) { $0 + max(size($1) - (downloaded[$1.repo] ?? 0), 0) }
    }

    /// Overall progress of whatever is being downloaded.
    var batchTotal: Int64 { queueSpecs.reduce(0) { $0 + size($1) } }
    var batchDone: Int64 { queueSpecs.reduce(0) { $0 + min(downloaded[$1.repo] ?? 0, size($1)) } }
    private var queueSpecs: [ModelSpec] { modelCatalog.filter { states[$0.repo] == .downloading || states[$0.repo] == .paused } }
    var remainingText: String? {
        guard speed > 20_000 else { return nil }
        let seconds = Double(max(batchTotal - batchDone, 0)) / speed
        if seconds < 90 { return "约剩 \(Int(seconds.rounded())) 秒" }
        if seconds < 5400 { return "约剩 \(Int((seconds / 60).rounded())) 分钟" }
        return String(format: "约剩 %.1f 小时", seconds / 3600)
    }
    var speedText: String? { speed > 0 ? "\(format(Int64(speed)))/秒" : nil }
    var bytesText: String { "\(format(batchDone)) / \(format(batchTotal))" }

    // MARK: Status

    func refresh() async {
        linkSystemModels()
        freeBytes = ((try? AppPaths.layout.modelCache.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]))?.volumeAvailableCapacityForImportantUsage) ?? freeBytes
        for spec in modelCatalog {
            if HubDownloader.isReady(spec.repo) { states[spec.repo] = .ready; downloaded[spec.repo] = HubDownloader.partialBytes(spec.repo) }
            else if states[spec.repo] != .downloading && states[spec.repo] != .paused {
                // A download interrupted earlier (even by quitting the app) continues from where it stopped.
                let partial = HubDownloader.partialBytes(spec.repo)
                if partial > 0 { states[spec.repo] = .paused; downloaded[spec.repo] = partial } else { states[spec.repo] = .missing }
            }
        }
        checked = true
    }

    /// Models another tool already downloaded are linked in, not fetched again.
    private func linkSystemModels() {
        guard AppPaths.layout.reuseSystemModels else { return }
        let fm = FileManager.default
        for spec in modelCatalog {
            let theirs = AppPaths.systemModelCache.appendingPathComponent("mlx-audio/" + spec.repo.replacingOccurrences(of: "/", with: "_"))
            let mine = AppPaths.modelDirRaw(spec.repo)
            guard !fm.fileExists(atPath: mine.path), fm.fileExists(atPath: theirs.appendingPathComponent("model.safetensors").path) else { continue }
            try? fm.createDirectory(at: mine.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? fm.createSymbolicLink(at: mine, withDestinationURL: theirs)
        }
    }

    // MARK: Download

    func download(_ specs: [ModelSpec]) {
        guard current == nil else { return }
        let todo = specs.filter { !isReady($0.repo) }.map(\.repo)
        guard !todo.isEmpty else { return }
        queue = todo
        wantPaused = false
        switched = false
        for repo in todo { states[repo] = .downloading }
        Task { await next() }
    }

    func downloadRequired() { download(requiredModels) }

    func pause() {
        wantPaused = true
        preparing = false
        current?.cancel()
        for repo in queue { states[repo] = .paused }
        speed = 0
    }

    func resume() {
        guard current == nil else { return }
        let todo = modelCatalog.filter { states[$0.repo] == .paused || states[$0.repo] == .downloading }.map(\.repo)
        queue = todo
        wantPaused = false
        for repo in todo { states[repo] = .downloading }
        Task { await next() }
    }

    func retry() {
        let failed = modelCatalog.filter { if case .failed = states[$0.repo] { return true } else { return false } }
        download(failed)
    }

    private func chooseSource() async -> DownloadSource {
        if source != .auto { return source }
        async let official = HubDownloader.probe(endpoint: DownloadSource.official.endpoint)
        async let mirror = HubDownloader.probe(endpoint: DownloadSource.mirror.endpoint)
        let (o, m) = await (official, mirror)
        return (m ?? 0) > (o ?? 0) ? .mirror : .official
    }

    private func next() async {
        guard let repo = queue.first else { ticker?.cancel(); speed = 0; activeSource = nil; await refresh(); return }
        let chosen: DownloadSource
        if let existing = activeSource { chosen = existing } else { preparing = true; chosen = await chooseSource(); preparing = false }
        if wantPaused { return }
        activeSource = chosen
        samples = []
        stallSince = nil
        speed = 0
        ticker?.cancel()
        ticker = Task { [weak self] in
            while !Task.isCancelled { try? await Task.sleep(for: .seconds(3)); self?.tick() }
        }
        let endpoint = chosen.endpoint
        current = Task { [weak self] in
            do {
                try await HubDownloader.download(repo: repo, endpoint: endpoint) { done, total in
                    Task { @MainActor in self?.report(repo: repo, done: done, total: total) }
                }
                await self?.finish(repo: repo, ok: true, error: nil)
            } catch is CancellationError {
                await self?.finish(repo: repo, ok: false, error: nil)
            } catch {
                await self?.finish(repo: repo, ok: false, error: error.localizedDescription)
            }
        }
    }

    private func report(repo: String, done: Int64, total: Int64) {
        if total > 0 { sizes[repo] = total }
        downloaded[repo] = done
        let now = Date()
        samples.append((now, done))
        samples.removeAll { now.timeIntervalSince($0.0) > 8 }
        if let first = samples.first, now.timeIntervalSince(first.0) > 1 { speed = Double(done - first.1) / now.timeIntervalSince(first.0) }
    }

    /// Source on "auto" crawling (or silent) for a while: switch to the other one and carry on; partial files are kept.
    private func tick() {
        guard current != nil, source == .auto, !switched, let active = activeSource else { return }
        let now = Date()
        if speed < 40_000 {
            if stallSince == nil { stallSince = now }
            if let since = stallSince, now.timeIntervalSince(since) > 25 {
                switched = true
                activeSource = active == .official ? .mirror : .official
                restarting = true
                current?.cancel()      // finish() restarts with the other source
            }
        } else { stallSince = nil }
    }

    private var restarting = false

    private func finish(repo: String, ok: Bool, error: String?) async {
        current = nil
        if wantPaused { return }
        if restarting { restarting = false; await next(); return }
        if ok {
            states[repo] = .ready
            queue.removeAll { $0 == repo }
            await next()
        } else {
            states[repo] = .failed(Self.explain(error))
            for other in queue where other != repo { states[other] = .missing }
            queue.removeAll()
            ticker?.cancel()
            activeSource = nil
            speed = 0
            await refresh()
        }
    }

    static func explain(_ raw: String?) -> String {
        let text = (raw ?? "").lowercased()
        if text.contains("space") || text.contains("no space") { return "磁盘空间不够，清理后再继续。" }
        if text.isEmpty || text.contains("timed out") || text.contains("network") || text.contains("connect") || text.contains("offline") || text.contains("internet") {
            return "连不上下载源。检查网络，或在「来源」里换一个，已下载的部分会保留。"
        }
        return "下载没有完成：\(raw ?? "未知原因")"
    }
}

// MARK: - View

struct ModelsView: View {
    @ObservedObject var store: ModelStore = .shared
    var onClose: (() -> Void)?

    private var requiredMissing: Int64 { store.missingBytes(of: store.requiredModels) }
    private var notEnoughSpace: Bool { store.freeBytes > 0 && requiredMissing + 1_000_000_000 > store.freeBytes && !store.offlineReady && !store.isDownloading }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                Text(store.offlineReady ? "本地模型已就绪" : "下载本地模型").font(.title2.weight(.semibold))
                if !store.offlineReady {
                    Text("离线转写在这台 Mac 上完成，不联网。需要先下载 \(format(store.missingBytes(of: store.requiredModels))) 的模型，只需一次。")
                        .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }

            VStack(spacing: 0) {
                ForEach(Array(modelCatalog.enumerated()), id: \.element.id) { index, spec in
                    if index > 0 { Divider() }
                    ModelRow(store: store, spec: spec)
                }
            }
            .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Color(nsColor: .controlBackgroundColor)))

            if store.isDownloading || store.anyProgress || store.preparing {
                VStack(alignment: .leading, spacing: 8) {
                    ProgressView(value: Double(store.batchDone), total: Double(max(store.batchTotal, 1)))
                    HStack {
                        Text(store.preparing ? "正在选择下载来源…" : store.bytesText).monospacedDigit()
                        if let speed = store.speedText { Text("· \(speed)").monospacedDigit() }
                        if let eta = store.remainingText { Text("· \(eta)") }
                        Spacer()
                        if let active = store.activeSource, store.isDownloading { Text("来源：\(active == .mirror ? "镜像" : "官方")").foregroundStyle(.secondary) }
                    }
                    .font(.callout).foregroundStyle(.secondary)
                }
            }

            if notEnoughSpace {
                Text("磁盘剩余 \(format(store.freeBytes))，不够放下这些模型。清理一些空间后再下载。").font(.callout).foregroundStyle(.orange)
            }

            HStack(spacing: 12) {
                actionButton
                Menu {
                    Picker("下载来源", selection: $store.source) { ForEach(DownloadSource.allCases) { Text($0.title).tag($0) } }.pickerStyle(.inline)
                } label: { Text("来源：\(store.source == .auto ? "自动" : store.source == .mirror ? "镜像" : "官方")") }
                    .menuStyle(.borderlessButton).fixedSize().disabled(store.isDownloading)
                Spacer()
                if let onClose { Button(store.offlineReady ? "完成" : "稍后") { onClose() }.keyboardShortcut(.cancelAction) }
            }

            HStack(spacing: 6) {
                Text("存放位置：\(AppPaths.layout.modelCache.path.replacingOccurrences(of: AppPaths.home.path, with: "~"))")
                    .lineLimit(1).truncationMode(.middle)
                Button("在访达中显示") { NSWorkspace.shared.activateFileViewerSelecting([AppPaths.layout.modelCache]) }.buttonStyle(.link)
            }
            .font(.callout).foregroundStyle(.secondary)
        }
        .padding(24)
        .frame(width: 520)
        .task { await store.refresh() }
    }

    @ViewBuilder private var actionButton: some View {
        if store.preparing {
            Button("正在准备…") {}.controlSize(.large).disabled(true)
        } else if store.isDownloading {
            Button("暂停") { store.pause() }.controlSize(.large)
        } else if store.anyProgress {
            Button("继续下载") { store.resume() }.buttonStyle(.borderedProminent).controlSize(.large)
        } else if store.states.values.contains(where: { if case .failed = $0 { return true } else { return false } }) {
            Button("重试") { store.retry() }.buttonStyle(.borderedProminent).controlSize(.large)
        } else if !store.offlineReady {
            Button("开始下载") { store.downloadRequired() }.buttonStyle(.borderedProminent).controlSize(.large).disabled(notEnoughSpace)
        }
    }
}

private struct ModelRow: View {
    @ObservedObject var store: ModelStore
    let spec: ModelSpec

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon).foregroundStyle(color).frame(width: 20).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(spec.title)
                Text(spec.role).font(.callout).foregroundStyle(.secondary)
                if case .failed(let message) = store.state(spec.repo) {
                    Text(message).font(.callout).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
            trailing
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private var icon: String {
        switch store.state(spec.repo) {
        case .ready: return "checkmark.circle.fill"
        case .downloading: return "arrow.down.circle"
        case .paused: return "pause.circle"
        case .failed: return "exclamationmark.circle.fill"
        default: return "circle"
        }
    }
    private var color: Color {
        switch store.state(spec.repo) {
        case .ready: return .green
        case .failed: return .red
        case .downloading, .paused: return .accentColor
        default: return .secondary
        }
    }

    @ViewBuilder private var trailing: some View {
        switch store.state(spec.repo) {
        case .ready: Text(format(store.size(spec))).foregroundStyle(.secondary).monospacedDigit()
        case .downloading, .paused:
            Text("\(Int(min(Double(store.downloaded[spec.repo] ?? 0) / Double(max(store.size(spec), 1)), 1) * 100))%").foregroundStyle(.secondary).monospacedDigit()
        default:
            if spec.required { Text(format(store.size(spec))).foregroundStyle(.secondary).monospacedDigit() }
            else { Button("下载 \(format(store.size(spec)))") { store.download([spec]) }.disabled(store.isDownloading) }
        }
    }
}
