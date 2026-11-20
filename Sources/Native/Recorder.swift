import AVFoundation
import Combine
import Foundation

enum RecorderState: Equatable {
    case idle
    case preparing
    case recording
    case paused
    case stopping

    var isActive: Bool {
        switch self {
        case .recording, .paused, .stopping: return true
        case .idle, .preparing: return false
        }
    }
}

@MainActor
final class RecordingModel: ObservableObject {
    @Published private(set) var state: RecorderState = .idle
    @Published private(set) var elapsed = 0.0
    @Published private(set) var level = 0.0
    @Published private(set) var error: String?

    private var recorder: MicrophoneRecorder?
    private var outputURL: URL?
    private var startedAt: Date?
    private var accumulated = 0.0
    private var ticker: Task<Void, Never>?
    private var startTask: Task<Void, Never>?
    private var startToken: UUID?

    var isActive: Bool { state.isActive || state == .preparing }
    var isPaused: Bool { state == .paused }
    var isPreparing: Bool { state == .preparing }

    func start() {
        guard state == .idle else { return }
        state = .preparing
        error = nil
        elapsed = 0
        level = 0
        accumulated = 0
        let token = UUID()
        startToken = token

        startTask = Task { @MainActor [weak self] in
            let allowed = await AVAudioApplication.requestRecordPermission()
            guard let self else { return }
            guard allowed else {
                guard !Task.isCancelled, startToken == token, state == .preparing else { return }
                state = .idle
                error = "没有麦克风权限。到系统设置 › 隐私与安全性 › 麦克风里允许语音转写。"
                startTask = nil
                startToken = nil
                return
            }
            guard !Task.isCancelled, startToken == token, state == .preparing else { return }
            var allocatedURL: URL?
            do {
                let url = try Self.newRecordingURL()
                allocatedURL = url
                let recorder = try MicrophoneRecorder(url: url) { [weak self] value in
                    DispatchQueue.main.async { self?.level = value }
                }
                try recorder.start()
                guard !Task.isCancelled, startToken == token, state == .preparing else {
                    _ = recorder.finish()
                    try? FileManager.default.removeItem(at: url)
                    return
                }
                self.recorder = recorder
                outputURL = url
                startedAt = .now
                state = .recording
                startTicker()
                startTask = nil
                startToken = nil
            } catch {
                if let allocatedURL { try? FileManager.default.removeItem(at: allocatedURL) }
                guard startToken == token else { return }
                state = .idle
                self.error = Self.friendly(error)
                startTask = nil
                startToken = nil
            }
        }
    }

    func togglePause() {
        switch state {
        case .recording:
            accumulated += Date().timeIntervalSince(startedAt ?? .now)
            startedAt = nil
            recorder?.pause()
            state = .paused
            ticker?.cancel()
            elapsed = accumulated
            level = 0
        case .paused:
            do {
                try recorder?.resume()
                startedAt = .now
                state = .recording
                startTicker()
            } catch {
                self.error = Self.friendly(error)
            }
        default:
            break
        }
    }

    @discardableResult
    func stop() -> URL? {
        guard state == .recording || state == .paused else { return nil }
        if state == .recording { accumulated += Date().timeIntervalSince(startedAt ?? .now) }
        elapsed = accumulated
        state = .stopping
        ticker?.cancel()
        ticker = nil
        let url = outputURL
        let finished = recorder?.finish()
        recorder = nil
        outputURL = nil
        startedAt = nil
        state = .idle
        level = 0
        guard let finished, accumulated >= 0.5 else {
            if let url { try? FileManager.default.removeItem(at: url) }
            if finished == nil { error = "录音没有保存成功，请检查麦克风后重试。" }
            else { error = "录音太短，没有可转写的内容。" }
            return nil
        }
        error = nil
        return finished
    }

    func discard() {
        startTask?.cancel()
        startTask = nil
        startToken = nil
        ticker?.cancel()
        ticker = nil
        let url = outputURL
        _ = recorder?.finish()
        recorder = nil
        outputURL = nil
        startedAt = nil
        state = .idle
        elapsed = 0
        level = 0
        if let url { try? FileManager.default.removeItem(at: url) }
    }

    private func startTicker() {
        ticker?.cancel()
        ticker = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(100))
                guard let self, !Task.isCancelled else { return }
                elapsed = accumulated + Date().timeIntervalSince(startedAt ?? .now)
            }
        }
    }

    private static func newRecordingURL() throws -> URL {
        let folder = AppPaths.layout.dataDir.appendingPathComponent("recordings", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        let stem = "录音-" + formatter.string(from: .now)
        var url = folder.appendingPathComponent(stem).appendingPathExtension("wav")
        var suffix = 2
        while FileManager.default.fileExists(atPath: url.path) {
            url = folder.appendingPathComponent("\(stem)-\(suffix)").appendingPathExtension("wav")
            suffix += 1
        }
        return url
    }

    private static func friendly(_ error: Error) -> String {
        let text = error.localizedDescription
        if text.isEmpty { return "麦克风启动失败，请检查输入设备后重试。" }
        return "麦克风启动失败：\(text)"
    }

    deinit {
        startTask?.cancel()
        ticker?.cancel()
        _ = recorder?.finish()
    }
}

