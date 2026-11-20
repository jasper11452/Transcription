#!/usr/bin/env python3
"""Run isolated regressions without building the app, MLX, or downloading models.

The model query declarations are taken verbatim from production source because
Models.swift also contains SwiftUI and downloader code outside this suite.
All preferences, configuration, and model state are in-memory substitutes.
"""
import pathlib
import subprocess
import tempfile

project = pathlib.Path(__file__).resolve().parents[1]
models = (project / "Sources/Models.swift").read_text()
engine = (project / "Sources/Native/Engine.swift").read_text()
catalog = models[models.index("struct ModelSpec:"):models.index("enum DownloadSource:")]
state = models[models.index("enum ModelState:"):models.index("private func format(")]
queries = models[models.index("    func state(_ repo:"):models.index("    var isDownloading:")]
local_models = engine[engine.index("enum LocalModel {"):engine.index("/// Loads the models")]

with tempfile.TemporaryDirectory(prefix="asr-engine-regression-") as temporary:
    temporary = pathlib.Path(temporary)
    model_queries = temporary / "ModelQueries.swift"
    model_queries.write_text("import Foundation\n"
                            "struct RegressionAccountToken { let accessToken: String }\n"
                            "enum AccountCredentialStore { static func loadOpenAI() -> RegressionAccountToken? { nil } }\n"
                            "enum DoubaoWebAuth { static let isConfigured = false }\n"
                            + local_models + catalog + state +
                            "@MainActor final class ModelStore {\n"
                            "var states: [String: ModelState] = [:]\n" + queries + "}\n")
    binary = temporary / "engine-regression-tests"
    subprocess.run([
        "swiftc", "-swift-version", "5", "-parse-as-library",
        str(project / "Sources/Native/TranscriptionOutput.swift"),
        str(project / "Sources/Native/Services.swift"), str(model_queries),
        str(project / "Tests/EngineReviewRegressionTests.swift"), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
    subprocess.run([
        "swiftc", "-frontend", "-parse", str(project / "Sources/Native/Engine.swift"),
        str(project / "Sources/Models.swift"),
    ], check=True)
