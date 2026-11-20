// swift-tools-version:6.2
import PackageDescription

let package = Package(
    name: "Transcription",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "Vendor/mlx-audio-swift"),
        .package(path: "Vendor/mlx-swift"),
    ],
    targets: [
        .executableTarget(
            name: "Transcription",
            dependencies: [
                .product(name: "MLX", package: "mlx-swift"),
                .product(name: "MLXAudioCore", package: "mlx-audio-swift"),
                .product(name: "MLXAudioSTT", package: "mlx-audio-swift"),
                .product(name: "MLXAudioVAD", package: "mlx-audio-swift"),
            ],
            path: "Sources",
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