final class MicrophoneRecorder: @unchecked Sendable {
    private let engine = AVAudioEngine()
    private let outputURL: URL
    private let outputFormat: AVAudioFormat
    private let levelHandler: (Double) -> Void
    private let writeLock = NSLock()
    private let stateLock = NSLock()
    private var file: AVAudioFile?
    private var converter: AVAudioConverter?
    private var stopped = false
    private var writingError: Error?

    init(url: URL, levelHandler: @escaping (Double) -> Void) throws {
        guard let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Double(AudioIO.rate), channels: 1, interleaved: true) else {
            throw TFailure(message: "无法准备录音格式。")
        }
        outputURL = url
        outputFormat = format
        self.levelHandler = levelHandler
    }

    func start() throws {
        let input = engine.inputNode
        input.removeTap(onBus: 0)
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
            throw TFailure(message: "没有可用的麦克风输入设备。")
        }
        guard let converter = AVAudioConverter(from: inputFormat, to: outputFormat) else {
            throw TFailure(message: "无法转换麦克风格式。")
        }
        file = try AVAudioFile(forWriting: outputURL, settings: outputFormat.settings)
        self.converter = converter
        stateLock.lock(); stopped = false; writingError = nil; stateLock.unlock()
        input.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) { [weak self] buffer, _ in
            self?.consume(buffer)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            file = nil
            try? FileManager.default.removeItem(at: outputURL)
            throw error
        }
    }

    func pause() {
        engine.pause()
    }

    func resume() throws {
        try engine.start()
    }

    func finish() -> URL? {
        stateLock.lock()
        if stopped {
            let result = writingError == nil ? outputURL : nil
            stateLock.unlock()
            return result
        }
        stopped = true
        stateLock.unlock()

        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        writeLock.lock()
        writeLock.unlock()
        stateLock.lock()
        let error = writingError
        stateLock.unlock()
        file = nil
        converter = nil
        guard error == nil, FileManager.default.fileExists(atPath: outputURL.path) else {
            try? FileManager.default.removeItem(at: outputURL)
            return nil
        }
        return outputURL
    }

    private func consume(_ inputBuffer: AVAudioPCMBuffer) {
        stateLock.lock()
        let shouldStop = stopped
        stateLock.unlock()
        guard !shouldStop else { return }

        let meter = Self.level(inputBuffer)
        writeLock.lock()
        defer { writeLock.unlock() }
        stateLock.lock()
        let active = !stopped
        stateLock.unlock()
        guard active, let converted = convert(inputBuffer) else { return }
        do {
            try file?.write(from: converted)
        } catch {
            stateLock.lock(); writingError = error; stateLock.unlock()
        }
        levelHandler(meter)
    }

    private func convert(_ inputBuffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let converter else { return nil }
        let ratio = outputFormat.sampleRate / inputBuffer.format.sampleRate
        let capacity = max(1, AVAudioFrameCount(Double(inputBuffer.frameLength) * ratio) + 32)
        guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else { return nil }
        var provided = false
        var conversionError: NSError?
        let status = converter.convert(to: output, error: &conversionError) { _, status in
            if provided {
                status.pointee = .noDataNow
                return nil
            }
            provided = true
            status.pointee = .haveData
            return inputBuffer
        }
        guard status != .error, conversionError == nil, output.frameLength > 0 else {
            let failure: Error = conversionError ?? TFailure(message: "无法写入录音，请检查麦克风输入。")
            stateLock.lock(); writingError = failure; stateLock.unlock()
            return nil
        }
        return output
    }

    private static func level(_ buffer: AVAudioPCMBuffer) -> Double {
        guard let samples = buffer.floatChannelData?[0] else { return 0 }
        let frames = Int(buffer.frameLength)
        let channels = buffer.format.isInterleaved ? Int(buffer.format.channelCount) : 1
        let count = frames * max(channels, 1)
        guard count > 0 else { return 0 }
        var sum: Float = 0
        for index in 0..<count {
            let sample = samples[index]
            sum += sample * sample
        }
        let rms = sqrt(sum / Float(count))
        return min(max(Double(rms) * 4, 0), 1)
    }

    deinit {
        _ = finish()
    }
}
