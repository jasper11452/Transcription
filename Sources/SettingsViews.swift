import SwiftUI

// MARK: - Settings: one window, every service and option in it

struct SettingsView: View {
    @AppStorage("settingsTab") private var tab = "service"

    var body: some View {
        TabView(selection: $tab) {
            AccountSettings().tabItem { Label("账号", systemImage: "person.crop.circle") }.tag("account")
            TranscriptionSettings().tabItem { Label("转写", systemImage: "waveform") }.tag("service")
            SummarySettings().tabItem { Label("LLM", systemImage: "sparkles") }.tag("summary")
            GlossarySettings().tabItem { Label("热词", systemImage: "text.book.closed") }.tag("glossary")
            ModelSettings().tabItem { Label("本机模型", systemImage: "arrow.down.circle") }.tag("models")
            AdvancedSettings().tabItem { Label("高级", systemImage: "gearshape.2") }.tag("advanced")
        }
        .frame(width: 600, height: 520)
        // Nothing is focused until the person clicks: a pre-selected field invites accidental overwrites.
        .task(id: tab) { await MainActor.run { NSApp.keyWindow?.makeFirstResponder(nil) } }
        .onAppear { if !["account", "service", "summary", "glossary", "models", "advanced"].contains(tab) { tab = "service" } }
    }
}

// MARK: Accounts

struct AccountSettings: View {
    @State private var openAI: OpenAIAccountToken?
    @State private var busy = false
    @State private var error: String?
    @State private var loginTask: Task<Void, Never>?
    @State private var loginToken: UUID?

