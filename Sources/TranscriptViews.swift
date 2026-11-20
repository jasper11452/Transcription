import AppKit
import SwiftUI
import UniformTypeIdentifiers

private func loadURLs(_ providers: [NSItemProvider], done: @escaping ([URL]) -> Void) {
    var urls: [URL] = []
    let group = DispatchGroup()
    for provider in providers {
        group.enter()
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            if let url { DispatchQueue.main.async { urls.append(url) } }
            group.leave()
        }
    }
    group.notify(queue: .main) { done(urls) }
}

// MARK: - Look

enum Brand {
    /// A restrained indigo, lighter in the dark so it keeps its contrast.
    /// Text on top of the accent: dark on the light dark-mode indigo, white on the deep light-mode one.
    static let onAccent = Color(nsColor: NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(red: 0.07, green: 0.08, blue: 0.16, alpha: 1) : .white
    })
    static let accent = Color(nsColor: NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(red: 0.55, green: 0.60, blue: 1.0, alpha: 1) : NSColor(red: 0.33, green: 0.39, blue: 0.82, alpha: 1)
    })
}

/// A row of bars that moves only while there is something to show: a quiet page costs no CPU.
struct WaveformMark: View {
    var energy: Double
    var color: Color = Brand.accent
    private let shape: [Double] = [0.35, 0.55, 0.8, 0.6, 1.0, 0.7, 0.85, 0.5, 0.3]

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: energy == 0)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 5) {
                ForEach(0..<shape.count, id: \.self) { i in
                    let wave = energy == 0 ? 0 : sin(t * 2.6 + Double(i) * 0.75)
                    let level = shape[i] * (0.3 + 0.7 * max(energy, 0.25)) * (0.78 + 0.22 * wave)
                    Capsule().fill(color.opacity(energy == 0 ? 0.55 : 1)).frame(width: 4, height: 8 + 40 * level)
                }
            }
            .frame(height: 56)
        }
        .accessibilityHidden(true)
    }
}

/// A compact menu that reads as one glass control: icon, current value, chevron.
struct PillMenu<Content: View>: View {
    let symbol: String
    let title: String
    @ViewBuilder var content: Content
    var body: some View {
        Menu { content } label: {
            Label(title, systemImage: symbol)
        }
        .menuStyle(.button).glassButton().controlSize(.large).fixedSize()
    }
}

// MARK: - Shell

struct WorkspaceView: View {
    @ObservedObject var model: WorkspaceModel

    var body: some View {
        NavigationSplitView {
            Sidebar(model: model)
                .navigationSplitViewColumnWidth(min: 220, ideal: 260, max: 340)
        } detail: {
            Group {
                switch model.selection {
                case .new:
                    if model.selectedTaskIDs.count > 1 { BatchTaskView(model: model) } else { NewTaskView(model: model) }
                case .task(let id): TaskView(model: model, id: id)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task { await model.run() }
        .onDrop(of: [.fileURL], isTargeted: nil) { providers in
            loadURLs(providers) { urls in model.select(.new) { model.stage(urls) } }
            return true
        }
    }
}

private struct BatchTaskView: View {
    @ObservedObject var model: WorkspaceModel
    @State private var confirmingDelete = false

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "checklist").font(.system(size: 38)).foregroundStyle(Brand.accent)
            Text("已选择 \(model.selectedTaskIDs.count) 个转录项目").font(.title2.weight(.semibold))
            HStack(spacing: 10) {
                Menu("导出…") {
                    Button("TXT 文稿…") { model.exportSelected(kind: "txt") }
                    Button("SRT 字幕…") { model.exportSelected(kind: "srt") }
                }
                .glassButton()
                Button("删除选中项目…", role: .destructive) { confirmingDelete = true }.glassButton()
            }
            if let message = model.batchMessage { Text(message).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 520) }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .confirmationDialog("删除选中的项目？", isPresented: $confirmingDelete) {
            Button("删除可删除项目", role: .destructive) { Task { await model.deleteSelected() } }
            Button("取消", role: .cancel) {}
        }
    }
}

struct Sidebar: View {
    @ObservedObject var model: WorkspaceModel
    @State private var deleting: TTask?
    @State private var confirmingBatchDelete = false

    private var selection: Binding<Set<WorkspaceModel.Selection>> {
        Binding(get: { Set(model.selectedTaskIDs.map { WorkspaceModel.Selection.task($0) }) },
                set: { model.setTaskSelection($0) })
    }

    var body: some View {
        List(selection: selection) {
            ForEach(model.groups, id: \.title) { group in
                Section(group.title) {
                    ForEach(group.tasks) { task in
                        TaskRow(task: task)
                            .tag(WorkspaceModel.Selection.task(task.id))
                            .contextMenu {
                                Button("在访达中显示", systemImage: "folder") { model.reveal(task) }
                                Divider()
                                Button("删除…", systemImage: "trash", role: .destructive) { deleting = task }.disabled(task.isActive)
                            }
                            .swipeActions(edge: .trailing) {
                                Button("删除", systemImage: "trash", role: .destructive) { deleting = task }.disabled(task.isActive)
                            }
                    }
                }
            }
        }
        .overlay {
            if model.tasks.isEmpty && model.search.isEmpty {
                Text("转写记录会出现在这里").font(.callout).foregroundStyle(.tertiary)
            } else if model.groups.isEmpty {
                Text(model.search.isEmpty ? "没有这类记录" : "没有找到“\(model.search)”").font(.callout).foregroundStyle(.secondary)
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) { StatusFilter(model: model) }
        .searchable(text: $model.search, placement: .sidebar, prompt: "搜索")
        .toolbar {
            // Reads sidebar toggle → settings → new, left to right.
            ToolbarItemGroup(placement: .primaryAction) {
                if model.selectedTaskIDs.count > 1 {
                    Menu {
                        Button("导出 TXT…") { model.exportSelected(kind: "txt") }
                        Button("导出 SRT…") { model.exportSelected(kind: "srt") }
                        Divider()
                        Button("删除选中项目…", role: .destructive) { confirmingBatchDelete = true }
                    } label: {
                        Label("已选 \(model.selectedTaskIDs.count)", systemImage: "checklist")
                    }
                    .help("批量操作")
                }
                SettingsLink { Image(systemName: "gearshape") }
                    .help("设置（⌘,）").accessibilityLabel("设置")
                Button { model.select(.new) } label: { Image(systemName: "square.and.pencil") }
                    .help("新建转写（⌘N）").accessibilityLabel("新建转写")
            }
        }
        .confirmationDialog("删除这条记录？", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), presenting: deleting) { task in
            Button("删除记录", role: .destructive) { Task { await model.delete(task.id) } }
        } message: { _ in
            Text("只删除历史，录音和已生成的文件不会动。")
        }
        .confirmationDialog("删除选中的项目？", isPresented: $confirmingBatchDelete) {
            Button("删除可删除项目", role: .destructive) { Task { await model.deleteSelected() } }
            Button("取消", role: .cancel) {}
        } message: {
            let active = model.tasks.filter { model.selectedTaskIDs.contains($0.id) && $0.isActive }.count
            Text(active == 0 ? "将删除 \(model.selectedTaskIDs.count) 个项目。" : "将删除可删除项目，跳过 \(active) 个正在转录的项目。")
        }
        .alert("批量操作完成", isPresented: Binding(get: { model.batchMessage != nil }, set: { if !$0 { model.batchMessage = nil } })) {
            Button("好") { model.batchMessage = nil }
        } message: {
            Text(model.batchMessage ?? "")
        }
    }
}

