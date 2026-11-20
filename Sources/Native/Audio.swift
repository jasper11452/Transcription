import AVFoundation
import Foundation

/// Reads any audio or video file as 16 kHz mono floats.
enum AudioIO {
    static let rate = 16_000

    static func duration(of url: URL) async throws -> Double {
        let asset = AVURLAsset(url: url)
        guard try await !asset.loadTracks(withMediaType: .audio).isEmpty else { throw TFailure(message: "这个文件读不出声音，可能已损坏，或不是音频、视频文件。换一个文件试试。") }
        return try await asset.load(.duration).seconds
    }

    static func decode(_ url: URL) async throws -> [Float] {
        let asset = AVURLAsset(url: url)
        guard let track = try await asset.loadTracks(withMediaType: .audio).first else {
            throw TFailure(message: "这个文件没有声音轨道。")
        }
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
            AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false,
            AVSampleRateKey: rate, AVNumberOfChannelsKey: 1,
        ])
        reader.add(output)
        guard reader.startReading() else { throw TFailure(message: "读取音频失败：\(reader.error?.localizedDescription ?? "未知原因")") }
        var samples: [Float] = []
        while let buffer = output.copyNextSampleBuffer(), let block = CMSampleBufferGetDataBuffer(buffer) {
            let length = CMBlockBufferGetDataLength(block)
            var chunk = [Float](repeating: 0, count: length / MemoryLayout<Float>.size)
            CMBlockBufferCopyDataBytes(block, atOffset: 0, dataLength: length, destination: &chunk)
            samples.append(contentsOf: chunk)
        }
        if reader.status == .failed { throw TFailure(message: "读取音频失败：\(reader.error?.localizedDescription ?? "未知原因")") }
        return samples
    }

    /// 16-bit mono WAV, for cloud engines that take a file.
    static func wav(_ samples: ArraySlice<Float>) -> Data {
        var data = Data()
        func put<T: FixedWidthInteger>(_ v: T) { var x = v.littleEndian; withUnsafeBytes(of: &x) { data.append(contentsOf: $0) } }
        let bytes = samples.count * 2
        data.append(contentsOf: Array("RIFF".utf8)); put(UInt32(36 + bytes)); data.append(contentsOf: Array("WAVEfmt ".utf8))
        put(UInt32(16)); put(UInt16(1)); put(UInt16(1)); put(UInt32(rate)); put(UInt32(rate * 2)); put(UInt16(2)); put(UInt16(16))
        data.append(contentsOf: Array("data".utf8)); put(UInt32(bytes))
        for s in samples { put(Int16(max(-1, min(1, s)) * 32767)) }
        return data
    }
}