    var body: some View {
        Form {
            Section("豆包") {
                DoubaoAccountControls(onChanged: {})
                Text("登录豆包后直接使用云端转写，不需要填写 API 密钥。音频会发送到豆包服务处理。")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Section("OpenAI") {
                LabeledContent("ChatGPT 账号") {
                    if openAI != nil {
                        HStack {
                            Label("已登录", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                            Button("退出登录", role: .destructive) { AccountCredentialStore.deleteOpenAI(); openAI = nil }
                        }
                    } else {
                        Button("使用 ChatGPT 登录") { signIn() }.disabled(busy)
                    }
                }
                Text("使用浏览器完成 OpenAI 官方授权。凭证只保存在这台 Mac 的钥匙串中，不写入配置文件。")
                    .font(.callout).foregroundStyle(.secondary)
                if let expiry = openAI?.expiresAt { Text("凭证有效期至：\(expiry.formatted(date: .abbreviated, time: .shortened))").font(.callout).foregroundStyle(.secondary) }
            }
            Section("DeepSeek") {
                Text("DeepSeek 目前没有面向第三方桌面应用的官方账号 OAuth。网页登录会话不能直接作为 API 凭证。")
                    .font(.callout).foregroundStyle(.secondary)
                Link("打开 DeepSeek API 控制台", destination: URL(string: "https://platform.deepseek.com/api_keys")!)
            }
            if busy {
                HStack {
                    ProgressView("正在等待浏览器授权…")
                    Spacer()
                    Button("取消") { loginTask?.cancel(); loginTask = nil; loginToken = nil; busy = false }
                }
            }
            if let error { Text(error).foregroundStyle(.red) }
        }
        .formStyle(.grouped)
        .onAppear { openAI = AccountCredentialStore.loadOpenAI() }
        .onDisappear { loginTask?.cancel() }
    }

    private func signIn() {
        loginTask?.cancel()
        busy = true
        error = nil
        let token = UUID()
        loginToken = token
        loginTask = Task { @MainActor in
            defer {
                if loginToken == token {
                    loginTask = nil
                    loginToken = nil
                    busy = false
                }
            }
            do { openAI = try await OpenAIAccountAuth.signIn() }
            catch is CancellationError { }
            catch let failure { error = failure.localizedDescription }
        }
    }
}

/// Opens Settings from anywhere, on the tab that answers the question at hand.
/// `showSettingsWindow:` stopped answering on macOS 14, so the SwiftUI action is captured once and reused.
@MainActor func openSettings(tab: String) {
    UserDefaults.standard.set(tab, forKey: "settingsTab")
    SettingsOpener.action?()
}

struct SettingsOpener: View {
    @MainActor static var action: (() -> Void)?
    @Environment(\.openSettings) private var open
    var body: some View { Color.clear.frame(width: 0, height: 0).onAppear { Self.action = { open(); NSApp.activate(ignoringOtherApps: true) } } }
}

// MARK: Pieces

/// A key in `config.env`: never shown in full, replaced or cleared explicitly.
private struct KeyRow: View {
    let title: String
    let env: String
    @State private var saved: String?
    @State private var draft = ""
    @State private var editing = false

    var body: some View {
        LabeledContent(title) {
            if let saved, !editing {
                HStack(spacing: 8) {
                    Text("····" + saved.suffix(4)).monospaced().foregroundStyle(.secondary)
                    Button("更换") { editing = true }
                    Button("清除") { ConfigEnv.save(env, ""); self.saved = nil }
                }
            } else {
                HStack(spacing: 8) {
                    SecureField("", text: $draft, prompt: Text("粘贴密钥")).frame(width: 220).onSubmit(save)
                    Button("保存", action: save).disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
                    if editing { Button("取消") { editing = false; draft = "" } }
                }
            }
        }
        .onAppear { saved = ConfigEnv.read(env) }
    }

    private func save() {
        let value = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        ConfigEnv.save(env, value)
        saved = value; draft = ""; editing = false
    }
}

/// A plain `config.env` value with a default shown as the placeholder; empty means default.
private struct ConfigField: View {
    let title: String
    let env: String
    let placeholder: String
    var url = false
    @State private var value = ""

    /// A base URL is a single endpoint: no commas, and it needs a scheme.
    private var problem: String? {
        guard url, !value.isEmpty else { return nil }
        if value.contains(",") || value.contains("，") { return "只填一个地址，不能有逗号" }
        if env == Service.local.baseEnv, !Service.isLoopback(value) { return "只能是本机地址，如 http://127.0.0.1:18475/v1" }
        return URL(string: value)?.scheme?.hasPrefix("http") == true ? nil : "以 https:// 开头"
    }

    var body: some View {
        TextField(title, text: $value, prompt: Text(placeholder))
            .onAppear { value = ConfigEnv.read(env) ?? "" }
            .onChange(of: value) {
                guard problem == nil else { return }
                ConfigEnv.save(env, value)
                if env == Service.local.baseEnv { LocalServer.shared.restartSoon() }
            }
        if let problem { Text(problem).font(.callout).foregroundStyle(.red) }
    }
}

/// Key, base URL and model of one service, each on its own row.
private struct ServiceFields: View {
    let service: Service
    /// Tucks the base URL away: most people never change it.
    var foldBase = false
    var onModelChanged: (() -> Void)? = nil
    @State private var model = ""
    @State private var picking = false

    var body: some View {
        if let env = service.keyEnv { KeyRow(title: service.id == "local" ? "访问密钥" : "API 密钥", env: env) }
        if !foldBase { ConfigField(title: "Base URL", env: service.baseEnv, placeholder: service.defaultBase, url: true) }
        LabeledContent("模型") {
            HStack(spacing: 8) {
                TextField("", text: $model, prompt: Text(service.defaultModel)).labelsHidden()
                    .onChange(of: model) { ConfigEnv.save(service.modelEnv, model); onModelChanged?() }
                if service.id != "bcut" {
                    Button("选择…") { picking = true }
                        .popover(isPresented: $picking, arrowEdge: .bottom) { ModelPicker(service: service, selection: $model, close: { picking = false }) }
                }
            }
        }
        .onAppear { model = ConfigEnv.read(service.modelEnv) ?? "" }
        if foldBase {
            DisclosureGroup("自定义地址") { ConfigField(title: "Base URL", env: service.baseEnv, placeholder: service.defaultBase, url: true) }
        }
    }
}

private struct ServiceHeader: View {
    let service: Service
    var body: some View {
        HStack {
            Text(service.name)
            Spacer()
            if let link = service.keyURL.flatMap(URL.init(string:)) { Link("获取密钥", destination: link).font(.callout) }
        }
    }
}

// MARK: Transcription

struct TranscriptionSettings: View {
    @AppStorage("engineChoice") private var choice = "local"
    @AppStorage("wsLanguage") private var language = ""
    @AppStorage("localModel") private var localModel = "standard"
    @AppStorage("settingsTab") private var tab = "service"
    @ObservedObject private var store = ModelStore.shared
    @State private var authVersion = 0

    private var service: Service? { Service.cloud.first { $0.id == choice } }

    var body: some View {
        Form {
            Section {
                EngineRow(title: "本机 · 离线", status: LocalModels.ready(localModel == "lite" ? LocalModels.lite : LocalModels.standard) ? "已就绪" : "需下载", selected: choice == "local") { choice = "local" }
                ForEach(Service.cloud) { s in
                    let status = s.id == "doubao" ? (s.readyForTranscription ? "已登录" : "未登录") : s.keyEnv == nil ? "免密钥" : s.configured ? "已配置" : "未填密钥"
                    EngineRow(title: s.name, status: status, selected: choice == s.id) { choice = s.id }
                }
                Picker("语言", selection: $language) {
                    ForEach(workspaceLanguages, id: \.0) { Text($0.1).tag($0.0) }
                }
            } header: { Text("引擎") }

            if choice == "local" {
                Section("本机") {
                    Picker("识别模型", selection: $localModel) {
                        Text("标准 · 1.7B").tag("standard")
                        Text("轻量 · 0.6B" + (LocalModels.ready(LocalModels.lite) ? "" : "（未下载）")).tag("lite")
                    }
                    if !LocalModels.ready(localModel == "lite" ? LocalModels.lite : LocalModels.standard) {
                        LabeledContent("状态") { Button("下载模型…") { tab = "models" } }
                    }
                }
            } else if choice == "doubao" {
                Section("豆包账号") {
                    DoubaoAccountControls { authVersion += 1 }
                    Text("豆包网页版登录是非官方云端接口，页面或服务协议变化时可能需要重新登录。")
                        .font(.callout).foregroundStyle(.secondary)
                }
            } else if let service, service.keyEnv != nil {
                Section { ServiceFields(service: service, foldBase: true) } header: { ServiceHeader(service: service) }
            }
        }
        .formStyle(.grouped)
        .animation(.snappy(duration: 0.2), value: choice)
        .id(authVersion)
        .task { await store.refresh() }
    }
}

// MARK: Local models: grouped by what they let you do, not by what they're made of

struct ModelSettings: View {
    @AppStorage("localModel") private var localModel = "standard"
    @ObservedObject private var store = ModelStore.shared

    var body: some View {
        Form {
            Section("语音识别") {
                ModelSetRow(title: "标准 · 1.7B", specs: LocalModels.standard, inUse: localModel == "standard")
                ModelSetRow(title: "轻量 · 0.6B", specs: LocalModels.lite, inUse: localModel == "lite")
            }
            Section("附加功能") {
                ModelSetRow(title: "区分说话人", specs: LocalModels.speakers, inUse: false)
            }
            if store.isDownloading || store.anyProgress { Section { DownloadProgress(store: store) } }
            Section {
                Picker("下载来源", selection: $store.source) { ForEach(DownloadSource.allCases) { Text($0.title).tag($0) } }
                    .disabled(store.isDownloading)
                LabeledContent("存放位置") {
                    Button("在访达中显示") { NSWorkspace.shared.activateFileViewerSelecting([AppPaths.layout.modelCache]) }.buttonStyle(.link)
                }
            }
        }
        .formStyle(.grouped)
        .task { await store.refresh() }
    }
}

/// What each local choice needs on disk. Alignment and voice detection ride along with either recognizer.
enum LocalModels {
    private static func specs(_ repos: [String]) -> [ModelSpec] { modelCatalog.filter { repos.contains($0.repo) } }
    static let standard = specs([LocalModel.asr, LocalModel.aligner, LocalModel.vad])
    static let lite = specs([LocalModel.asrLite, LocalModel.aligner, LocalModel.vad])
    static let speakers = specs([LocalModel.diar])
    @MainActor static func ready(_ specs: [ModelSpec]) -> Bool { specs.allSatisfy { ModelStore.shared.isReady($0.repo) } }
}

private struct EngineRow: View {
    let title: String, status: String, selected: Bool
    let pick: () -> Void
    var body: some View {
        Button(action: pick) {
            HStack {
                Image(systemName: "checkmark").font(.callout.weight(.semibold)).foregroundStyle(Brand.accent).opacity(selected ? 1 : 0).frame(width: 16)
                Text(title)
                Spacer()
                Text(status).foregroundStyle(.secondary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// One capability on disk: its size once downloaded, progress while downloading, otherwise a download button.
private struct ModelSetRow: View {
    @ObservedObject private var store = ModelStore.shared
    let title: String, specs: [ModelSpec], inUse: Bool

    private var total: Int64 { specs.reduce(0) { $0 + store.size($1) } }
    private var missing: Int64 { store.missingBytes(of: specs) }
    private var failure: String? { specs.lazy.compactMap { if case .failed(let m) = store.state($0.repo) { return m } else { return nil } }.first }
    private var busy: Bool { specs.contains { [.downloading, .paused].contains(store.state($0.repo)) } }

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(title)
                    if inUse { Text("使用中").font(.caption.weight(.medium)).foregroundStyle(Brand.accent)
                        .padding(.horizontal, 6).padding(.vertical, 1).background(Capsule().fill(Brand.accent.opacity(0.12))) }
                }
                if let failure { Text(failure).font(.callout).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
            }
            Spacer()
            if LocalModels.ready(specs) { Text(bytes(total)).foregroundStyle(.secondary).monospacedDigit() }
            else if busy { Text("\(Int(Double(total - missing) / Double(max(total, 1)) * 100))%").foregroundStyle(.secondary).monospacedDigit() }
            else { Button((failure == nil ? "下载 " : "重试 ") + bytes(missing)) { store.download(specs.filter { !store.isReady($0.repo) }) }.disabled(store.isDownloading) }
        }
    }
}

private struct DownloadProgress: View {
    @ObservedObject var store: ModelStore
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ProgressView(value: Double(store.batchDone), total: Double(max(store.batchTotal, 1)))
            HStack {
                Text(store.preparing ? "正在选择下载来源…" : [store.bytesText, store.speedText, store.remainingText].compactMap { $0 }.joined(separator: " · "))
                    .monospacedDigit()
                Spacer()
                if store.isDownloading { Button("暂停") { store.pause() }.buttonStyle(.link).disabled(store.preparing) }
                else { Button("继续") { store.resume() }.buttonStyle(.link) }
            }
            .font(.callout).foregroundStyle(.secondary)
        }
    }
}

private func bytes(_ n: Int64) -> String { ByteCountFormatter.string(fromByteCount: n, countStyle: .file) }

// MARK: Summary

struct SummarySettings: View {
    @AppStorage("summaryProvider") private var provider = "openrouter"
    @State private var prompts = Summarizer.prompts()
    @State private var prompt = ""
    @State private var reasoningRefresh = 0

    private var dirty: Bool { prompt != prompts.current.prompt }

    var body: some View {
        Form {
            Section("服务") {
                Picker("服务", selection: $provider) {
                    Text("OpenRouter · API Key").tag("openrouter")
                    Text("OpenAI · ChatGPT 账号").tag("openai")
                }
                if provider == "openai" {
                    HStack {
                        Label(AccountCredentialStore.loadOpenAI() == nil ? "未登录" : "已登录", systemImage: AccountCredentialStore.loadOpenAI() == nil ? "person.crop.circle.badge.xmark" : "checkmark.circle.fill")
                        Spacer()
                        Button("打开账号设置") { openSettings(tab: "account") }
                    }
                }
                ServiceFields(service: .summary) { reasoningRefresh += 1 }
                ReasoningSettings().id(reasoningRefresh)
            }
            Section {
                PromptProfileEditor(prompts: $prompts, text: $prompt, height: 160)
            } header: {
                HStack {
                    Text("总结要求")
                    Spacer()
                    Button("保存", action: save).disabled(!dirty)
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { prompts = Summarizer.prompts(); prompt = prompts.current.prompt }
    }

    private func save() {
        prompts.update(prompts.selected, prompt: prompt)
        Summarizer.savePrompts(prompts)
        prompt = prompts.current.prompt
    }
}

private struct ReasoningSettings: View {
    @State private var model = Service.summary.model
    @State private var effort = ""
    @State private var supportsReasoning = true

    private var options: [LLMReasoning.Option] { LLMReasoning.options(model: model, supportsReasoning: supportsReasoning) }

    var body: some View {
        Picker("思考等级", selection: Binding(get: { effort }, set: { value in
            effort = value
            LLMReasoning.save(value, base: Service.summary.base, model: model)
        })) {
            ForEach(options) { option in Text(option.title).tag(option.id) }
        }
        .onAppear {
            model = Service.summary.model
            effort = LLMReasoning.read(base: Service.summary.base, model: model)
            Task {
                if let models = try? await Summarizer.models(key: Service.summary.key, base: Service.summary.modelsBase),
                   let info = models.first(where: { $0.id == model }) {
                    await MainActor.run { supportsReasoning = info.reasoning }
                }
            }
        }
        .help("按模型保存，服务默认会省略思考参数")
    }
}

/// Profile picker with a small menu, plus the editor. Switching profiles saves unsaved edits first.
struct PromptProfileEditor: View {
    @Binding var prompts: SummaryPrompts
    @Binding var text: String
    var height: CGFloat = 200
    @State private var renaming: String?
    @FocusState private var nameFocus: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                if renaming != nil {
                    TextField("方案名称", text: Binding(get: { renaming ?? "" }, set: { renaming = $0 }))
                        .textFieldStyle(.roundedBorder).focused($nameFocus).onSubmit(finishRename)
                        .onExitCommand { renaming = nil }
                    Button("完成", action: finishRename)
                } else {
                    Picker("方案", selection: Binding(get: { prompts.selected }, set: switchTo)) {
                        ForEach(prompts.names, id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                    Menu {
                        Button("新建方案") { create() }
                        Button("重命名") { renaming = prompts.selected }.disabled(prompts.selected == SummaryPrompts.defaultName)
                        Button("删除", role: .destructive) { delete() }.disabled(prompts.selected == SummaryPrompts.defaultName)
                        if prompts.selected == SummaryPrompts.defaultName {
                            Divider()
                            Button("恢复默认") { prompts.resetDefault(); text = prompts.current.prompt; Summarizer.savePrompts(prompts) }
                        }
                    } label: { Image(systemName: "ellipsis.circle") }
                    .menuStyle(.borderlessButton).fixedSize()
                    .accessibilityLabel("方案菜单")
                }
                Spacer(minLength: 0)
            }
            TextEditor(text: $text).font(.system(size: 13)).frame(height: height).scrollContentBackground(.hidden)
                .padding(8).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Color.primary.opacity(0.05)))
        }
    }

    private func switchTo(_ name: String) {
        guard name != prompts.selected else { return }
        if text != prompts.current.prompt { prompts.update(prompts.selected, prompt: text) }
        prompts.select(name)
        Summarizer.savePrompts(prompts)
        text = prompts.current.prompt
    }

    private func create() {
        let source = text
        if source != prompts.current.prompt { prompts.update(prompts.selected, prompt: source) }
        prompts.add(prompts.freshName(), prompt: source)
        Summarizer.savePrompts(prompts)
        renaming = prompts.selected
        nameFocus = true
    }

    private func finishRename() {
        if let new = renaming, new.trimmingCharacters(in: .whitespacesAndNewlines) != prompts.selected {
            prompts.rename(prompts.selected, to: new); Summarizer.savePrompts(prompts)
        }
        renaming = nil
    }

    private func delete() {
        prompts.delete(prompts.selected)
        Summarizer.savePrompts(prompts)
        text = prompts.current.prompt
    }
}

/// The endpoint's model list, filterable, with what matters for choosing: context, thinking, price.
private struct ModelPicker: View {
    let service: Service
    @Binding var selection: String
    let close: () -> Void
    @State private var all: [Summarizer.ModelInfo] = []
    @State private var query = ""
    @State private var error: String?
    @State private var loading = true

    private var shown: [Summarizer.ModelInfo] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return q.isEmpty ? all : all.filter { $0.id.lowercased().contains(q) || $0.name.lowercased().contains(q) }
    }

    var body: some View {
        VStack(spacing: 0) {
            TextField("搜索模型", text: $query).textFieldStyle(.roundedBorder).padding(10)
            Divider()
            Group {
                if loading { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                else if let error { Text(error).foregroundStyle(.secondary).frame(maxWidth: .infinity, maxHeight: .infinity).padding() }
                else {
                    List(shown) { m in
                        Button { selection = m.id; close() } label: {
                            HStack(spacing: 8) {
                                Text(m.id).lineLimit(1).truncationMode(.middle)
                                if m.audio { Text("音频").font(.caption2).padding(.horizontal, 5).padding(.vertical, 1).background(Capsule().fill(Brand.accent.opacity(0.18))) }
                                if m.reasoning { Text("思考").font(.caption2).padding(.horizontal, 5).padding(.vertical, 1).background(Capsule().fill(.quaternary)) }
                                Spacer(minLength: 8)
                                Text(detail(m)).font(.callout).monospacedDigit().foregroundStyle(.secondary)
                                if m.id == selection { Image(systemName: "checkmark").foregroundStyle(Brand.accent) }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                    .listStyle(.plain)
                    .overlay { if shown.isEmpty { Text("没有匹配的模型").foregroundStyle(.secondary) } }
                }
            }
        }
        .frame(width: 440, height: 380)
        .task {
            do { all = try await Summarizer.models(key: service.key, base: service.modelsBase) }
            catch { self.error = error.localizedDescription }
            loading = false
        }
    }

    private func detail(_ m: Summarizer.ModelInfo) -> String {
        var parts: [String] = []
        if let c = m.context { parts.append(c >= 1_000_000 ? "\(c / 1_000_000)M" : "\(c / 1000)K") }
        if let p = m.pricePerMillion { parts.append(p == 0 ? "免费" : String(format: "$%.2f", p)) }
        return parts.joined(separator: " · ")
    }
}

// MARK: Hot words

/// Hot words by group, plus corrections. Saves as you go, to the same file the earlier Transcript install reads.
struct GlossarySettings: View {
    @State private var glossary = Glossary()
    @State private var drafts: [UUID: String] = [:]
    @State private var loaded = false

    var body: some View {
        Form {
            ForEach($glossary.groups) { $group in
                Section {
                    WordCloud(words: $group.words)
                    TextField("", text: Binding(get: { drafts[group.id] ?? "" }, set: { drafts[group.id] = $0 }), prompt: Text("添加热词"))
                        .onSubmit { add(to: group.id) }
                } header: {
                    HStack {
                        TextField("", text: $group.name, prompt: Text("未命名分组")).textFieldStyle(.plain).font(.headline)
                        Spacer()
                        Button { glossary.groups.removeAll { $0.id == group.id } } label: { Image(systemName: "trash") }
                            .buttonStyle(.borderless).foregroundStyle(.secondary).help("删除分组").accessibilityLabel("删除分组 \(group.name)")
                    }
                }
            }
            Section {
                Button { glossary.groups.append(HotWordGroup(name: "新分组", words: [])) } label: { Label("新建分组", systemImage: "plus") }
                    .buttonStyle(.borderless)
            }
            Section {
                ForEach($glossary.corrections) { $rule in
                    HStack(spacing: 10) {
                        TextField("", text: $rule.wrong, prompt: Text("听错的写法")).labelsHidden()
                        Image(systemName: "arrow.right").foregroundStyle(.tertiary)
                        TextField("", text: $rule.right, prompt: Text("正确写法")).labelsHidden()
                        Button { glossary.corrections.removeAll { $0.id == rule.id } } label: { Image(systemName: "minus.circle") }
                            .buttonStyle(.borderless).foregroundStyle(.secondary).accessibilityLabel("删除这条纠错")
                    }
                }
                Button { glossary.corrections.append(Correction(wrong: "", right: "")) } label: { Label("添加纠错", systemImage: "plus") }
                    .buttonStyle(.borderless)
            } header: { Text("纠错") }
        }
        .formStyle(.grouped)
        .onAppear { glossary = Glossary(file: AppPaths.layout.glossary); loaded = true }
        .onChange(of: glossary.text) { if loaded { save() } }
    }

    private func add(to id: UUID) {
        let words = (drafts[id] ?? "").split(whereSeparator: { "，,、;；\n".contains($0) }).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        guard let i = glossary.groups.firstIndex(where: { $0.id == id }) else { return }
        for w in words where !glossary.groups[i].words.contains(w) { glossary.groups[i].words.append(w) }
        drafts[id] = ""
    }

    private func save() {
        let url = AppPaths.layout.glossary
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? glossary.text.write(to: url, atomically: true, encoding: .utf8)
    }
}

/// Words as removable tokens that wrap like text.
private struct WordCloud: View {
    @Binding var words: [String]

    var body: some View {
        if words.isEmpty {
            Text("还没有热词").foregroundStyle(.tertiary)
        } else {
            FlowLayout(spacing: 6) {
                ForEach(words, id: \.self) { word in
                    HStack(spacing: 4) {
                        Text(word)
                        Button { words.removeAll { $0 == word } } label: { Image(systemName: "xmark").font(.system(size: 9, weight: .bold)) }
                            .buttonStyle(.plain).foregroundStyle(.secondary).accessibilityLabel("删除 \(word)")
                    }
                    .padding(.leading, 9).padding(.trailing, 7).padding(.vertical, 4)
                    .background(Capsule().fill(Color.primary.opacity(0.06)))
                }
            }
            .padding(.vertical, 2)
        }
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews)
        return CGSize(width: proposal.width ?? rows.map(\.width).max() ?? 0, height: rows.last.map { $0.y + $0.height } ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for row in arrange(width: bounds.width, subviews) {
            var x = bounds.minX
            for i in row.items {
                let size = subviews[i].sizeThatFits(.unspecified)
                subviews[i].place(at: CGPoint(x: x, y: bounds.minY + row.y), proposal: .init(size))
                x += size.width + spacing
            }
        }
    }

    private struct Row { var items: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0; var y: CGFloat = 0 }

    private func arrange(width: CGFloat, _ subviews: Subviews) -> [Row] {
        var rows: [Row] = [Row()]
        for i in subviews.indices {
            let size = subviews[i].sizeThatFits(.unspecified)
            if !rows[rows.count - 1].items.isEmpty, rows[rows.count - 1].width + spacing + size.width > width {
                let y = rows[rows.count - 1].y + rows[rows.count - 1].height + spacing
                rows.append(Row(y: y))
            }
            var row = rows[rows.count - 1]
            row.width += (row.items.isEmpty ? 0 : spacing) + size.width
            row.height = max(row.height, size.height)
            row.items.append(i)
            rows[rows.count - 1] = row
        }
        return rows
    }
}

// MARK: Advanced

struct AdvancedSettings: View {
    @AppStorage("localServer") private var serverOn = true
    @AppStorage(Theme.key) private var appearance = ""

    var body: some View {
        Form {
            Section("外观") {
                Picker("主题", selection: $appearance) {
                    Text("跟随系统").tag("")
                    Text("浅色").tag("light")
                    Text("深色").tag("dark")
                }
                .pickerStyle(.segmented)
                .onChange(of: appearance) { Theme.apply(appearance) }
            }
            Section("OpenAI 兼容本地服务") {
                Toggle("允许其他应用调用本机转写", isOn: Binding(get: { serverOn }, set: { on in
                    serverOn = on
                    if on { try? LocalServer.shared.start() } else { LocalServer.shared.stop() }
                }))
                if serverOn {
                    ServiceFields(service: .local)
                    TimelineView(.periodic(from: .now, by: 1)) { _ in
                        if let failure = LocalServer.shared.failure { Text(failure).font(.callout).foregroundStyle(.red) }
                    }
                }
            }
            Section("文件位置") {
                LabeledContent("配置") { PathButton(url: AppPaths.layout.config) }
                LabeledContent("热词") { PathButton(url: AppPaths.layout.glossary) }
            }
        }
        .formStyle(.grouped)
    }
}

private struct PathButton: View {
    let url: URL
    var body: some View {
        Button((url.path as NSString).abbreviatingWithTildeInPath) { NSWorkspace.shared.activateFileViewerSelecting([url]) }
            .buttonStyle(.link).lineLimit(1).truncationMode(.middle)
    }
}
