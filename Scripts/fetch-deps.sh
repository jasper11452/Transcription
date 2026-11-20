#!/bin/bash
# Fetches the two Swift packages the app builds on into Vendor/ (kept out of git) and applies the one local patch.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p Vendor && cd Vendor
[ -d mlx-swift ] || git clone --depth 1 --recurse-submodules --shallow-submodules https://github.com/ml-explore/mlx-swift.git
[ -d mlx-audio-swift ] || git clone --depth 1 https://github.com/Blaizzy/mlx-audio-swift.git
# Silero VAD v6 ships no 8 kHz branch; the loader should not insist on one.
sed -i '' 's/verify: \[.all\]/verify: [.noUnusedKeys]/' mlx-audio-swift/Sources/MLXAudioVAD/Models/SileroVAD/SileroVAD.swift
echo "Tested with mlx-swift $(git -C mlx-swift rev-parse --short HEAD) and mlx-audio-swift $(git -C mlx-audio-swift rev-parse --short HEAD)"