struct TaskRow: View {
    let task: TTask

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(task.displayTitle).lineLimit(1).truncationMode(.middle)
                Group {
                    if task.isFailed { Text("没有完成").foregroundStyle(.red) }
                    else if task.isActive { Text(task.running ? "\(task.stage ?? "转写中") · \(Int(task.percent))%" : "排队中").foregroundStyle(.secondary) }
                    else {
                        Text([task.date?.formatted(date: .omitted, time: .shortened), task.durationS.map(clock)].compactMap { $0 }.joined(separator: " · "))
                            .foregroundStyle(.secondary)
                    }
                }
                .font(.caption).monospacedDigit().lineLimit(1)
            }
            Spacer(minLength: 0)
            if task.running {
                ProgressView(value: max(task.percent, 2), total: 100).progressViewStyle(.circular).controlSize(.small)
            } else if task.isActive {
                Image(systemName: "clock").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - New task

let workspaceLanguages: [(String, String)] = [("", "自动识别"), ("zh", "中文"), ("en", "English"), ("ja", "日本語"), ("ko", "한국어")]

struct NewTaskView: View {
    @ObservedObject var model: WorkspaceModel
    @ObservedObject private var models = ModelStore.shared
    @StateObject private var recorder = RecordingModel()
    @AppStorage("engineChoice") private var choice = "local"
    @State private var targeted = false

    var body: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 0)
            Group {
                if recorder.isActive { recordingPanel }
                else if model.files.isEmpty { dropZone }
                else { fileList }
            }
                .frame(height: 300)
                .animation(.smooth(duration: 0.3), value: model.files.isEmpty)
            composer
            // One fixed-height slot: hints, errors and download state change its text, never the layout.
            VStack(spacing: 8) {
                if let error = model.newError ?? recorder.error {
                    Label(error, systemImage: "exclamationmark.triangle.fill").font(.callout).foregroundStyle(.red)
                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
                downloadBanner
                if model.mode == "online", model.newError == nil {
                    Label("音频会上传到\(Service.cloud(model.engine).name)进行识别", systemImage: "icloud.and.arrow.up").font(.callout).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.horizontal, 6)
            .frame(maxWidth: .infinity, minHeight: 64, alignment: .top)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: 640)
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .navigationTitle("新建转写")
        .onAppear { apply(choice); model.language = UserDefaults.standard.string(forKey: "wsLanguage") ?? model.language; model.loadHotWordGroups() }
        .onDisappear { if recorder.isActive { recorder.discard() } }
        .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
            loadURLs(providers) { model.stage($0) }
            return true
        }
        .fileImporter(isPresented: $model.showImporter, allowedContentTypes: [.audio, .movie], allowsMultipleSelection: true) { result in
            if case .success(let urls) = result { model.stage(urls) }
        }
    }

    // MARK: Files

    private var dropZone: some View {
        VStack(spacing: 20) {
            WaveformMark(energy: targeted ? 1 : 0, color: targeted ? Brand.accent : .secondary)
            VStack(spacing: 12) {
                Text(targeted ? "松开即可添加" : "拖入录音或视频").font(.title2.weight(.semibold))
                HStack(spacing: 10) {
                    Button("开始录音", systemImage: "mic.fill") { recorder.start() }
                        .glassButton(prominent: true).controlSize(.large)
                    Button("选择文件…") { model.showImporter = true }
                        .glassButton().controlSize(.large)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(RoundedRectangle(cornerRadius: 28, style: .continuous).fill(Color.primary.opacity(targeted ? 0.06 : 0.03)))
        .overlay(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .strokeBorder(targeted ? Brand.accent : Color.primary.opacity(0.10), style: StrokeStyle(lineWidth: targeted ? 2 : 1, dash: targeted ? [] : [6, 5]))
        )
        .scaleEffect(targeted ? 1.015 : 1)
        .animation(.spring(response: 0.3, dampingFraction: 0.75), value: targeted)
    }

    private var recordingPanel: some View {
        VStack(spacing: 16) {
            WaveformMark(energy: recorder.isPreparing || recorder.isPaused ? 0 : max(recorder.level, 0.18), color: .red)
            VStack(spacing: 6) {
                Text(recorder.isPreparing ? "准备麦克风…" : recorder.isPaused ? "录音已暂停" : "正在录音")
                    .font(.title2.weight(.semibold))
                Text(clock(recorder.elapsed)).font(.system(.title3, design: .monospaced)).foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                Button(recorder.isPaused ? "继续" : "暂停", systemImage: recorder.isPaused ? "play.fill" : "pause.fill") {
                    recorder.togglePause()
                }
                .glassButton().controlSize(.large)
                .disabled(recorder.isPreparing)
                Button("停止并加入", systemImage: "stop.fill") {
                    if let url = recorder.stop() { model.stage([url]) }
                }
                .glassButton(prominent: true).controlSize(.large)
                .disabled(recorder.isPreparing)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(RoundedRectangle(cornerRadius: 28, style: .continuous).fill(Color.red.opacity(0.045)))
        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous).strokeBorder(Color.red.opacity(0.22), lineWidth: 1))
    }

    private var fileList: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(spacing: 2) {
                    ForEach(model.files) { file in fileRow(file) }
                }
                .padding(8)
            }
            .scrollBounceBehavior(.basedOnSize)
            Divider().opacity(0.6)
            HStack {
                Button { model.showImporter = true } label: { Label("添加文件", systemImage: "plus") }
                    .buttonStyle(.borderless)
                Spacer()
                Text(summaryLine).font(.callout).monospacedDigit().foregroundStyle(.secondary)
            }
            .padding(.horizontal, 16).padding(.vertical, 11)
        }
        .background(RoundedRectangle(cornerRadius: 28, style: .continuous).fill(Color.primary.opacity(targeted ? 0.06 : 0.03)))
        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous).strokeBorder(targeted ? Brand.accent : Color.primary.opacity(0.08), lineWidth: targeted ? 2 : 1))
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .animation(.spring(response: 0.3, dampingFraction: 0.75), value: targeted)
    }

    private func fileRow(_ file: WorkspaceModel.StagedFile) -> some View {
        let isVideo = UTType(filenameExtension: file.url.pathExtension)?.conforms(to: .movie) == true
        return HStack(spacing: 12) {
            Image(systemName: isVideo ? "film" : "waveform")
                .font(.system(size: 15, weight: .medium)).foregroundStyle(file.problem == nil ? Brand.accent : .secondary)
                .frame(width: 34, height: 34)
                .background(Circle().fill((file.problem == nil ? Brand.accent : Color.secondary).opacity(0.12)))
            VStack(alignment: .leading, spacing: 2) {
                Text(file.url.lastPathComponent).lineLimit(1).truncationMode(.middle)
                Group {
                    if let problem = file.problem { Text(problem).foregroundStyle(.red).lineLimit(2) }
                    else if let d = file.duration { Text(clock(d) + costText(file.cost)) .foregroundStyle(.secondary) }
                    else { Text("正在读取…").foregroundStyle(.tertiary) }
                }
                .font(.caption).monospacedDigit()
            }
            Spacer(minLength: 8)
            Button { withAnimation(.smooth) { model.unstage(file.url) } } label: {
                Image(systemName: "xmark.circle.fill").font(.system(size: 15)).foregroundStyle(.tertiary)
            }
            .buttonStyle(.plain).help("移出队列").accessibilityLabel("移除 \(file.url.lastPathComponent)")
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .contentShape(Rectangle())
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private func costText(_ cost: Double?) -> String {
        guard model.mode == "online", let cost else { return "" }
        return cost > 0 ? String(format: " · 约 $%.2f", cost) : " · 免费"
    }

    private var summaryLine: String {
        let ready = model.readyFiles.count
        guard ready > 0 else { return model.files.contains { !$0.checked } ? "正在读取…" : "" }
        var text = "\(ready) 个文件 · 共 \(clock(model.totalDuration))"
        if let cost = model.totalCost { text += cost > 0 ? String(format: " · 约 $%.2f", cost) : " · 免费" }
        return text
    }

    // MARK: Composer: every choice that shapes the run, on one glass bar

    private var composer: some View {
        HStack(spacing: 8) {
            PillMenu(symbol: model.mode == "offline" ? "desktopcomputer" : "cloud", title: model.mode == "offline" ? "本机 · 离线" : "云端 · " + Service.cloud(model.engine).name) {
                Picker("引擎", selection: engineBinding) {
                    Label("本机 · 离线", systemImage: "desktopcomputer").tag("local")
                    ForEach(Service.cloud) { s in
                        Label("云端 · \(s.name)" + (s.readyForTranscription ? "" : "（未配置）"), systemImage: "cloud").tag(s.id)
                    }
                }.pickerStyle(.inline)
            }
            PillMenu(symbol: "globe", title: workspaceLanguages.first { $0.0 == model.language }?.1 ?? "自动识别") {
                Picker("语言", selection: $model.language) {
                    ForEach(workspaceLanguages, id: \.0) { Text($0.1).tag($0.0) }
                }.pickerStyle(.inline)
            }
            hotWordMenu
            if model.mode == "offline" { speakerToggle }
            Spacer(minLength: 12)
            startButton
        }
        .glassGroup(spacing: 8)
    }

    private var hotWordMenu: some View {
        Menu {
            Button("全选") { model.setHotWordGroups(Set(model.hotWordGroups)) }
            Button("清空") { model.setHotWordGroups([]) }
            if !model.hotWordGroups.isEmpty { Divider() }
            ForEach(model.hotWordGroups, id: \.self) { name in
                Toggle(name.isEmpty ? "未分组" : name, isOn: Binding(
                    get: { model.selectedHotWordGroups.contains(name) },
                    set: { on in
                        var next = model.selectedHotWordGroups
                        if on { next.insert(name) } else { next.remove(name) }
                        model.setHotWordGroups(next)
                    }))
            }
        } label: {
            Label("热词组 \(model.selectedHotWordGroups.count)/\(model.hotWordGroups.count)", systemImage: "text.book.closed")
        }
        .menuStyle(.borderlessButton)
        .help("选择本次转录使用的热词组")
        .accessibilityLabel("热词组")
    }

    @ViewBuilder private var speakerToggle: some View {
        let ready = models.isReady(LocalModel.diar)
        let on = model.speakers && ready
        Button {
            if ready { withAnimation(.snappy) { model.speakers.toggle() } } else { models.presenting = true }
        } label: {
            Label("区分说话人", systemImage: on ? "person.2.fill" : "person.2")
                .foregroundStyle(on ? Brand.accent : Color.primary)
        }
        .glassButton().controlSize(.large)
        .help(ready ? "给每段话标上说话人（最多 4 人）" : "需要先下载 Sortformer 模型（236 MB）")
        .accessibilityValue(on ? "开" : "关")
    }

    private var startDisabled: Bool {
        model.readyFiles.isEmpty || model.submitting || (model.mode == "offline" && !models.offlineReady)
    }

    private var startButton: some View {
        Button { Task { await model.submit() } } label: {
            HStack(spacing: 6) {
                if model.submitting { ProgressView().controlSize(.small) }
                Text(model.readyFiles.count > 1 ? "转写 \(model.readyFiles.count) 个文件" : "开始转写").fontWeight(.semibold)
            }
            .padding(.horizontal, 6)
        }
        .glassButton(prominent: true).controlSize(.large)
        .disabled(startDisabled).keyboardShortcut(.defaultAction)
        .animation(.easeOut(duration: 0.15), value: startDisabled)
    }

    private var engineBinding: Binding<String> {
        Binding(get: { model.mode == "offline" ? "local" : Service.cloud(model.engine).id }, set: { apply($0) })
    }

    private func apply(_ value: String) {
        choice = value
        if value == "local" { model.mode = "offline" } else { model.mode = "online"; model.engine = Service.cloud(value).id }
        Task { await model.updateInfo() }
    }

    /// Models are downloading (possibly with the panel closed): say so, where the person is looking.
    @ViewBuilder private var downloadBanner: some View {
        if model.mode == "offline", models.isDownloading || models.anyProgress {
            let fraction = Double(models.batchDone) / Double(max(models.batchTotal, 1))
            HStack(spacing: 12) {
                ProgressView(value: fraction).frame(width: 90)
                Text(models.isDownloading ? "正在下载本机模型 \(Int(fraction * 100))%" + (models.speedText.map { " · \($0)" } ?? "") : "本机模型下载已暂停")
                    .monospacedDigit().frame(maxWidth: .infinity, alignment: .leading)
                Button("查看") { models.presenting = true }.glassButton()
            }
            .padding(.horizontal, 16).padding(.vertical, 10).glassPanel(radius: 18)
        } else if model.mode == "offline", models.checked, !models.offlineReady {
            HStack(spacing: 10) {
                Image(systemName: "arrow.down.circle").foregroundStyle(Brand.accent)
                Text("本机转写需要先下载模型（3.7 GB）").frame(maxWidth: .infinity, alignment: .leading)
                Button("改用云端") { apply("dashscope") }.glassButton()
                Button("下载") { models.presenting = true }.glassButton(prominent: true)
            }
            .padding(.horizontal, 16).padding(.vertical, 10).glassPanel(radius: 18)
        }
    }
}

// MARK: - Task

struct TaskView: View {
    @ObservedObject var model: WorkspaceModel
    let id: Int
    @State private var confirmDelete = false

    var body: some View {
        if let detail = model.detail, detail.task.id == id {
            let task = detail.task
            VStack(spacing: 0) {
                if task.isDone { TaskResult(model: model, task: task, confirmDelete: $confirmDelete) }
                else if task.isFailed { failed(task) }
                else { RunningView(model: model, task: task, chunks: detail.chunks) }
            }
            .navigationTitle(task.displayTitle)
            .navigationSubtitle(subtitle(task))
            .toolbar {
                // A finished task puts this menu after its own tools, so the order stays tools → more.
                if !task.isDone { ToolbarItem(placement: .primaryAction) { MoreMenu(model: model, task: task, confirmDelete: $confirmDelete) } }
            }
            .confirmationDialog("删除这条记录？", isPresented: $confirmDelete) {
                Button("删除记录", role: .destructive) { Task { await model.delete(task.id) } }
            } message: { Text("只删除历史，录音和已生成的文件不会动。") }
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func subtitle(_ task: TTask) -> String {
        [task.mode == "offline" ? "本机" : "云端", task.durationS.map(clock), task.date?.formatted(date: .abbreviated, time: .shortened)]
            .compactMap { $0 }.joined(separator: " · ")
    }

    private func failed(_ task: TTask) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle").font(.system(size: 40, weight: .light)).foregroundStyle(.orange)
                .symbolRenderingMode(.hierarchical)
            VStack(spacing: 6) {
                Text("转写没有完成").font(.title2.weight(.semibold))
                if let error = task.error, !error.isEmpty {
                    Text(error).foregroundStyle(.secondary).multilineTextAlignment(.center).textSelection(.enabled).frame(maxWidth: 460)
                }
            }
            if let message = model.actionError { Text(message).font(.callout).foregroundStyle(.red).textSelection(.enabled) }
            HStack(spacing: 10) {
                if task.srcExists == true {
                    Button("换个设置重来") { model.select(.new) { model.stage([model.audioURL(for: task)]) } }.glassButton().controlSize(.large)
                }
                if task.resumable == true {
                    Button("从断点继续") { Task { await model.resume(task.id) } }.glassButton(prominent: true).controlSize(.large)
                }
            }
            .glassGroup()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity).padding(40)
    }
}

struct RunningView: View {
    @ObservedObject var model: WorkspaceModel
    let task: TTask
    let chunks: [TChunk]

    private var liveText: String { chunks.compactMap(\.text).joined(separator: "\n\n") }

    @AppStorage("readingWidth") private var width = 680.0

    var body: some View {
        // The progress stays put; only the live text scrolls, inside its own container, following the newest words.
        VStack(spacing: 0) {
            VStack(spacing: 14) {
                WaveformMark(energy: task.running ? 0.85 : 0)
                Text(task.running ? "\(Int(task.percent))%" : "排队中")
                    .font(.system(size: 44, weight: .semibold, design: .rounded)).monospacedDigit()
                    .contentTransition(.numericText()).animation(.snappy, value: Int(task.percent))
                ProgressView(value: task.running ? max(task.percent, 2) : 0, total: 100).tint(Brand.accent).frame(maxWidth: 320)
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    let elapsed = task.date.map { max(0, context.date.timeIntervalSince($0)) } ?? 0
                    let eta = task.running && task.percent >= 8 ? " · 还需约 \(clock(elapsed * (100 - task.percent) / task.percent))" : ""
                    Text(task.cancelling == true ? "正在停止…" : task.running
                         ? "\(task.stage ?? "转写中") · 已用 \(clock(elapsed))" + eta
                         : "前面的任务完成后自动开始")
                        .font(.callout.monospacedDigit()).foregroundStyle(.secondary)
                }
                if let message = model.actionError { Text(message).font(.callout).foregroundStyle(.red).textSelection(.enabled) }
                Button("停止") { Task { await model.cancel(task.id) } }
                    .glassButton().disabled(task.cancelling == true || !task.running)
            }
            .padding(.top, 40).padding(.bottom, 24)
            if !liveText.isEmpty {
                ScrollViewReader { proxy in
                    ScrollView {
                        Text(liveText).font(.system(size: 16)).lineSpacing(9).foregroundStyle(.secondary).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(24)
                        Color.clear.frame(height: 1).id("end")
                    }
                    .scrollIndicators(.never)
                    .onAppear { proxy.scrollTo("end", anchor: .bottom) }
                    .onChange(of: chunks.count) { _, _ in withAnimation(.smooth) { proxy.scrollTo("end", anchor: .bottom) } }
                }
                .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.primary.opacity(0.035)))
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .frame(maxWidth: width + 48)
                .padding(.horizontal, 32).padding(.bottom, 32)
                .transition(.opacity)
            } else { Spacer(minLength: 0) }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .animation(.smooth, value: liveText.isEmpty)
    }
}

