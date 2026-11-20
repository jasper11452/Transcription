#!/bin/bash
# Synthetic local SSE + real backend/persistence + a background SwiftUI window.
# Requires Python 3; UI tests also need a macOS GUI session.
# First argument: screenshot directory, or --headless to run parser/backend only.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/asr-streaming-tests.XXXXXX")"
SERVER_PID=""
printf '%s\n' \
    'struct RegressionAccountToken { let accessToken: String }' \
    'enum AccountCredentialStore { static func loadOpenAI() -> RegressionAccountToken? { nil } }' \
    'enum DoubaoWebAuth { static let isConfigured = false }' \
    'enum OpenAIAccountAuth { static func runResponses(system: String, input: String, model: String, effort: String?, onDelta: @escaping @Sendable (String) async -> Void) async throws -> String { throw TFailure(message: "test stub") } }' \
    > "$TEST_DIR/ServiceStubs.swift"
cleanup() {
    if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; fi
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT
python3 "$PROJECT_DIR/Tests/mock_summary_server.py" "$TEST_DIR/pipeline" > "$TEST_DIR/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 100); do
    [ -f "$TEST_DIR/pipeline/data/server-ready" ] && break
    kill -0 "$SERVER_PID" 2>/dev/null || { cat "$TEST_DIR/server.log" >&2; exit 1; }
    sleep 0.05
done
[ -f "$TEST_DIR/pipeline/data/server-ready" ] || { echo "Local SSE fixture failed to start" >&2; exit 1; }
xcrun swiftc -swift-version 5 -parse-as-library \
    "$PROJECT_DIR/Sources/MarkdownDocument.swift" \
    "$PROJECT_DIR/Tests/MarkdownDocumentTests.swift" \
    -o "$TEST_DIR/MarkdownDocumentTests"
"$TEST_DIR/MarkdownDocumentTests"
xcrun swiftc -swift-version 5 -parse-as-library \
    "$PROJECT_DIR/Sources/Native/SummaryPrompts.swift" \
    "$PROJECT_DIR/Tests/SummaryPromptsTests.swift" \
    -o "$TEST_DIR/SummaryPromptsTests"
"$TEST_DIR/SummaryPromptsTests"
xcrun swiftc -swift-version 5 -parse-as-library \
    "$PROJECT_DIR/Sources/AppPaths.swift" "$PROJECT_DIR/Sources/TranscriptAPI.swift" \
    "$TEST_DIR/ServiceStubs.swift" \
    "$PROJECT_DIR/Sources/Native/ConfigEnv.swift" "$PROJECT_DIR/Sources/Native/Text.swift" \
    "$PROJECT_DIR/Sources/Native/Services.swift" "$PROJECT_DIR/Sources/Native/LLMReasoning.swift" \
    "$PROJECT_DIR/Sources/Native/TranscriptChat.swift" "$PROJECT_DIR/Sources/Native/Backend.swift" \
    "$PROJECT_DIR/Sources/Native/SummaryPrompts.swift" "$PROJECT_DIR/Sources/Native/TranscriptionOutput.swift" \
    "$PROJECT_DIR/Sources/MarkdownDocument.swift" "$PROJECT_DIR/Tests/SummaryPipelineTests.swift" \
    -o "$TEST_DIR/SummaryPipelineTests"
"$TEST_DIR/SummaryPipelineTests" -DataRoot "$TEST_DIR/pipeline"
if [ "${1:-}" = "--headless" ]; then exit 0; fi
xcrun swiftc -swift-version 5 -parse-as-library \
    "$PROJECT_DIR/Sources/MarkdownDocument.swift" \
    "$PROJECT_DIR/Sources/MarkdownView.swift" \
    "$PROJECT_DIR/Tests/StreamingMarkdownTests.swift" \
    -o "$TEST_DIR/StreamingMarkdownTests"
"$TEST_DIR/StreamingMarkdownTests" "$@"
