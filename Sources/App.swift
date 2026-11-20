import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var workspace: WorkspaceModel?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let workspace else { return .terminateNow }
        guard !workspace.editingLocked else { return .terminateCancel }
        guard workspace.hasUnsavedEdits else { return .terminateNow }
        // Reply after the alert has closed and, if requested, the save has completed.
        Task { @MainActor in
            workspace.resolveEdits { sender.reply(toApplicationShouldTerminate: $0) }
        }
        return .terminateLater
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // `-Appearance dark|light` on the command line lands in the same defaults key, so tests can force a theme.
        Theme.apply(UserDefaults.standard.string(forKey: Theme.key) ?? "")
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { sender.windows.first(where: { $0.canBecomeMain })?.makeKeyAndOrderFront(nil) }
        sender.activate(ignoringOtherApps: true)
        return true
    }
}

@main
struct TranscriptionApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var workspace = WorkspaceModel()
    @AppStorage("localServer") private var serverOn = true

    init() {
        AppPaths.prepareDataDirectory()
        Notifier.authorize()
        if UserDefaults.standard.object(forKey: "localServer") as? Bool ?? true { try? LocalServer.shared.start() }
    }

    var body: some Scene {
        Window("语音转写", id: "main") {
            ContentView(workspace: workspace)
                .environmentObject(workspace)
                .onAppear { delegate.workspace = workspace }
                .onOpenURL { url in workspace.select(.new) { workspace.stage([url]) } }
        }
        .windowToolbarStyle(.unified)
        .defaultSize(width: 1100, height: 760)
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("新建转写") { workspace.select(.new) }.keyboardShortcut("n")
                Button("选择录音…") { workspace.select(.new) { workspace.showImporter = true } }.keyboardShortcut("o")
            }
        }
        Settings {
            SettingsView()
        }
    }
}

/// 跟随系统 / 浅色 / 深色, stored under `Appearance`.
enum Theme {
    static let key = "Appearance"
    @MainActor static func apply(_ value: String) {
        NSApp.appearance = value == "dark" ? NSAppearance(named: .darkAqua) : value == "light" ? NSAppearance(named: .aqua) : nil
    }
}