struct TaskResult: View {
    @ObservedObject var model: WorkspaceModel
    let task: TTask
    @Binding var confirmDelete: Bool
    @StateObject private var player = PlayerModel()
    @StateObject private var editor = ProseEditorController()
    @AppStorage("resultTab") private var tab = 0
    @AppStorage("readingWidth") private var width = 680.0
    @AppStorage("summaryPaneWidth") private var summaryWidth = 360.0
    @AppStorage("showSummaryPane") private var showSummaryPane = false
    @State private var showChatPane = false
    private var draft: String {
        get { model.transcriptDraft }
        nonmutating set { if !editingLocked { model.transcriptDraft = newValue } }
    }
    private var draftCues: [Cue] {
        get { model.cueDraft }
        nonmutating set { if !editingLocked { model.cueDraft = newValue } }
    }
    @State private var copied = false
    @State private var saving = false
    @State private var finding = false
    @State private var query = ""
    @State private var replacement = ""
    @State private var hit = 0
    @State private var showHits = true
    @State private var focusCue: Int?
    @State private var renaming = false
    @State private var reprompt = false
    @State private var summary: TSummary?
    @State private var startingSummary = false
    @State private var summaryStartedAt: Date?
    @State private var showThinking = false

    private var loaded: Bool { model.outputsFor == task.id }
    private var dirty: Bool { loaded && model.hasUnsavedEdits }
    private var editingLocked: Bool { saving || model.editingLocked }
    private var hasAudio: Bool { task.srcExists == true }
    private static let barRoom: CGFloat = 84

