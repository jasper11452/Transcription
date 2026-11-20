import AppKit
import SwiftUI

struct ContentView: View {
    @ObservedObject var workspace: WorkspaceModel
    @ObservedObject private var models = ModelStore.shared
    @State private var welcome = false

    var body: some View {
        WorkspaceView(model: workspace)
            .frame(minWidth: 760, minHeight: 520)
            .background(SettingsOpener())
            .toolbar { if !models.offlineReady || models.isDownloading { ToolbarItem(placement: .primaryAction) { StatusButton() } } }
            .task {
                AppPaths.prepareDataDirectory()
                await ModelStore.shared.refresh()
                await selectFromLaunchArgument()
                let welcomedKey = "welcomed:" + AppPaths.layout.modelCache.path
                if !ModelStore.shared.offlineReady, !UserDefaults.standard.bool(forKey: welcomedKey) {
                    UserDefaults.standard.set(true, forKey: welcomedKey)
                    welcome = true
                }
            }
            .sheet(isPresented: $welcome) {
                WelcomeView(
                    local: { welcome = false; UserDefaults.standard.set("local", forKey: "engineChoice"); ModelStore.shared.downloadRequired(); ModelStore.shared.presenting = true },
                    cloud: { welcome = false; UserDefaults.standard.set("doubao", forKey: "engineChoice"); workspace.mode = "online"; openSettings(tab: "service") },
                    later: { welcome = false })
            }
            .sheet(isPresented: $models.presenting) { ModelsView(store: models, onClose: { models.presenting = false }) }
    }

    /// Test hook: `-Select <task id|latest>` opens a task at launch, so every screen can be captured without clicking.
    private func selectFromLaunchArgument() async {
        guard let value = UserDefaults.standard.string(forKey: "Select") else { return }
        for _ in 0..<20 where workspace.tasks.isEmpty { try? await Task.sleep(for: .milliseconds(150)) }
        if value == "latest", let first = workspace.tasks.first { workspace.select(.task(first.id)) }
        else if let id = Int(value) { workspace.select(.task(id)) }
    }
}

/// Shown only when the local models are missing or downloading. Opens Settings.
struct StatusButton: View {
    @ObservedObject private var models = ModelStore.shared

    var body: some View {
        Button { openSettings(tab: "models") } label: {
            HStack(spacing: 6) {
                if models.isDownloading { ProgressView().controlSize(.mini); Text("正在下载模型").font(.callout) }
                else if models.checked { Label("本机模型未下载", systemImage: "arrow.down.circle").font(.callout) }
            }
        }
        .help(models.offlineReady ? "本机转写已就绪" : "打开设置查看模型")
        .accessibilityLabel(models.offlineReady ? "本机转写已就绪" : "本机模型未就绪")
    }
}

/// First run: two honest options, each with its price.
struct WelcomeView: View {
    let local: () -> Void
    let cloud: () -> Void
    let later: () -> Void

    var body: some View {
        VStack(spacing: 22) {
            WaveformMark(energy: 0.6)
            VStack(spacing: 6) {
                Text("选一种转写方式").font(.title.weight(.bold))
                Text("之后随时可以在设置里换。").foregroundStyle(.secondary)
            }
            HStack(spacing: 14) {
                card("desktopcomputer", "本机", "离线，免费，录音不会离开这台 Mac。", "首次下载 3.7 GB，只需一次。", "下载并使用", primary: true, local)
                card("cloud", "云端", "登录豆包后直接使用。", "音频会上传到豆包处理，也可以改用 API 服务。", "登录豆包", primary: false, cloud)
            }
            Button("稍后再说", action: later).buttonStyle(.plain).foregroundStyle(.secondary)
        }
        .padding(32).frame(width: 600)
    }

    private func card(_ symbol: String, _ title: String, _ line: String, _ cost: String, _ action: String, primary: Bool, _ run: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: symbol).font(.system(size: 22, weight: .light)).foregroundStyle(Brand.accent)
            Text(title).font(.headline)
            Text(line).font(.callout)
            Text(cost).font(.callout).foregroundStyle(.secondary)
            Spacer(minLength: 6)
            Button(action: run) { Text(action).fontWeight(.semibold).frame(maxWidth: .infinity) }
                .glassButton(prominent: primary).controlSize(.large)
        }
        .padding(18).frame(maxWidth: .infinity, minHeight: 210, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 22, style: .continuous).fill(Color.primary.opacity(0.04)))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Color.primary.opacity(0.08)))
    }
}
