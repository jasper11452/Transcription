// 音频层：播放引擎、静音预扫、合成演示音频。
// 解码本身直接用 Web Audio 的 decodeAudioData，不在这一层再包一遍。
//
// 演示音频为什么要自己合成：一个需要用户先准备好录音才能看见界面的工作台是没法评审的。
// 这里用 OfflineAudioContext 造一段有起承转合的多说话人"会议"——
// 基频 + 共振峰 + 音节包络 + 房间底噪，听得出谁在说话、听得出停顿，
// 于是波形、分段、跟读高亮、跳过静音全都能被真实触发。

const TAU = Math.PI * 2;

/* ------------------------------------------------------------------ 解码 */

/* ------------------------------------------------------- 合成演示音频 */

/**
 * 用共振峰模型合成"像人说话"的音节序列。
 * 不是语音识别素材，只是让播放、定位、波形、跳过静音有真实输入，
 * 所以只要"有起伏、有停顿、听得出几个人在说"就够了。
 */
export function synthesizeSpeech({ sampleRate = 44100, duration = 96, script = [], roomTone = 0.012, seed = 20260924 } = {}) {
  const length = Math.ceil(duration * sampleRate);
  const offline = new OfflineAudioContext(1, length, sampleRate);

  // 确定性随机：同一 seed 每次生成同一段音频，回归测试才能引用它
  let s = seed >>> 0;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0), s / 4294967296);

  // 房间底噪（粉噪近似）：让静音段不是绝对 0，波形看起来才像真录音
  const noise = offline.createBuffer(1, length, sampleRate);
  const nd = noise.getChannelData(0);
  let pink = 0;
  for (let i = 0; i < length; i += 1) {
    const white = rnd() * 2 - 1;
    pink = (pink + 0.02 * white) / 1.02;
    nd[i] = white * 0.35 + pink * 2.2;
  }
  const noiseSrc = offline.createBufferSource();
  noiseSrc.buffer = noise;
  const noiseGain = offline.createGain();
  noiseGain.gain.value = roomTone;
  noiseSrc.connect(noiseGain).connect(offline.destination);
  noiseSrc.start();

  const master = offline.createGain();
  master.gain.value = 0.85;
  master.connect(offline.destination);

  for (const line of script) {
    const { start, end, voice = {} } = line;
    if (!(end > start)) continue;
    const f0 = voice.f0 || 180;
    const gain = voice.gain ?? 0.5;

    // 音节节奏 3~6 个/秒，偶尔"想一下"留个长一点的缝
    for (let t = start; t < end - 0.05; ) {
      const dur = Math.min(0.16 + rnd() * 0.14, end - t);
      const amp = gain * (0.6 + rnd() * 0.5);
      const drift = 0.94 + rnd() * 0.14; // 声调起伏

      // 三个共振峰叠出元音色；包络快起慢落，避免点击声
      [f0, ...(voice.formants || [700, 1200, 2600])].forEach((f, k) => {
        const osc = offline.createOscillator();
        osc.type = k === 0 ? 'sawtooth' : 'sine';
        osc.frequency.value = f * drift;
        const g = offline.createGain();
        const peak = Math.max(0.001, amp * (k === 0 ? 0.5 : 0.7 / (k + 1)));
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(peak, t + Math.min(0.045, dur / 3));
        g.gain.setValueAtTime(peak, t + dur * 0.55);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        osc.connect(g).connect(master);
        osc.start(t);
        osc.stop(t + dur + 0.02);
      });

      t += dur + (rnd() < 0.12 ? 0.12 + rnd() * 0.2 : 0.02 + rnd() * 0.05);
    }
  }

  return offline.startRendering(); // -> AudioBuffer
}