    var body: some View {
        if !loaded {
            Group {
                if let problem = model.actionError {
                    ContentUnavailableView {
                        Label("打不开这条记录的文稿", systemImage: "doc.questionmark")
                    } description: {
                        Text(problem.replacingOccurrences(of: "读取结果失败：", with: ""))
                    }
                } else { ProgressView() }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            GeometryReader { geometry in
                let transcriptMinimum: CGFloat = 360
                let chatMinimum: CGFloat = showChatPane ? 320 : 0
                let paneSpacing: CGFloat = showSummaryPane && showChatPane ? 24 : 0
                let narrow = geometry.size.width < transcriptMinimum + (showSummaryPane ? summaryWidth : 0) + chatMinimum + paneSpacing
                HStack(spacing: 0) {
                    Group { if tab == 0 { transcript } else { subtitles } }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .overlay { WidthHandles() }
                    if showSummaryPane {
                        Divider()
                        summaryView
                            .frame(width: summaryWidth)
                            .frame(maxHeight: .infinity)
                            .overlay(alignment: .leading) { SummaryWidthHandle(width: $summaryWidth) }
                    }
                    if showChatPane && !narrow {
                        Divider()
                        chatPane.frame(width: 320)
                    }
                }
                .overlay(alignment: .trailing) {
                    if showChatPane && narrow {
                        chatPane
                            .frame(width: min(320, max(260, geometry.size.width * 0.82)))
                            .background(.regularMaterial)
                            .shadow(color: .black.opacity(0.18), radius: 12, x: -4)
                    }
                }
            }
                .overlay(alignment: .top) { if finding && tab < 2 { findBar.transition(.move(edge: .top).combined(with: .opacity)) } }
                .overlay(alignment: .bottom) { if hasAudio { audioBar } }
                .safeAreaInset(edge: .top, spacing: 0) {
                    if let message = model.actionError {
                        Label(message, systemImage: "exclamationmark.triangle.fill").font(.callout).foregroundStyle(.red)
                            .padding(.horizontal, 16).padding(.vertical, 8).glassPanel(radius: 14).padding(.top, 8)
                    }
                }
                .animation(.smooth(duration: 0.25), value: finding)
                .toolbar { toolbarContent }
                .task(id: task.id) {
                    summary = await model.loadSummary(task.id)
                }
                .onReceive(NotificationCenter.default.publisher(for: NSWindow.didBecomeMainNotification)) { _ in
                    Task {
                        guard !startingSummary, summary?.pending != true else { return }
                        let next = await model.loadSummary(task.id)
                        guard model.selection == .task(task.id), !startingSummary, summary?.pending != true else { return }
                        summary = next
                    }
                }
                .task(id: summary?.pending == true) {
                    await pollSummary()
                }
                .onAppear {
                    if tab == 2 { tab = 0; showSummaryPane = true }
                    if hasAudio { player.load(model.audioURL(for: task)) }
                }
                .onDisappear { player.unload() }
                .onChange(of: tab) { _, _ in finding = false }
                .onChange(of: finding) { _, on in if on { reveal() } else { editor.mark([], current: nil); focusCue = nil } }
                .onChange(of: query) { _, _ in hit = 0; reveal() }
        }
    }

    @ToolbarContentBuilder private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .principal) {
            Picker("视图", selection: $tab) {
                Text("文稿").tag(0)
                Text("字幕").tag(1)
            }
            .pickerStyle(.segmented).labelsHidden().fixedSize()
            .disabled(dirty || editingLocked).help(dirty ? "先保存或还原修改" : "")
        }
        if dirty {
            ToolbarItemGroup(placement: .primaryAction) {
                Button("还原") { model.discardEdits() }.disabled(editingLocked)
                Button {
                    guard !editingLocked else { return }
                    let id = task.id
                    let text = draft
                    let edited = draftCues
                    let saveText = draft != model.txt
                    saving = true
                    Task {
                        if saveText { await model.saveTranscript(text, for: id) }
                        else { await model.saveCues(edited, for: id) }
                        saving = false
                    }
                } label: { Text("保存") }
                .buttonStyle(.borderedProminent).disabled(editingLocked).keyboardShortcut("s")
            }
        } else {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { showSummaryPane.toggle() } label: {
                    Image(systemName: showSummaryPane ? "text.badge.xmark" : "text.badge.star")
                }
                .help(showSummaryPane ? "关闭总结" : "打开总结")
                .accessibilityLabel(showSummaryPane ? "关闭总结" : "打开总结")
                Button { showChatPane.toggle() } label: {
                    Image(systemName: showChatPane ? "bubble.left.and.bubble.right.fill" : "bubble.left.and.bubble.right")
                }
                .help(showChatPane ? "关闭文稿对话" : "打开文稿对话")
                .accessibilityLabel(showChatPane ? "关闭文稿对话" : "打开文稿对话")
                if tab < 2 {
                    Button { find() } label: { Image(systemName: "magnifyingglass") }
                        .keyboardShortcut("f").help("查找和替换（⌘F）").accessibilityLabel("查找和替换")
                }
                if tab == 1, speakerNames.count > 0 {
                    Button { renaming = true } label: { Image(systemName: "person.2") }
                        .help("重命名说话人").accessibilityLabel("重命名说话人")
                        .popover(isPresented: $renaming, arrowEdge: .bottom) { SpeakerRename(names: speakerNames, apply: renameSpeakers) }
                        .disabled(editingLocked)
                }
                if showSummaryPane, summary?.available != false, summary?.pending != true, !startingSummary, summary?.content != nil || summary?.reasoning != nil || summary?.status == "failed" {
                    Button { reprompt = true } label: { Image(systemName: "arrow.clockwise") }
                        .help("换提示词重新总结").accessibilityLabel("重新总结")
                        .popover(isPresented: $reprompt, arrowEdge: .bottom) {
                            Resummarize { prompt in reprompt = false; Task { await startSummary(prompt: prompt) } }
                        }
                }
                Menu {
                    Button("复制文稿（TXT）") { copy(model.txt) }
                    Button("复制总结（Markdown）") { copy(summary?.markdown ?? "") }.disabled(summary?.content == nil || summary?.pending == true)
                } label: { Image(systemName: copied ? "checkmark" : "doc.on.doc").contentTransition(.symbolEffect(.replace)) }
                primaryAction: { copy(showSummaryPane ? (summary?.markdown ?? "") : model.txt) }
                    .help(showSummaryPane ? "复制总结 Markdown" : "复制文稿").accessibilityLabel(copied ? "已复制" : "复制")
            }
            ToolbarSpacerIfAvailable()
            ToolbarItemGroup(placement: .primaryAction) {
                Menu {
                    Button("TXT 文稿…") { model.export(kind: "txt", name: task.name) }
                    Button("SRT 字幕…") { model.export(kind: "srt", name: task.name) }
                } label: { Image(systemName: "arrow.down.circle") }
                    .help("下载").accessibilityLabel("下载")
                MoreMenu(model: model, task: task, confirmDelete: $confirmDelete)
            }
        }
    }

    private func find() {
        finding.toggle()
    }

    private var chatPane: some View {
        TranscriptChatView(model: model, taskID: task.id, onCitation: revealCitation)
    }

    private func revealCitation(_ citation: TranscriptCitation) {
        tab = 0
        finding = false
        let nsText = draft as NSString
        var range = nsText.range(of: citation.quote)
        if range.location == NSNotFound {
            range = (draft as NSString).range(of: citation.quote.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        guard range.location != NSNotFound else {
            model.chatError = "原文已经修改，找不到这条引用。引用内容：\(citation.quote)"
            return
        }
        editor.mark([range], current: 0)
    }

    private func copy(_ text: String) {
        guard !text.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        withAnimation(.snappy) { copied = true }
        Task { try? await Task.sleep(for: .seconds(1.6)); withAnimation(.snappy) { copied = false } }
    }

    private func startSummary(prompt: String? = nil) async {
        guard !startingSummary, summary?.pending != true else { return }
        startingSummary = true
        summaryStartedAt = Date()
        showThinking = false
        defer { startingSummary = false }
        summary = await model.summarize(task.id, prompt: prompt)
    }

    private func pollSummary() async {
        // One view-owned poller; leaving this record cancels it immediately.
        while summary?.pending == true, !Task.isCancelled {
            do { try await Task.sleep(for: .milliseconds(100)) } catch { return }
            let next = await model.loadSummary(task.id)
            guard !Task.isCancelled else { return }
            if let next { summary = next }
        }
    }

    // MARK: Speakers: subtitles start with "名字：", and renaming rewrites both the subtitles and the transcript

    private var speakerNames: [String] {
        var seen: [String] = []
        for cue in model.cues {
            guard let r = cue.text.range(of: "：") else { continue }
            let name = String(cue.text[..<r.lowerBound])
            if name.count <= 12, !name.isEmpty, !seen.contains(name) { seen.append(name) }
        }
        return seen.count >= 1 && model.cues.filter { $0.text.contains("：") }.count * 2 > model.cues.count ? seen : []
    }

    private func renameSpeakers(_ map: [String: String]) {
        guard !editingLocked, !dirty else { return }
        renaming = false
        saving = true
        let id = task.id
        Task {
            await model.renameSpeakers(map, for: id)
            saving = false
        }
    }

    /// Where each subtitle begins in the transcript, so a click in the text can move the audio there.
    private func time(at offset: Int) -> Double? {
        let text = draft as NSString
        var from = 0, best: Double?
        for cue in draftCues {
            let probe = String(cue.text.split(separator: "：", maxSplits: 1).last ?? "").trimmingCharacters(in: .whitespaces).prefix(8)
            guard !probe.isEmpty, from < text.length else { continue }
            let r = text.range(of: String(probe), range: NSRange(location: from, length: text.length - from))
            guard r.location != NSNotFound else { continue }
            if r.location > offset { break }
            best = cue.start; from = NSMaxRange(r)
        }
        return best
    }

    // MARK: Find and replace: one bar for the transcript and the subtitles

    /// What is searched: the transcript, or the subtitles joined by a separator no one types.
    private static let sep = "\u{1}"
    private var haystack: String { tab == 0 ? draft : draftCues.map(\.text).joined(separator: Self.sep) }

    private var hits: [NSRange] {
        guard !query.isEmpty else { return [] }
        let text = haystack as NSString
        var out: [NSRange] = [], from = 0
        while from < text.length {
            let r = text.range(of: query, options: .caseInsensitive, range: NSRange(location: from, length: text.length - from))
            guard r.location != NSNotFound else { break }
            out.append(r); from = NSMaxRange(r)
        }
        return out
    }

    private func write(_ text: String) {
        if tab == 0 { draft = text; return }
        let parts = text.components(separatedBy: Self.sep)
        guard parts.count == draftCues.count else { return }
        for i in draftCues.indices where draftCues[i].text != parts[i] { draftCues[i].text = parts[i] }
    }

    /// Marks every match and brings the current one into view.
    private func reveal() {
        let all = hits
        if !all.isEmpty { hit = min(max(hit, 0), all.count - 1) }
        if tab == 0 { DispatchQueue.main.async { editor.mark(all, current: all.isEmpty ? nil : hit) } }
        else if !all.isEmpty {
            let before = (haystack as NSString).substring(to: all[hit].location)
            let index = before.components(separatedBy: Self.sep).count - 1
            focusCue = draftCues.indices.contains(index) ? draftCues[index].id : nil
        } else { focusCue = nil }
    }

    private func step(_ delta: Int) {
        let n = hits.count
        guard n > 0 else { return }
        hit = (hit + delta + n) % n
        reveal()
    }

    private func replaceOne() {
        let all = hits
        guard all.indices.contains(hit) else { return }
        write((haystack as NSString).replacingCharacters(in: all[hit], with: replacement))
        DispatchQueue.main.async { reveal() }
    }

    private func replaceAll() {
        write((haystack as NSString).replacingOccurrences(of: query, with: replacement, options: .caseInsensitive, range: NSRange(location: 0, length: (haystack as NSString).length)))
        DispatchQueue.main.async { reveal() }
    }

    private func snippet(_ r: NSRange) -> AttributedString {
        let text = haystack as NSString
        let lo = max(0, r.location - 14), hi = min(text.length, NSMaxRange(r) + 24)
        func clean(_ s: String) -> String { s.replacingOccurrences(of: Self.sep, with: " ").replacingOccurrences(of: "\n", with: " ") }
        var head = AttributedString((lo > 0 ? "…" : "") + clean(text.substring(with: NSRange(location: lo, length: r.location - lo))))
        var word = AttributedString(clean(text.substring(with: r)))
        word.foregroundColor = Brand.accent; word.font = .callout.weight(.semibold)
        let tail = AttributedString(clean(text.substring(with: NSRange(location: NSMaxRange(r), length: hi - NSMaxRange(r)))) + (hi < text.length ? "…" : ""))
        head.append(word); head.append(tail)
        return head
    }

    private var findBar: some View {
        let all = hits
        return VStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("查找", text: $query).textFieldStyle(.plain).frame(width: 140).onSubmit { step(1) }
                Text(query.isEmpty ? "" : all.isEmpty ? "无结果" : "\(hit + 1)/\(all.count)")
                    .font(.callout.monospacedDigit()).foregroundStyle(.secondary).frame(width: 52, alignment: .trailing)
                Button { step(-1) } label: { Image(systemName: "chevron.up") }.buttonStyle(.borderless).disabled(all.isEmpty)
                    .keyboardShortcut("g", modifiers: [.command, .shift]).help("上一处（⇧⌘G）").accessibilityLabel("上一处")
                Button { step(1) } label: { Image(systemName: "chevron.down") }.buttonStyle(.borderless).disabled(all.isEmpty)
                    .keyboardShortcut("g").help("下一处（⌘G）").accessibilityLabel("下一处")
                Button { withAnimation(.snappy) { showHits.toggle() } } label: { Image(systemName: "list.bullet") }.buttonStyle(.borderless)
                    .foregroundStyle(showHits ? Brand.accent : .secondary).disabled(all.isEmpty).help("显示匹配内容").accessibilityLabel("显示匹配内容")
                Divider().frame(height: 16)
                TextField("替换为", text: $replacement).textFieldStyle(.plain).frame(width: 120).onSubmit(replaceOne)
                Button("替换", action: replaceOne).disabled(all.isEmpty || editingLocked).glassButton()
                Button("全部", action: replaceAll).disabled(all.isEmpty || editingLocked).glassButton().help("全部替换")
                Button { finding = false } label: { Image(systemName: "xmark") }.buttonStyle(.borderless).keyboardShortcut(.cancelAction).accessibilityLabel("关闭查找")
            }
            .padding(.leading, 16).padding(.trailing, 8).padding(.vertical, 6)
            .glassCapsule()
            if showHits, !all.isEmpty {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(all.indices, id: \.self) { i in
                                Button { hit = i; reveal() } label: {
                                    Text(snippet(all[i])).font(.callout).lineLimit(1).frame(maxWidth: .infinity, alignment: .leading)
                                        .padding(.horizontal, 12).padding(.vertical, 6)
                                        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Brand.accent.opacity(i == hit ? 0.14 : 0)))
                                        .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain).id(i)
                            }
                        }
                        .padding(6)
                    }
                    .frame(maxHeight: min(CGFloat(all.count) * 30 + 12, 180))
                    .onChange(of: hit) { _, new in proxy.scrollTo(new, anchor: .center) }
                }
                .frame(maxWidth: 560)
                .glassPanel(radius: 16)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.top, 10)
    }

    @ViewBuilder private var summaryView: some View {
        if !startingSummary, let summary, summary.content != nil || summary.reasoning != nil {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if summary.status == "failed", let error = summary.error {
                        HStack(alignment: .top, spacing: 12) {
                            Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Button("重试") { reprompt = true }.glassButton()
                        }
                    }
                    if let reasoning = summary.reasoning { thinking(reasoning, live: summary.pending && summary.content == nil) }
                    if let markdown = summary.content { StreamingMarkdown(source: markdown, live: summary.pending, onSeek: hasAudio ? { player.seek($0, play: true) } : nil).textSelection(.enabled).transition(.opacity) }
                }
                .frame(maxWidth: width, alignment: .leading)
                .padding(.horizontal, 16).padding(.top, 28).padding(.bottom, hasAudio ? Self.barRoom : 28)
                .frame(maxWidth: .infinity)
            }
        } else if startingSummary || summary?.pending == true {
            VStack(spacing: 12) {
                ProgressView()
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    let elapsed = Int(context.date.timeIntervalSince(summaryStartedAt ?? context.date))
                    Text(elapsed > 0 ? "正在等待模型输出… \(elapsed) 秒" : "正在等待模型输出…")
                        .foregroundStyle(.secondary).monospacedDigit()
                }
            }
            .onAppear { if summaryStartedAt == nil { summaryStartedAt = Date() } }
        } else if summary?.available == false {
            ContentUnavailableView {
                Label("还没有配置总结服务", systemImage: "text.badge.star")
            } description: {
                Text("在设置 › 总结里填入密钥。")
            } actions: {
                Button("打开设置") { openSettings(tab: "summary") }.glassButton().controlSize(.large)
            }
        } else {
            ContentUnavailableView {
                Label("总结", systemImage: "text.badge.star")
            } description: {
                if let error = summary?.error, summary?.status == "failed" { Text(error).foregroundStyle(.red) }
                else { Text("文稿会发送到总结服务。") }
            } actions: {
                Button(summary?.status == "failed" ? "重试" : "生成总结") { if summary?.status == "failed" { reprompt = true } else { Task { await startSummary() } } }
                    .glassButton(prominent: true).controlSize(.large)
            }
        }
    }

    /// The model's thinking, folded by default; while it is still thinking the label says so.
    private func thinking(_ text: String, live: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { withAnimation(.snappy) { showThinking.toggle() } } label: {
                HStack(spacing: 6) {
                    Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                        .rotationEffect(.degrees(showThinking ? 90 : 0))
                    Text(live ? "正在思考…" : "思考过程")
                    if live { ProgressView().controlSize(.mini) }
                }
                .foregroundStyle(.secondary).contentShape(Rectangle())
            }
            .buttonStyle(.plain).accessibilityLabel(showThinking ? "收起思考过程" : "展开思考过程")
            if showThinking {
                Text(text).font(.callout).foregroundStyle(.secondary).lineSpacing(5).textSelection(.enabled)
                    .padding(.leading, 14)
                    .overlay(alignment: .leading) { Capsule().fill(.quaternary).frame(width: 2) }
                    .transition(.opacity)
            }
        }
    }

    private var transcript: some View {
        ProseEditor(text: Binding(get: { draft }, set: { draft = $0 }), controller: editor, isEditable: !editingLocked,
                    topInset: finding ? 64 : 20, bottomInset: hasAudio ? Self.barRoom : 24,
                    onClick: hasAudio ? { offset in if let t = time(at: offset) { player.seek(t) } } : nil)
            .frame(maxWidth: width + 32, maxHeight: .infinity)
            .frame(maxWidth: .infinity)
            .accessibilityLabel("文稿")
    }

    private var subtitles: some View {
        let current = draftCues.lastIndex { $0.start <= player.time }
        return ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(Binding(get: { draftCues }, set: { draftCues = $0 })) { $cue in
                        let active = player.playing && current == cue.id
                        HStack(alignment: .firstTextBaseline, spacing: 14) {
                            Button(clock(cue.start)) { player.seek(cue.start, play: true) }
                                .buttonStyle(.plain).font(.caption.monospacedDigit())
                                .foregroundStyle(active ? Brand.onAccent : .secondary)
                                .padding(.horizontal, 8).padding(.vertical, 3)
                                .background(Capsule().fill(active ? Brand.accent : Color.primary.opacity(0.06)))
                                .disabled(!hasAudio).help(hasAudio ? "从这里播放" : "")
                            TextField("", text: $cue.text, axis: .vertical)
                                .textFieldStyle(.plain).font(.system(size: 16)).lineSpacing(5)
                                .disabled(editingLocked)
                        }
                        .padding(.vertical, 8).padding(.horizontal, 12)
                        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Brand.accent.opacity(active ? 0.10 : focusCue == cue.id ? 0.16 : 0)))
                        .animation(.easeOut(duration: 0.2), value: active)
                        .id(cue.id)
                    }
                }
                .padding(.horizontal, 16).padding(.top, finding ? 64 : 16).padding(.bottom, hasAudio ? Self.barRoom : 24)
                .frame(maxWidth: width + 32).frame(maxWidth: .infinity)
            }
            .onChange(of: current) { _, new in
                if player.playing, let new { withAnimation(.easeInOut(duration: 0.35)) { proxy.scrollTo(new, anchor: .center) } }
            }
            .onChange(of: focusCue) { _, new in if let new { withAnimation(.easeInOut(duration: 0.3)) { proxy.scrollTo(new, anchor: .center) } } }
        }
    }

    /// Floats over the text; the reading column scrolls underneath the glass.
    private var audioBar: some View {
        HStack(spacing: 10) {
            Button { player.skip(-5) } label: { Image(systemName: "gobackward.5") }
                .buttonStyle(.borderless).help("后退 5 秒").accessibilityLabel("后退 5 秒")
            Button { player.toggle() } label: {
                Image(systemName: player.playing ? "pause.fill" : "play.fill").font(.system(size: 16)).frame(width: 22, height: 22)
                    .contentTransition(.symbolEffect(.replace))
            }
            .buttonStyle(.borderless).accessibilityLabel(player.playing ? "暂停" : "播放")
            Button { player.skip(5) } label: { Image(systemName: "goforward.5") }
                .buttonStyle(.borderless).help("前进 5 秒").accessibilityLabel("前进 5 秒")
            Text(clock(player.time)).font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(minWidth: 40, alignment: .trailing)
            Slider(value: Binding(get: { player.time }, set: { player.seek($0) }), in: 0...max(player.duration, 1)).controlSize(.small).tint(Brand.accent)
            Text(clock(player.duration)).font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(minWidth: 40, alignment: .leading)
            Menu {
                Picker("速度", selection: $player.rate) {
                    ForEach([Float(0.75), 1, 1.25, 1.5, 2], id: \.self) { Text(rateText($0)).tag($0) }
                }.pickerStyle(.inline)
            } label: { Text(rateText(player.rate)).font(.caption.monospacedDigit().weight(.medium)) }
                .menuStyle(.button).buttonStyle(.borderless).menuIndicator(.hidden).fixedSize()
                .help("播放速度").accessibilityLabel("播放速度 \(rateText(player.rate))")
        }
        .padding(.horizontal, 18).padding(.vertical, 12)
        .glassCapsule()
        .frame(maxWidth: 620)
        .padding(.horizontal, 24).padding(.bottom, 16)
    }

    private func rateText(_ rate: Float) -> String {
        rate == 1 ? "1×" : String(format: "%g×", rate)
    }
}

