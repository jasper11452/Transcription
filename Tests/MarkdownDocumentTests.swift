import Foundation

@main
struct MarkdownDocumentTests {
    static func check(_ condition: @autoclosure () -> Bool, _ name: String) {
        guard condition() else { fputs("FAIL \(name)\n", stderr); exit(1) }
        print("PASS \(name)")
    }

    static func main() {
        let headings = MarkdownDocument((1...6).map { String(repeating: "#", count: $0) + " 第\($0)级标题" }.joined(separator: "\n\n"))
        check(headings.blocks.map(\.kind) == (1...6).map { .heading($0) }, "all six heading levels survive parsing")
        check(MarkdownDocument("标题\n===\n\n小节\n---").blocks.map(\.kind) == [.heading(1), .heading(2)], "setext headings preserve levels")

        let nested = MarkdownDocument("""
        - **业务模块**
          - **上周完成**
            - 具体工作
              继续说明
          - [ ] 明天验收
          - [x] 已完成编译
        - **第二模块**
        """)
        check(nested.blocks.compactMap { $0.list?.depth } == [0, 1, 2, 1, 1, 0], "nested list and task depths")
        check(nested.blocks[0].isLabel && nested.blocks[1].isLabel && !nested.blocks[2].isLabel, "bold module labels retain inline styling")
        check(String(nested.blocks[2].text.characters).contains("继续说明"), "list continuation stays with its parent")
        let softBreak = MarkdownDocument("第一行\n第二行")
        check(String(softBreak.blocks[0].text.characters) == "第一行\n第二行", "paragraph soft breaks keep the author's line layout")
        let spacedCode = MarkdownDocument("```\n\n  indented  \n\n```")
        check(String(spacedCode.blocks[0].text.characters) == "\n  indented  \n\n", "code block whitespace is preserved")
        check(nested.blocks[3].list?.marker == .task(false) && nested.blocks[4].list?.marker == .task(true), "task completion states")
        check(String(nested.blocks[3].text.characters) == "明天验收", "task syntax is removed from display text")

        let numbered = MarkdownDocument("3. 第三项\n   1. 子步骤\n4. 第四项")
        check(numbered.blocks.compactMap { $0.list?.marker } == [.number(3), .number(1), .number(4)], "ordered list starts and nesting")
        let loose = MarkdownDocument("- 第一段\n\n  同一项的第二段\n\n- 下一项")
        check(loose.blocks[1].list?.marker == .continuation, "multi-paragraph items do not repeat markers")
        let quote = MarkdownDocument("> 引用\n>\n> > 深一层的引用")
        check(quote.blocks.map(\.quoteDepth) == [1, 2], "nested quotes preserve depth")
        let code = MarkdownDocument("```swift\nlet text = \"# 原样\"\n```")
        check(code.blocks.first?.kind == .code && String(code.blocks[0].text.characters).contains("# 原样"), "code is kept verbatim")

        let table = MarkdownDocument("| 事项 | 负责人 |\n| :--- | ---: |\n| 验收 | 开发组 |\n| 待确认 | |")
        check(table.blocks.count == 1 && table.blocks[0].kind == .table, "table remains one semantic block")
        check(table.blocks[0].rows.count == 3 && table.blocks[0].rows[0].header, "table header and data rows")
        check(String(table.blocks[0].rows[1].cells[1].characters) == "开发组", "table cell content")
        check(table.blocks[0].columns[1].alignment == .right, "table column alignment")

        let link = MarkdownDocument("查看 [原文](https://example.com) 和 `代码`。")
        check(link.blocks[0].text.runs.contains { $0.link != nil }, "links retain their destinations")
        for source in ["# 正在生成", "# 总结\n\n**正在输出", "- 模块\n  - 正在写", "```\n未闭合代码"] {
            let document = MarkdownDocument(source)
            check(!document.blocks.isEmpty && !document.blocks[0].text.characters.isEmpty, "incomplete stream remains visible")
        }
        let long = (0..<200).map { "- **模块\($0)**\n  - 子类\n    - 具体说明及 [原文](https://example.com)" }.joined(separator: "\n")
        let start = Date()
        let parsed = MarkdownDocument(long)
        check(parsed.blocks.count == 600, "long summary keeps every nested item")
        print(String(format: "Parsed %d blocks in %.3f seconds", parsed.blocks.count, Date().timeIntervalSince(start)))
    }
}