/* -------------------------------------------------------------- 播放引擎 */
export function createAudioEngine({ onTime, onState, onError } = {}) {
  let ctx = null;
  let buffer = null;
  let source = null;
  let gainNode = null;
  let startedAt = 0;
  let startOffset = 0;
  let playing = false;
  let rate = 1;
  let volume = 0.9;
  let loop = null; // {start, end}
  let silenceMap = null;
  let rafId = 0;
  let skipSilence = false;

  function ensureCtx() {
    if (!ctx) {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) throw new Error('这个浏览器没有 Web Audio，工作台无法播放音频');
      ctx = new Ctor();
      gainNode = ctx.createGain();
      gainNode.gain.value = volume;
      gainNode.connect(ctx.destination);
    }
    return ctx;
  }

  /** 预扫静音：RMS 低于阈值的连续区间。播放时用来"跳过静音"。 */
  function buildSilenceMap(threshold = 0.012, minLen = 0.35) {
    if (!buffer) return [];
    const data = buffer.getChannelData(0);
    const win = Math.floor(buffer.sampleRate * 0.02);
    const map = [];
    let runStart = null;
    for (let i = 0; i < data.length; i += win) {
      let sum = 0;
      const end = Math.min(i + win, data.length);
      for (let j = i; j < end; j += 1) sum += data[j] * data[j];
      const rms = Math.sqrt(sum / (end - i));
      const t = i / buffer.sampleRate;
      if (rms < threshold) {
        if (runStart == null) runStart = t;
      } else if (runStart != null) {
        if (t - runStart >= minLen) map.push({ start: runStart, end: t });
        runStart = null;
      }
    }
    const lastT = data.length / buffer.sampleRate;
    if (runStart != null && lastT - runStart >= minLen) map.push({ start: runStart, end: lastT });
    silenceMap = map;
    return map;
  }

  /** 波形峰值：多分辨率缓存，避免每次缩放都全量扫描 */
  function buildPeaks(buckets) {
    if (!buffer) return null;
    const data = buffer.getChannelData(0);
    const size = Math.max(1, Math.floor(data.length / buckets));
    const out = new Float32Array(buckets * 2);
    for (let b = 0; b < buckets; b += 1) {
      let min = 1;
      let max = -1;
      const s = b * size;
      const e = Math.min(s + size, data.length);
      for (let i = s; i < e; i += 1) {
        const v = data[i];
        if (v < min) min = v;
        if (v > max) max = v;
      }
      out[b * 2] = min;
      out[b * 2 + 1] = max;
    }
    return out;
  }

  function currentTime() {
    if (!ctx || !buffer) return startOffset;
    if (!playing) return startOffset;
    let t = startOffset + (ctx.currentTime - startedAt) * rate;
    if (loop) {
      // 循环区间内按模长折算，避免位置跑到区间外
      const len = loop.end - loop.start;
      if (len > 0 && (t >= loop.end || t < loop.start - 1e-6)) {
        t = loop.start + (((t - loop.start) % len) + len) % len;
      }
    }
    return Math.min(t, buffer.duration);
  }

  function tick() {
    if (!playing) return;
    rafId = 0;
    // 一帧里的任何异常都不允许中断播放循环：
    // 这里曾经因为一个未定义标识符在第一帧就抛异常，导致整个进度更新永久停摆。
    try {
      const t = currentTime();
      if (onTime) onTime(t, buffer ? buffer.duration : 0);
      // 跳过静音只在没有循环区间时生效，否则会跟循环抢位置
      if (!loop && skipSilence && silenceMap) {
        const hit = silenceMap.find((s) => t >= s.start && t < s.end && s.end - s.start > 0.6);
        if (hit && hit.end - t > 0.2) {
          engine.seek(hit.end + 0.02);
          return;
        }
      }
    } catch (err) {
      if (onError) onError(err);
      // 吞掉本帧错误继续跑：宁可某帧高亮不更新，也不能没有播放头
    }
    if (playing) rafId = requestAnimationFrame(tick);
  }

  /** 播放循环的唯一入口：保证 rafId 注册与 playing 状态永远一致 */
  function startLoop() {
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(tick);
  }

  function stopSource() {
    if (source) {
      try {
        source.onended = null;
        source.stop();
      } catch {
        /* 已经停了 */
      }
      source.disconnect();
      source = null;
    }
  }

  function startSource(at, { when = 0 } = {}) {
    ensureCtx();
    stopSource();
    source = ctx.createBufferSource();
    source.buffer = buffer;
    source.playbackRate.value = rate;
    if (loop) {
      source.loop = true;
      source.loopStart = loop.start;
      source.loopEnd = loop.end;
    }
    source.connect(gainNode);
    source.onended = () => {
      // 只有自然播完（非手动 stop）才归零
      if (playing && !loop && currentTime() >= buffer.duration - 0.05) {
        playing = false;
        startOffset = buffer.duration;
        if (onState) onState({ playing, time: startOffset });
      }
    };
    const offset = loop ? Math.max(at, loop.start) % (buffer.duration || 1) : Math.max(0, Math.min(at, buffer.duration));
    source.start(ctx.currentTime + when, offset);
    startedAt = ctx.currentTime + when;
    startOffset = offset;
  }

  const engine = {
    get ctx() {
      return ensureCtx();
    },
    get buffer() {
      return buffer;
    },
    get playing() {
      return playing;
    },
    get duration() {
      return buffer ? buffer.duration : 0;
    },
    get silenceMap() {
      return silenceMap;
    },
    get loop() {
      return loop;
    },

    async ensureRunning() {
      ensureCtx();
      if (ctx.state === 'suspended') await ctx.resume();
    },

    setBuffer(audioBuffer, meta = {}) {
      stopSource();
      playing = false;
      startOffset = 0;
      buffer = audioBuffer;
      silenceMap = null;
      loop = null;
      if (buffer) {
        buffer.__peaksCache = new Map();
        buffer.__meta = meta;
        buildSilenceMap();
      }
      if (onState) onState({ playing, time: 0, duration: engine.duration });
      return buffer;
    },

    async play(at = null) {
      if (!buffer) return false;
      await engine.ensureRunning();
      const target = at == null ? startOffset : at;
      startSource(target >= buffer.duration - 0.01 ? 0 : target);
      playing = true;
      startLoop();
      if (onState) onState({ playing, time: currentTime(), duration: buffer.duration });
      return true;
    },

    pause() {
      if (!playing) return;
      startOffset = currentTime();
      stopSource();
      playing = false;
      cancelAnimationFrame(rafId);
      if (onState) onState({ playing, time: startOffset, duration: engine.duration });
    },

    toggle() {
      return playing ? (engine.pause(), false) : engine.play();
    },

    seek(t) {
      if (!buffer) return;
      const target = Math.max(0, Math.min(t, buffer.duration));
      startOffset = target;
      if (playing) {
        startSource(target);
        startLoop();
      }
      if (onTime) onTime(target, buffer.duration);
      if (onState) onState({ playing, time: target, duration: buffer.duration });
    },

    nudge(delta) {
      engine.seek(currentTime() + delta);
    },

    setRate(next) {
      rate = Math.max(0.25, Math.min(4, next));
      if (playing) {
        const t = currentTime();
        startSource(t);
        startLoop();
      }
      return rate;
    },

    setVolume(v) {
      volume = Math.max(0, Math.min(1, v));
      if (gainNode) gainNode.gain.value = volume;
      return volume;
    },

    setLoop(start, end) {
      loop = end > start + 0.05 ? { start, end } : null;
      if (playing) {
        startSource(currentTime());
        startLoop();
      }
      return loop;
    },

    get time() {
      return currentTime();
    },

    peaks(buckets) {
      if (!buffer) return null;
      const key = buckets;
      if (!buffer.__peaksCache) buffer.__peaksCache = new Map();
      if (!buffer.__peaksCache.has(key)) buffer.__peaksCache.set(key, buildPeaks(buckets));
      return buffer.__peaksCache.get(key);
    },

    set skipSilence(on) {
      skipSilence = !!on;
      return skipSilence;
    },

    destroy() {
      cancelAnimationFrame(rafId);
      stopSource();
      ctx?.close();
      ctx = null;
    },
  };

  return engine;
}