struct MoreMenu: View {
    @ObservedObject var model: WorkspaceModel
    let task: TTask
    @Binding var confirmDelete: Bool

    var body: some View {
        Menu {
            Button("换个设置重新转写", systemImage: "arrow.clockwise") { model.select(.new) { model.stage([model.audioURL(for: task)]) } }
                .disabled(task.srcExists != true || task.isActive)
            Button("在访达中显示", systemImage: "folder") { model.reveal(task) }
            Divider()
            Button("删除…", systemImage: "trash", role: .destructive) { confirmDelete = true }.disabled(task.isActive)
        } label: { Image(systemName: "ellipsis") }
            .menuIndicator(.hidden).help("更多").accessibilityLabel("更多操作")
    }
}

/// `ToolbarSpacer` splits the toolbar into separate glass groups on macOS 26; earlier systems need nothing.
struct ToolbarSpacerIfAvailable: ToolbarContent {
    var body: some ToolbarContent {
        if #available(macOS 26.0, *) { ToolbarSpacer(.fixed, placement: .primaryAction) }
    }
}

// MARK: - Settings (Transcript engines and hot words)

/// Lets SwiftUI reach the text view for the native find bar (highlights, next/previous, replace).
final class ProseEditorController: ObservableObject {
    weak var textView: NSTextView?
    /// Tints every match, the current one stronger, and scrolls it into view without taking focus from the find field.
    func mark(_ ranges: [NSRange], current: Int?) {
        guard let view = textView, let layout = view.layoutManager else { return }
        let length = (view.string as NSString).length
        layout.removeTemporaryAttribute(.backgroundColor, forCharacterRange: NSRange(location: 0, length: length))
        for r in ranges where NSMaxRange(r) <= length {
            layout.addTemporaryAttribute(.backgroundColor, value: NSColor.findHighlightColor.withAlphaComponent(0.3), forCharacterRange: r)
        }
        guard let current, ranges.indices.contains(current), NSMaxRange(ranges[current]) <= length else { return }
        let r = ranges[current]
        layout.addTemporaryAttribute(.backgroundColor, value: NSColor.findHighlightColor, forCharacterRange: r)
        view.scrollRangeToVisible(r)
        view.showFindIndicator(for: r)
    }

