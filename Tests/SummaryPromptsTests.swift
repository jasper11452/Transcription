import Foundation

@main
struct SummaryPromptsTests {
    static func check(_ condition: @autoclosure () -> Bool, _ name: String) {
        guard condition() else { fputs("FAIL \(name)\n", stderr); exit(1) }
        print("PASS \(name)")
    }

    static func main() {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("prompts-test-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let file = dir.appendingPathComponent("summary-prompts.json"), legacy = dir.appendingPathComponent("summary-prompt.txt")
        let base = "内置提示词"

        var p = SummaryPrompts.load(file: file, legacy: legacy, defaultPrompt: base)
        check(p.names == ["默认"] && p.current.prompt == base, "no files: only the built-in profile")
        check(!FileManager.default.fileExists(atPath: file.path), "nothing written when there is nothing to migrate")

        try? "  自定义内容  ".write(to: legacy, atomically: true, encoding: .utf8)
        p = SummaryPrompts.load(file: file, legacy: legacy, defaultPrompt: base)
        check(p.names == ["默认", "我的提示词"] && p.selected == "我的提示词" && p.current.prompt == "自定义内容", "legacy prompt imported and selected")
        check(FileManager.default.fileExists(atPath: legacy.path) && FileManager.default.fileExists(atPath: file.path), "legacy file kept, json written")

        try? "改过的旧文件".write(to: legacy, atomically: true, encoding: .utf8)
        check(SummaryPrompts.load(file: file, legacy: legacy, defaultPrompt: base).current.prompt == "自定义内容", "json wins over legacy afterwards")

        check(p.add("会议", prompt: "A") && p.selected == "会议", "add selects the new profile")
        check(!p.add("会议", prompt: "B") && !p.add("  ", prompt: "B"), "duplicate and empty names rejected")
        p.update("会议", prompt: "A2")
        check(p.prompt(named: "会议") == "A2", "update stores text")
        check(p.freshName() == "方案 2", "fresh name")
        check(p.rename("会议", to: "周会") && p.selected == "周会" && p.names.contains("周会") && !p.names.contains("会议"), "rename follows selection")
        check(!p.rename("默认", to: "x") && !p.rename("周会", to: "我的提示词"), "default cannot be renamed, no name clash")
        p.select("不存在")
        check(p.selected == "周会", "selecting an unknown name is ignored")

        p.save(to: file)
        var q = SummaryPrompts.load(file: file, legacy: legacy, defaultPrompt: base)
        check(q == p, "save/load round trip")

        check(!q.delete("默认") && q.names.contains("默认"), "default cannot be deleted")
        check(q.delete("周会") && q.selected == "默认", "deleting the selected profile falls back to default")

        q.update("默认", prompt: "我改了默认")
        check(q.current.prompt == "我改了默认", "default is editable")
        q.resetDefault()
        check(q.current.prompt == base, "reset restores built-in text")
        q.update("默认", prompt: "   ")
        check(q.current.prompt == base, "empty prompt falls back to built-in")

        try? "{ broken".write(to: file, atomically: true, encoding: .utf8)
        check(SummaryPrompts.load(file: file, legacy: legacy, defaultPrompt: base).names.contains("默认"), "corrupt json still yields default")
        print("ALL PASS")
    }
}
