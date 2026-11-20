import SwiftUI

struct TranscriptChatView: View {
    @ObservedObject var model: WorkspaceModel
    let taskID: Int
    let onCitation: (TranscriptCitation) -> Void
    @State private var input = ""
    @State private var expandedThinking = Set<UUID>()
    @FocusState private var focused: Bool

    private var conversation: TranscriptChatConversation { model.chatConversation }
    private var generating: Bool { conversation.activeRequest != nil }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("文稿对话").font(.headline)
                Spacer()
                Button { Task { await model.clearChat(for: taskID) } } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .help("清空会话")
                .disabled(conversation.turns.isEmpty || generating)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(conversation.turns) { turn in
                            turnView(turn)
                                .id(turn.id)
                        }
                        Color.clear.frame(height: 1).id("chat-end")
                    }
                    .padding(14)
                }
                .scrollIndicators(.automatic)
                .onAppear { scrollLatest(proxy, animated: false) }
                .onChange(of: conversation.turns.count) { _, _ in scrollLatest(proxy) }
                .onChange(of: conversation.turns.map { $0.answer + $0.reasoning }) { _, _ in scrollLatest(proxy) }
            }
            if let error = model.chatError {
                Text(error).font(.callout).foregroundStyle(.red).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 14).padding(.bottom, 6)
            }
            Divider()
            HStack(alignment: .bottom, spacing: 8) {
                TextEditor(text: $input)
                    .focused($focused)
                    .frame(minHeight: 34, maxHeight: 88)
                    .scrollContentBackground(.hidden)
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 14).fill(Color.primary.opacity(0.06)))
                Button {
                    if generating { Task { await model.stopChat(for: taskID) } }
                    else { send() }
                } label: {
                    Image(systemName: generating ? "stop.fill" : "arrow.up")
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!generating && input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .help(generating ? "停止回复" : "发送")
            }
            .padding(10)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .task(id: taskID) {
            await model.loadChat(taskID)
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(180))
                await model.loadChat(taskID)
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { focused = true } label: { Image(systemName: "square.and.pencil") }
                    .help("新问题")
            }
        }
    }

    @ViewBuilder private func turnView(_ turn: TranscriptChatTurn) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Spacer(minLength: 40)
                Text(turn.question)
                    .textSelection(.enabled)
                    .padding(.horizontal, 12).padding(.vertical, 9)
                    .background(Brand.accent, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .foregroundStyle(Brand.onAccent)
            }
            HStack(alignment: .top, spacing: 7) {
                Image(systemName: "text.bubble").foregroundStyle(Brand.accent).padding(.top, 7)
                VStack(alignment: .leading, spacing: 7) {
                    if !turn.reasoning.isEmpty {
                        Button { if expandedThinking.contains(turn.id) { expandedThinking.remove(turn.id) } else { expandedThinking.insert(turn.id) } } label: {
                            HStack(spacing: 5) {
                                Image(systemName: expandedThinking.contains(turn.id) ? "chevron.down" : "chevron.right").font(.caption2)
                                Text(turn.status == .generating ? "正在思考…" : "思考过程").lineLimit(1)
                            }
                            .font(.caption).foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        if expandedThinking.contains(turn.id) {
                            Text(turn.reasoning).font(.caption).foregroundStyle(.secondary).lineSpacing(3).textSelection(.enabled)
                        }
                    }
                    if !turn.answer.isEmpty {
                        MarkdownView(source: turn.renderedAnswer)
                            .textSelection(.enabled)
                            .environment(\.openURL, OpenURLAction { url in
                                let rawIndex = url.host ?? String(url.path.dropFirst())
                                guard url.scheme == "asr-citation", let index = Int(rawIndex), let citation = turn.citations.first(where: { $0.index == index }) else { return .discarded }
                                onCitation(citation)
                                return .handled
                            })
                    } else if turn.status == .generating {
                        ProgressView().controlSize(.small)
                    }
                    if let error = turn.error {
                        HStack(spacing: 8) {
                            Text(error).font(.caption).foregroundStyle(.orange)
                            Button("重试") { Task { await model.retryChat(turn.id, for: taskID) } }.buttonStyle(.borderless)
                        }
                    }
                }
                .padding(.horizontal, 12).padding(.vertical, 9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
        }
    }

    private func send() {
        let question = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !question.isEmpty else { return }
        input = ""
        Task { await model.sendChat(question, for: taskID) }
    }

    private func scrollLatest(_ proxy: ScrollViewProxy, animated: Bool = true) {
        if animated { withAnimation(.smooth) { proxy.scrollTo("chat-end", anchor: .bottom) } }
        else { proxy.scrollTo("chat-end", anchor: .bottom) }
    }
}