    func markCitation(_ quote: String) {
        guard let view = textView else { return }
        let range = (view.string as NSString).range(of: quote)
        guard range.location != NSNotFound else { return }
        mark([range], current: 0)
    }
}

/// A plain text editor with a reading-friendly line height, the system find bar, and room under the floating player.
struct ProseEditor: NSViewRepresentable {
    @Binding var text: String
    var controller: ProseEditorController? = nil
    var isEditable = true
    var topInset: CGFloat = 20
    var bottomInset: CGFloat = 24
    /// A plain click (not a drag or a keyboard move) puts the caret here; the audio follows.
    var onClick: ((Int) -> Void)? = nil

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    private static var attributes: [NSAttributedString.Key: Any] {
        let style = NSMutableParagraphStyle()
        style.lineSpacing = 9
        return [.font: NSFont.systemFont(ofSize: 16), .foregroundColor: NSColor.textColor, .paragraphStyle: style]
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = false
        scroll.drawsBackground = false
        scroll.borderType = .noBorder
        scroll.automaticallyAdjustsContentInsets = false
        scroll.contentInsets = NSEdgeInsets(top: topInset, left: 0, bottom: bottomInset, right: 0)
        let view = NSTextView()
        view.isRichText = false
        view.isEditable = isEditable
        view.drawsBackground = false
        view.allowsUndo = true
        view.isAutomaticQuoteSubstitutionEnabled = false
        view.isAutomaticDashSubstitutionEnabled = false
        view.usesFindBar = true
        view.isIncrementalSearchingEnabled = true
        view.textContainerInset = NSSize(width: 4, height: 6)
        view.isVerticallyResizable = true
        view.autoresizingMask = [.width]
        view.textContainer?.widthTracksTextView = true
        view.typingAttributes = Self.attributes
        view.delegate = context.coordinator
        view.setAccessibilityLabel("文稿")
        scroll.documentView = view
        scroll.findBarPosition = .aboveContent
        controller?.textView = view
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        if scroll.contentInsets.bottom != bottomInset { scroll.contentInsets.bottom = bottomInset }
        if scroll.contentInsets.top != topInset { scroll.contentInsets.top = topInset }
        guard let view = scroll.documentView as? NSTextView else { return }
        view.isEditable = isEditable
        guard view.string != text else { return }
        view.string = text
        view.textStorage?.setAttributes(Self.attributes, range: NSRange(location: 0, length: (text as NSString).length))
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ProseEditor
        init(_ parent: ProseEditor) { self.parent = parent }
        func textDidChange(_ notification: Notification) {
            guard parent.isEditable, let view = notification.object as? NSTextView else { return }
            parent.text = view.string
        }
        func textViewDidChangeSelection(_ notification: Notification) {
            guard let view = notification.object as? NSTextView, let event = NSApp.currentEvent, event.type == .leftMouseUp || event.type == .leftMouseDown,
                  view.selectedRange().length == 0 else { return }
            parent.onClick?(view.selectedRange().location)
        }
    }
}

