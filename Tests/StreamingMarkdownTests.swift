import AppKit
import SwiftUI

// Standalone regression test: compile with the production MarkdownView.swift.
// Only its unrelated color/time dependencies are supplied here.
enum Brand {
    static let accent = Color(nsColor: NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(red: 0.55, green: 0.60, blue: 1.0, alpha: 1)
            : NSColor(red: 0.33, green: 0.39, blue: 0.82, alpha: 1)
    })
}
func clock(_ time: Double) -> String { String(format: "%d:%02d", Int(time) / 60, Int(time) % 60) }

@MainActor
private final class StreamState: ObservableObject {
    @Published var source = "# 总结"
    @Published var live = true
}

private struct StreamFixture: View {
    @ObservedObject var state: StreamState
    let height: CGFloat
    var body: some View {
        StreamingMarkdown(source: state.source, live: state.live)
            .padding(32)
            .frame(width: 720, height: height, alignment: .topLeading)
            .background(Color(nsColor: .textBackgroundColor))
    }
}

@main
@MainActor
private final class StreamingMarkdownTests: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var host: NSHostingView<StreamFixture>!
    private let state = StreamState()

    static func main() {
        let app = NSApplication.shared
        let delegate = StreamingMarkdownTests()
        app.setActivationPolicy(.accessory)
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let height: CGFloat = CommandLine.arguments.count > 1 ? 1200 : 320
        host = NSHostingView(rootView: StreamFixture(state: state, height: height))
        window = NSWindow(contentRect: NSRect(x: 20, y: 20, width: 720, height: height),
                          styleMask: [.titled], backing: .buffered, defer: false)
        window.title = "Streaming Markdown regression test"
        window.contentView = host
        window.orderBack(nil)
        AXUIElementSetAttributeValue(AXUIElementCreateApplication(getpid()), "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
        Task { await verify() }
    }

    private func text(in element: Any, depth: Int = 0) -> String {
        guard depth < 30, let node = element as? NSObject else { return "" }
        func attribute(_ name: String) -> Any? {
            let selector = NSSelectorFromString(name)
            guard node.responds(to: selector) else { return nil }
            return node.perform(selector)?.takeUnretainedValue()
        }
        let own = [attribute("accessibilityValue") as? String, attribute("accessibilityLabel") as? String].compactMap { $0 }
        let children = (attribute("accessibilityChildren") as? [Any] ?? []).map { text(in: $0, depth: depth + 1) }
        return (own + children).joined(separator: "\n")
    }

    private func expectVisible(_ expected: String, name: String) async {
        try? await Task.sleep(for: .milliseconds(500))
        host.layoutSubtreeIfNeeded()
        let visible = text(in: window as Any)
        guard visible.contains(expected) else {
            fputs("FAIL \(name): expected \(expected), got \(visible)\n", stderr)
            exit(1)
        }
        print("PASS \(name)")
    }

    private func verify() async {
        await expectVisible("总结", name: "initial streaming snapshot")
        state.source += "\n\n第一段已经到达。"
        await expectVisible("第一段已经到达。", name: "new content appears before completion")
        state.source += "\n\n第二段也立即显示。"
        await expectVisible("第二段也立即显示。", name: "subsequent content appears while live stays true")
        state.live = false
        await expectVisible("第二段也立即显示。", name: "completion preserves the final text")
        state.source = "# 重新生成\n\n这是新请求的内容。"
        state.live = true
        await expectVisible("这是新请求的内容。", name: "restart replaces previous content")
        state.live = false
        if CommandLine.arguments.count > 1 { await snapshots(to: CommandLine.arguments[1]) }
        window.close()
        NSApplication.shared.terminate(nil)
    }

    private func snapshots(to directory: String) async {
        try? FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
        let hierarchy = """
        # 总结
        本周完成总结的流式显示，接下来验收排版与稳定性。

        - **文稿与总结**
          - **已完成**
            - 模型返回的文字实时显示，保留完整内容。
            - 等待期间显示状态和已等待的时间。
          - **下周计划**
            - 检查长文稿、多级列表和任务切换。
        - **服务与稳定性**
          - **检查结果**
            - 请求已按流式返回，旧请求不会覆盖新结果。

        ## 待办事项
        - [ ] 开发组：明天完成完整验收。
        - [x] 已完成编译与流式回归测试。

        ### 关键决策
        1. 收到内容后立即显示。
           1. 保留 Markdown 的真实结构。

        #### 实施细节
        标题、模块和小类各有明确层级。

        ##### 验证范围
        同时覆盖浅色与深色模式。

        ###### 补充说明
        正文保持清晰可读。
        """
        let blocks = """
        # 智能章节
        [00:23] **本周进展**：梳理总结服务与显示流程。

        [02:45] **后续计划**：明天验收长文稿与嵌套列表。

        ## 关键决策
        > 所有层级都应清楚呈现，颜色用于帮助阅读。
        >
        > > 对重点结论保留清楚的引用关系。

        | 事项 | 负责人 | 状态 |
        | :--- | :--- | :--- |
        | 流式显示 | 开发组 | 已完成 |
        | 排版验收 | 测试组 | 进行中 |

        ### 补充材料
        阅读 [验收说明](https://example.com)，核对 `stream: true`。

        ```swift
        summary.content += delta
        ```
        """
        for (name, source) in [("hierarchy", hierarchy), ("blocks", blocks)] {
            state.source = source
            for (mode, appearance) in [("light", NSAppearance.Name.aqua), ("dark", NSAppearance.Name.darkAqua)] {
                window.appearance = NSAppearance(named: appearance)
                try? await Task.sleep(for: .milliseconds(300))
                host.layoutSubtreeIfNeeded()
                guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { fatalError("No snapshot bitmap") }
                host.cacheDisplay(in: host.bounds, to: bitmap)
                guard let png = bitmap.representation(using: .png, properties: [:]) else { fatalError("No PNG data") }
                try! png.write(to: URL(fileURLWithPath: directory).appendingPathComponent("\(name)-\(mode).png"))
                print("PASS \(name) snapshot in \(mode) appearance")
            }
        }
    }
}