/* ---------------------------------------------------- 造一份演示转录文本 */

export const DEMO_SCRIPT = [
  { start: 0.6, end: 7.2, speaker: 'spk_a', voice: { f0: 176, formants: [720, 1180, 2560], gain: 0.5 }, text: '好，人都到齐了，我们开始今天的产品评审。今天是九月二十四号，主要过三件事：转录质量、导出格式，还有前端这一版的重做。' },
  { start: 7.9, end: 13.4, speaker: 'spk_b', voice: { f0: 208, formants: [660, 1720, 2410], gain: 0.46 }, text: '我先说质量。昨天用那段八十七分钟的访谈跑了一遍离线引擎，专业名词错了四个，都是人名和公司名。' },
  { start: 14.0, end: 17.6, speaker: 'spk_a', voice: { f0: 176, formants: [720, 1180, 2560], gain: 0.5 }, text: '那四个是可以通过热词表解决，还是得人手改？' },
  { start: 18.2, end: 25.8, speaker: 'spk_b', voice: { f0: 208, formants: [660, 1720, 2410], gain: 0.46 }, text: '热词表能盖住三个。剩下一个是外文缩写，模型把它当成英文单词切成了两半，这个只能标注出来让人复核。' },
  { start: 26.4, end: 33.1, speaker: 'spk_c', voice: { f0: 148, formants: [600, 1040, 2400], gain: 0.44 }, text: '我建议低置信度的段落直接在界面上标出来，不要等人自己去听。刚才那一句在我这边看置信度只有零点六。' },
  { start: 33.8, end: 40.5, speaker: 'spk_a', voice: { f0: 176, formants: [720, 1180, 2560], gain: 0.5 }, text: '同意。界面上的目标是"只需改专名，不用重听"。只要还有需要回听的段落，这一版就不算完成。' },
  { start: 41.2, end: 48.9, speaker: 'spk_d', voice: { f0: 224, formants: [780, 1400, 2900], gain: 0.42 }, text: '说到导出，现在只能出纯文本和字幕。客户那边经常还要一份带时间戳的逐字稿，用来做引用，最好能一键复制。' },
  { start: 49.5, end: 56.3, speaker: 'spk_b', voice: { f0: 208, formants: [660, 1720, 2410], gain: 0.46 }, text: '带时间戳的可以，纯文本也行。但我不希望界面上堆一大堆格式选项，选错了还得回头重跑。' },
  { start: 57.0, end: 63.7, speaker: 'spk_a', voice: { f0: 176, formants: [720, 1180, 2560], gain: 0.5 }, text: '格式是同一份数据的呈现，不涉及重跑。做成菜单，默认给最常用的两个，其余折叠起来。' },
  { start: 64.4, end: 71.2, speaker: 'spk_c', voice: { f0: 148, formants: [600, 1040, 2400], gain: 0.44 }, text: '前端这边，波形要能缩放，点击定位要准。我现在最烦的是改完一句话，位置就飘了，得重新找。' },
  { start: 71.8, end: 79.5, speaker: 'spk_a', voice: { f0: 176, formants: [720, 1180, 2560], gain: 0.5 }, text: '编辑不能动时间轴，改文字就只改文字。要调时间的话给单独的操作，而且必须能撤销。' },
  { start: 80.2, end: 87.6, speaker: 'spk_d', voice: { f0: 224, formants: [780, 1400, 2900], gain: 0.42 }, text: '还有一个：长录音的加载。八十多分钟的文件解码要几秒，界面上得有个真实的进度，别转个圈让人干等。' },
  { start: 88.3, end: 95.4, speaker: 'spk_b', voice: { f0: 208, formants: [660, 1720, 2410], gain: 0.46 }, text: '行，那这三点先落到这一版：低置信度标记、拆分导出、编辑不动时间轴。散会之前我把热词表更新一下。' },
];

export async function buildDemoAudio({ sampleRate = 44100 } = {}) {
  const duration = 96.5;
  const script = DEMO_SCRIPT.map((line) => ({
    ...line,
    voice: line.voice,
  }));
  const audio = await synthesizeSpeech({ sampleRate, duration, script });
  return { audio, meta: { title: '产品评审会 2026-09-24', source: '合成演示音频', engine: '本机合成', duration } };
}

export function demoDoc(duration) {
  return {
    meta: {
      title: '产品评审会 2026-09-24',
      duration,
      source: '合成演示音频',
      engine: '本机合成',
      createdAt: new Date().toISOString(),
    },
    segments: DEMO_SCRIPT.map((line, i) => ({
      id: `seg_demo_${i}`,
      start: line.start,
      end: line.end,
      speaker: line.speaker,
      text: line.text,
      // 人为压低两处置信度，让"待复核"这条路走得通
      confidence: [0.94, 0.68, 0.96, 0.88, 0.61, 0.95, 0.9, 0.86, 0.93, 0.71, 0.9, 0.97, 0.92][i] ?? 0.9,
      edited: false,
      flag: false,
    })),
  };
}