/// Grab either edge of the reading column to set its width; double-click to go back to the default.
struct WidthHandles: View {
    @AppStorage("readingWidth") private var width = 680.0
    static let range = 420.0...1400.0

    var body: some View {
        GeometryReader { geo in
            let column = min(width + 32, geo.size.width - 24)
            HStack(spacing: 0) {
                Handle(side: -1, width: $width)
                Spacer(minLength: 0)
                Handle(side: 1, width: $width)
            }
            .frame(width: column + 24, height: geo.size.height)
            .frame(maxWidth: .infinity)
        }
    }

    private struct Handle: View {
        let side: Double
        @Binding var width: Double
        @State private var hover = false
        @State private var start: Double?

        var body: some View {
            Color.clear.frame(width: 12).contentShape(Rectangle())
                .overlay {
                    Capsule().fill(Brand.accent.opacity(start != nil ? 0.9 : hover ? 0.45 : 0))
                        .frame(width: 3, height: start != nil ? 56 : 36)
                        .animation(.snappy(duration: 0.2), value: hover)
                        .animation(.snappy(duration: 0.2), value: start != nil)
                }
                .overlay(alignment: side < 0 ? .trailing : .leading) {
                    if start != nil {
                        Text("\(Int(width))").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                            .padding(.horizontal, 6).padding(.vertical, 2).glassCapsule()
                            .fixedSize().offset(x: side * 34).transition(.opacity)
                    }
                }
                .onHover { inside in
                    hover = inside
                    if inside { NSCursor.resizeLeftRight.push() } else { NSCursor.pop() }
                }
                .gesture(DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    .onChanged { drag in
                        let base = start ?? width
                        if start == nil { withAnimation(.snappy(duration: 0.2)) { start = base } }
                        // The column is centred, so each edge moves half the change.
                        width = min(WidthHandles.range.upperBound, max(WidthHandles.range.lowerBound, base + side * 2 * drag.translation.width))
                    }
                    .onEnded { _ in withAnimation(.snappy(duration: 0.2)) { start = nil } })
                .onTapGesture(count: 2) { withAnimation(.snappy) { width = 680 } }
                .help("拖动调整宽度，双击恢复")
                .accessibilityLabel("文字宽度")
                .accessibilityValue("\(Int(width))")
                .accessibilityAdjustableAction { d in width = min(WidthHandles.range.upperBound, max(WidthHandles.range.lowerBound, width + (d == .increment ? 40 : -40))) }
        }
    }
}

