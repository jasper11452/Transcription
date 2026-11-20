#!/usr/bin/env python3
"""Compile only WorkspaceModel with in-memory client/dialog/defaults substitutes."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
api = (repo / "Sources/TranscriptAPI.swift").read_text()
# Use the real API value types without linking the backend, credentials or services.
models = api.split("// MARK: - Client (the UI's one door to the engine)", 1)[0]
with tempfile.TemporaryDirectory(prefix="asr-workspace-editing-") as temporary:
    temp = Path(temporary)
    model_file = temp / "TranscriptValueTypes.swift"
    model_file.write_text(models)
    views = (repo / "Sources/TranscriptViews.swift").read_text()
    result_views = temp / "ResultEditingViews.swift"
    result_views.write_text("import AppKit\nimport SwiftUI\n" + views[views.index("struct TaskResult: View {"):])
    app = (repo / "Sources/App.swift").read_text()
    delegate = temp / "WorkspaceAppDelegate.swift"
    delegate.write_text(app.split("@main", 1)[0])
    executable = temp / "workspace-editing-tests"
    subprocess.run([
        "swiftc", "-parse-as-library", "-module-cache-path", str(temp / "module-cache"),
        str(model_file), str(repo / "Sources/AppPaths.swift"), str(repo / "Sources/Native/Text.swift"),
        str(repo / "Sources/WorkspaceModel.swift"), str(result_views), str(delegate),
        str(repo / "Tests/WorkspaceEditingRegressionTests.swift"), "-o", str(executable),
    ], check=True, cwd=repo)
    subprocess.run([str(executable)], check=True, cwd=temp)