private struct SummaryWidthHandle: View {
    @Binding var width: Double
    @State private var start: Double?

    var body: some View {
        Color.clear.frame(width: 14).contentShape(Rectangle())
            .overlay {
                Capsule().fill(Brand.accent.opacity(start == nil ? 0.35 : 0.9)).frame(width: 3, height: start == nil ? 36 : 56)
            }
            .onHover { inside in
                if inside { NSCursor.resizeLeftRight.push() } else { NSCursor.pop() }
            }
            .gesture(DragGesture(minimumDistance: 1, coordinateSpace: .global)
                .onChanged { drag in
                    let base = start ?? width
                    if start == nil { start = base }
                    width = min(720, max(260, base - drag.translation.width))
                }
                .onEnded { _ in start = nil })
            .onTapGesture(count: 2) { width = 360 }
            .help("拖动调整总结宽度，双击恢复")
            .accessibilityLabel("总结宽度")
            .accessibilityValue("\(Int(width))")
            .accessibilityAdjustableAction { direction in
                width = min(720, max(260, width + (direction == .increment ? 40 : -40)))
            }
    }
}

/// 全部 / 进行中 / 失败 / 完成, shown only when there is more than one kind to tell apart.
private struct StatusFilter: View {
    @ObservedObject var model: WorkspaceModel
    var body: some View {
        let kinds = WorkspaceModel.Filter.allCases.filter { f in f == .all || model.tasks.contains(where: f.matches) }
        if kinds.count > 2 || model.filter != .all {
            HStack(spacing: 4) {
                ForEach(kinds, id: \.self) { f in
                    let on = model.filter == f
                    Button { withAnimation(.snappy(duration: 0.2)) { model.filter = f } } label: {
                        Text(f.title).font(.callout.weight(on ? .semibold : .regular)).foregroundStyle(on ? Brand.accent : .secondary)
                            .padding(.horizontal, 10).padding(.vertical, 4)
                            .background(Capsule().fill(Brand.accent.opacity(on ? 0.14 : 0)))
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain).accessibilityAddTraits(on ? .isSelected : [])
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12).padding(.vertical, 6)
        }
    }
}

private struct SpeakerRename: View {
    let names: [String]
    let apply: ([String: String]) -> Void
    @State private var edits: [String: String] = [:]
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(names, id: \.self) { name in
                TextField(name, text: Binding(get: { edits[name] ?? name }, set: { edits[name] = $0 }))
                    .textFieldStyle(.roundedBorder).frame(width: 200)
            }
            HStack { Spacer(); Button("完成") { apply(edits) }.keyboardShortcut(.defaultAction).disabled(edits.allSatisfy { $0.value == $0.key || $0.value.isEmpty }) }
        }
        .padding(16)
    }
}

private struct Resummarize: View {
    let run: (String) -> Void
    @State private var prompts = Summarizer.prompts()
    @State private var prompt = ""
    var body: some View {
        VStack(alignment: .trailing, spacing: 10) {
            PromptProfileEditor(prompts: $prompts, text: $prompt).frame(width: 380)
            Button("重新总结") {
                prompts.update(prompts.selected, prompt: prompt)
                Summarizer.savePrompts(prompts)
                run(prompts.current.prompt)
            }
            .keyboardShortcut(.defaultAction).buttonStyle(.borderedProminent)
            .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(16)
        .onAppear { prompt = prompts.current.prompt }
    }
}
