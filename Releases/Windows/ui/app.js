(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  const elements = {
    fileName: $("#fileName"),
    fileMeta: $("#fileMeta"),
    importButton: $("#importButton"),
    waveformStage: $("#waveformStage"),
    waveformCanvas: $("#waveformCanvas"),
    playbackHead: $("#playbackHead"),
    playPauseButton: $("#playPauseButton"),
    stopButton: $("#stopButton"),
    previewCutButton: $("#previewCutButton"),
    playbackCurrent: $("#playbackCurrent"),
    playbackTotal: $("#playbackTotal"),
    emptyState: $("#emptyState"),
    loadingState: $("#loadingState"),
    offsetInput: $("#offsetInput"),
    decreaseOffset: $("#decreaseOffset"),
    increaseOffset: $("#increaseOffset"),
    sourceDuration: $("#sourceDuration"),
    outputDuration: $("#outputDuration"),
    resetButton: $("#resetButton"),
    sampleRate: $("#sampleRateSelect"),
    channels: $("#channelsSelect"),
    bitDepth: $("#bitDepthSelect"),
    bitrate: $("#bitrateSelect"),
    format: $("#formatSelect"),
    antiClick: $("#antiClickToggle"),
    fade: $("#fadeSelect"),
    fadeField: $("#fadeField"),
    normalize: $("#normalizeToggle"),
    filename: $("#filenameInput"),
    filenameExtension: $("#filenameExtension"),
    estimatedSize: $("#estimatedSize"),
    exportButton: $("#exportButton"),
    statusText: $("#statusText"),
    statusDot: $(".status-dot"),
    progressFill: $("#progressFill"),
    ffmpegStatus: $("#ffmpegStatus"),
    motionButton: $("#motionButton"),
    themeButton: $("#themeButton"),
    revealOutputButton: $("#revealOutputButton"),
    minimizeButton: $("#minimizeButton"),
    maximizeButton: $("#maximizeButton"),
    closeButton: $("#closeButton"),
    toastRegion: $("#toastRegion"),
    offsetTaskTab: $("#offsetTaskTab"),
    convertTaskTab: $("#convertTaskTab"),
    offsetView: $("#offsetView"),
    converterView: $("#converterView"),
    converterFileName: $("#converterFileName"),
    converterFileMeta: $("#converterFileMeta"),
    converterImportButton: $("#converterImportButton"),
    converterStage: $("#converterStage"),
    converterWaveformCanvas: $("#converterWaveformCanvas"),
    converterEmptyState: $("#converterEmptyState"),
    converterLoadingState: $("#converterLoadingState"),
    bpmMeasureButton: $("#bpmMeasureButton"),
    bpmButtonStatus: $("#bpmButtonStatus"),
    bpmButtonValue: $("#bpmButtonValue"),
    converterSourceFormat: $("#converterSourceFormat"),
    converterTargetFormat: $("#converterTargetFormat"),
    converterEstimatedSize: $("#converterEstimatedSize"),
    converterFormat: $("#converterFormatSelect"),
    converterSampleRate: $("#converterSampleRateSelect"),
    converterChannels: $("#converterChannelsSelect"),
    converterBitDepth: $("#converterBitDepthSelect"),
    converterBitrate: $("#converterBitrateSelect"),
    converterNormalize: $("#converterNormalizeToggle"),
    converterFilename: $("#converterFilenameInput"),
    converterFilenameExtension: $("#converterFilenameExtension"),
    convertButton: $("#convertButton"),
    ncmDialog: $("#ncmConfirmDialog"),
    ncmDialogFile: $("#ncmDialogFile"),
    cancelNcmButton: $("#cancelNcmButton"),
    confirmNcmButton: $("#confirmNcmButton"),
    bpmDialog: $("#bpmDialog"),
    bpmDialogFile: $("#bpmDialogFile"),
    bpmProgressPanel: $("#bpmProgressPanel"),
    bpmProgressMessage: $("#bpmProgressMessage"),
    bpmProgressValue: $("#bpmProgressValue"),
    bpmProgressFill: $("#bpmProgressFill"),
    bpmResults: $("#bpmResults"),
    bpmResultValue: $("#bpmResultValue"),
    bpmResultConfidence: $("#bpmResultConfidence"),
    bpmResultDuration: $("#bpmResultDuration"),
    bpmResultSegmentCount: $("#bpmResultSegmentCount"),
    bpmResultBeatCount: $("#bpmResultBeatCount"),
    bpmSegmentList: $("#bpmSegmentList"),
    bpmCandidateList: $("#bpmCandidateList"),
    bpmResultNote: $("#bpmResultNote"),
    bpmDismissButton: $("#bpmDismissButton"),
  };

  const state = {
    backend: null,
    config: null,
    audio: null,
    action: "trim",
    exporting: false,
    converting: false,
    activeTool: "offset",
    bpm: null,
    bpmMeasuring: false,
    pendingNcmPath: null,
    progress: 0,
    theme: document.documentElement.dataset.theme || "dark",
    playbackState: "stopped",
    playbackPositionMs: 0,
    playbackDurationMs: 0,
    scrubbing: false,
  };
  window.__xmaoState = state;

  class MockSignal {
    constructor() {
      this.listeners = [];
    }
    connect(listener) {
      this.listeners.push(listener);
    }
    emit(...args) {
      this.listeners.forEach((listener) => listener(...args));
    }
  }

  function mockAudio() {
    const points = 520;
    const left = [];
    const right = [];
    for (let index = 0; index < points; index += 1) {
      const envelope = Math.min(1, index / 70) * Math.min(1, (points - index) / 34);
      const base = Math.abs(Math.sin(index * 0.37) * 0.36 + Math.sin(index * 0.083) * 0.31);
      left.push(Math.min(0.95, (0.16 + base) * envelope));
      right.push(Math.min(0.9, (0.14 + Math.abs(Math.sin(index * 0.31 + 1.3)) * 0.58) * envelope));
    }
    return {
      path: "C:/Music/ouroboros -twin stroke of the end-.wav",
      name: "ouroboros -twin stroke of the end-.wav",
      stem: "ouroboros -twin stroke of the end-",
      sourceFormat: "wav",
      durationMs: 308230,
      sampleRate: 44100,
      channels: 2,
      bitDepth: 16,
      bitrateKbps: 1411,
      frameCount: 13592943,
      waveform: [left, right],
    };
  }

  class MockBackend {
    constructor() {
      this.audioLoaded = new MockSignal();
      this.audioLoadFailed = new MockSignal();
      this.exportProgress = new MockSignal();
      this.exportFinished = new MockSignal();
      this.exportFailed = new MockSignal();
      this.conversionProgress = new MockSignal();
      this.conversionFinished = new MockSignal();
      this.conversionFailed = new MockSignal();
      this.bpmAnalysisStarted = new MockSignal();
      this.bpmAnalysisProgress = new MockSignal();
      this.bpmDetected = new MockSignal();
      this.bpmAnalysisFailed = new MockSignal();
      this.ncmConfirmationRequested = new MockSignal();
      this.ncmProgress = new MockSignal();
      this.ncmConverted = new MockSignal();
      this.ncmConversionFailed = new MockSignal();
      this.windowStateChanged = new MockSignal();
      this.playbackChanged = new MockSignal();
      this.playbackPositionChanged = new MockSignal();
      this.playbackFailed = new MockSignal();
      this.notice = new MockSignal();
      this.playbackTimer = null;
    }
    getInitialState(callback) {
      callback(JSON.stringify({
        ok: true,
        ffmpegPath: "project-local/ffmpeg.exe",
        outputDirectory: "Output",
        formats: [
          { value: "mp3", label: "MP3", bitrates: [128, 192, 256, 320], defaultBitrate: 320, lossless: false },
          { value: "wav", label: "WAV (PCM)", bitrates: [], defaultBitrate: 0, lossless: true },
          { value: "flac", label: "FLAC", bitrates: [], defaultBitrate: 0, lossless: true },
          { value: "ogg", label: "OGG Vorbis", bitrates: [96, 128, 192, 256, 320, 500], defaultBitrate: 256, lossless: false },
          { value: "m4a", label: "M4A (AAC)", bitrates: [96, 128, 192, 256, 320], defaultBitrate: 256, lossless: false },
          { value: "aac", label: "AAC", bitrates: [96, 128, 192, 256, 320], defaultBitrate: 256, lossless: false },
          { value: "wma", label: "WMA", bitrates: [96, 128, 192, 256, 320], defaultBitrate: 192, lossless: false },
          { value: "aiff", label: "AIFF (PCM)", bitrates: [], defaultBitrate: 0, lossless: true },
          { value: "opus", label: "Opus", bitrates: [64, 96, 128, 160, 192, 256, 320, 512], defaultBitrate: 192, lossless: false },
        ],
        sampleRates: [22050, 32000, 44100, 48000, 88200, 96000, 192000],
        channels: [1, 2, 6, 8],
        bitDepths: [8, 16, 24, 32],
        maximized: false,
        platform: navigator.platform.toLowerCase().includes("mac") ? "macos" : "windows",
      }));
    }
    browseAudio(callback) {
      callback(JSON.stringify({ ok: true, pending: true, name: "ouroboros -twin stroke of the end-.wav" }));
      setTimeout(() => {
        this.audioLoaded.emit(JSON.stringify(mockAudio()));
      }, 420);
    }
    loadAudio(_path, callback) {
      this.browseAudio(callback);
    }
    exportAudio(_payload, callback) {
      callback(JSON.stringify({ ok: true, pending: true, outputPath: "Output/mock.wav" }));
      let progress = 0;
      const timer = setInterval(() => {
        progress += 8;
        this.exportProgress.emit(progress, progress < 66 ? "正在处理音频" : "正在编码导出");
        if (progress >= 100) {
          clearInterval(timer);
          this.exportFinished.emit("Output/ouroboros_edited.wav");
        }
      }, 80);
    }
    convertAudio(_payload, callback) {
      callback(JSON.stringify({ ok: true, pending: true, outputPath: "Output/mock.mp3" }));
      let progress = 0;
      const timer = setInterval(() => {
        progress += 10;
        this.conversionProgress.emit(progress, progress < 60 ? "正在应用输出参数" : "正在编码转换");
        if (progress >= 100) {
          clearInterval(timer);
          this.conversionFinished.emit("Output/ouroboros_converted.mp3");
        }
      }, 70);
    }
    convertNcm(path, callback) {
      callback(JSON.stringify({ ok: true, pending: true, outputPath: "Output/mock.wav" }));
      let progress = 0;
      const timer = setInterval(() => {
        progress += 20;
        this.ncmProgress.emit(progress, progress < 60 ? "正在解密 NCM 音频" : "正在转换为 WAV");
        if (progress >= 100) {
          clearInterval(timer);
          this.ncmConverted.emit("Output/mock.wav");
          this.audioLoaded.emit(JSON.stringify({ ...mockAudio(), path, name: "Rubbish Sorting.wav", stem: "Rubbish Sorting" }));
        }
      }, 100);
    }
    measureBpm(callback) {
      callback(JSON.stringify({ ok: true, pending: true }));
      this.bpmAnalysisStarted.emit("ouroboros -twin stroke of the end-.wav");
      const stages = [
        [12, "正在解码音频"], [30, "移除静音并增强节奏瞬态"], [51, "分析节奏片段 2/5"],
        [72, "分析节奏片段 4/5"], [86, "汇总候选 BPM 并校正拍层级"], [100, "BPM 分析完成"],
      ];
      let index = 0;
      const timer = setInterval(() => {
        const [progress, message] = stages[index++];
        this.bpmAnalysisProgress.emit(progress, message);
        if (index === stages.length) {
          clearInterval(timer);
          this.bpmDetected.emit(JSON.stringify({
            bpm: 174.18,
            confidence: 91,
            beatCount: 882,
            analysisDurationMs: 180000,
            segmentCount: 5,
            isVariableTempo: false,
            segments: [{ startMs: 4200, endMs: 177800, bpm: 174.18, confidence: 96, beatCount: 882 }],
            candidates: [{ bpm: 174.18, label: "推荐拍层" }, { bpm: 87.09, label: "半速候选" }],
            method: "多片段节拍回归",
          }));
        }
      }, 180);
    }
    revealOutput(callback) { callback(JSON.stringify({ ok: true })); }
    playFrom(position, callback) {
      this.playbackPosition = Number(position) || 0;
      clearInterval(this.playbackTimer);
      this.playbackChanged.emit("playing");
      this.playbackPositionChanged.emit(this.playbackPosition, mockAudio().durationMs);
      this.playbackTimer = setInterval(() => {
        this.playbackPosition += 100;
        if (this.playbackPosition >= mockAudio().durationMs) {
          this.playbackPosition = mockAudio().durationMs;
          clearInterval(this.playbackTimer);
          this.playbackChanged.emit("stopped");
        }
        this.playbackPositionChanged.emit(this.playbackPosition, mockAudio().durationMs);
      }, 100);
      callback(JSON.stringify({ ok: true, positionMs: this.playbackPosition }));
    }
    pausePlayback(callback) {
      clearInterval(this.playbackTimer);
      this.playbackChanged.emit("paused");
      callback(JSON.stringify({ ok: true }));
    }
    stopPlayback(callback) {
      clearInterval(this.playbackTimer);
      this.playbackPosition = 0;
      this.playbackChanged.emit("stopped");
      this.playbackPositionChanged.emit(0, mockAudio().durationMs);
      callback(JSON.stringify({ ok: true }));
    }
    seekPlayback(position, callback) {
      this.playbackPosition = Number(position) || 0;
      this.playbackPositionChanged.emit(this.playbackPosition, mockAudio().durationMs);
      callback(JSON.stringify({ ok: true, positionMs: this.playbackPosition }));
    }
    setWindowTheme() {}
    minimizeWindow() {}
    toggleMaximize() { this.windowStateChanged.emit(false); }
    closeWindow() {}
  }

  function callBackend(method, ...args) {
    return new Promise((resolve, reject) => {
      if (!state.backend || typeof state.backend[method] !== "function") {
        reject(new Error(`Backend method unavailable: ${method}`));
        return;
      }
      state.backend[method](...args, (result) => {
        try {
          resolve(typeof result === "string" ? JSON.parse(result) : result);
        } catch (error) {
          reject(error);
        }
      });
    });
  }

  function setStatus(message, mode = "ready", progress = null) {
    elements.statusText.textContent = message;
    elements.statusDot.className = `status-dot is-${mode}`;
    if (progress !== null) {
      state.progress = Math.max(0, Math.min(100, Number(progress)));
      elements.progressFill.style.transform = `scaleX(${state.progress / 100})`;
      window.fluidBackground?.setProgress(state.progress);
    }
  }

  function themeColor(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function applyTheme(theme, persist = true) {
    const normalized = theme === "light" ? "light" : "dark";
    state.theme = normalized;
    document.documentElement.dataset.theme = normalized;
    if (persist) localStorage.setItem("xmao-theme", normalized);
    const nextLabel = normalized === "dark" ? "切换到浅色主题" : "切换到深色主题";
    elements.themeButton.title = nextLabel;
    elements.themeButton.setAttribute("aria-label", nextLabel);
    window.fluidBackground?.setTheme(normalized);
    state.backend?.setWindowTheme?.(normalized);
    requestAnimationFrame(() => {
      renderWaveform();
      renderConverterWaveform();
    });
  }

  function showToast(title, message, error = false) {
    const toast = document.createElement("div");
    toast.className = `toast${error ? " is-error" : ""}`;
    const icon = document.createElement("div");
    icon.innerHTML = error
      ? '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 4h.01"/></svg>'
      : '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>';
    const copy = document.createElement("div");
    const heading = document.createElement("strong");
    const body = document.createElement("span");
    heading.textContent = title;
    body.textContent = message;
    copy.append(heading, body);
    toast.append(icon, copy);
    elements.toastRegion.append(toast);
    setTimeout(() => toast.remove(), 4200);
  }

  function formatDuration(milliseconds) {
    if (!Number.isFinite(milliseconds) || milliseconds < 0) return "--:--.---";
    const total = Math.round(milliseconds);
    const minutes = Math.floor(total / 60000);
    const seconds = Math.floor((total % 60000) / 1000);
    const ms = total % 1000;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
  }

  function formatBpmRange(milliseconds) {
    return formatDuration(Number(milliseconds)).slice(0, 5);
  }

  function bpmConfidenceLabel(confidence) {
    const value = Number(confidence) || 0;
    if (value >= 80) return "高可信";
    if (value >= 60) return "中等可信";
    return "低可信，建议试听确认";
  }

  function setBpmProgress(progress, message) {
    const normalized = Math.max(0, Math.min(100, Number(progress) || 0));
    elements.bpmProgressMessage.textContent = message || "正在分析节奏";
    elements.bpmProgressValue.textContent = `${Math.round(normalized)}%`;
    elements.bpmProgressFill.style.transform = `scaleX(${normalized / 100})`;
  }

  function resetBpmDialog() {
    elements.bpmProgressPanel.hidden = false;
    elements.bpmResults.hidden = true;
    elements.bpmSegmentList.replaceChildren();
    elements.bpmCandidateList.replaceChildren();
    elements.bpmResultNote.textContent = "";
    elements.bpmDismissButton.disabled = true;
    setBpmProgress(0, "正在准备分析");
  }

  function resultRow(primary, secondary) {
    const row = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("strong");
    label.textContent = primary;
    value.textContent = secondary;
    row.append(label, value);
    return row;
  }

  function renderBpmResult(result) {
    const bpm = Number(result.bpm) || 0;
    const confidence = Math.max(0, Math.min(100, Number(result.confidence) || 0));
    state.bpm = result;
    elements.bpmButtonValue.textContent = bpm ? bpm.toFixed(2) : "--.-";
    elements.bpmButtonStatus.textContent = bpm ? `${bpmConfidenceLabel(confidence)} · ${result.segmentCount || 0} 个片段` : "未检测到稳定 BPM";
    elements.bpmResultValue.textContent = bpm ? bpm.toFixed(2) : "--.-";
    elements.bpmResultConfidence.textContent = `${bpmConfidenceLabel(confidence)} · ${Math.round(confidence)}%`;
    elements.bpmResultDuration.textContent = formatBpmRange(result.analysisDurationMs);
    elements.bpmResultSegmentCount.textContent = `${result.segmentCount || 0} 个`;
    elements.bpmResultBeatCount.textContent = Number(result.beatCount || 0).toLocaleString();
    elements.bpmSegmentList.replaceChildren();
    (result.segments || []).forEach((segment) => {
      const range = `${formatBpmRange(segment.startMs)} - ${formatBpmRange(segment.endMs)}`;
      const bpmText = `${Number(segment.bpm).toFixed(2)} BPM · ${Math.round(Number(segment.confidence) || 0)}%`;
      elements.bpmSegmentList.append(resultRow(range, bpmText));
    });
    elements.bpmCandidateList.replaceChildren();
    (result.candidates || []).forEach((candidate) => {
      elements.bpmCandidateList.append(resultRow(candidate.label || "候选", `${Number(candidate.bpm).toFixed(2)} BPM`));
    });
    elements.bpmResultNote.textContent = result.isVariableTempo
      ? "检测到可能的变速段，主 BPM 是可信度最高的拍层候选。"
      : `各局部片段节奏一致，结果由 ${result.method || "多片段节拍回归"} 得出。`;
    elements.bpmProgressPanel.hidden = true;
    elements.bpmResults.hidden = false;
    elements.bpmDismissButton.disabled = false;
  }

  async function startBpmMeasurement() {
    if (!state.audio || state.bpmMeasuring) return;
    state.bpmMeasuring = true;
    elements.bpmMeasureButton.disabled = true;
    elements.bpmMeasureButton.classList.add("is-measuring");
    elements.bpmDialogFile.textContent = state.audio.name;
    resetBpmDialog();
    if (!elements.bpmDialog.open) elements.bpmDialog.showModal();
    try {
      const result = await callBackend("measureBpm");
      if (!result.ok) {
        throw new Error(result.error || "无法启动 BPM 分析。");
      }
    } catch (error) {
      state.bpmMeasuring = false;
      elements.bpmMeasureButton.disabled = !state.audio;
      elements.bpmMeasureButton.classList.remove("is-measuring");
      if (elements.bpmDialog.open) elements.bpmDialog.close();
      showToast("无法测量 BPM", error.message, true);
    }
  }

  function updatePlaybackUi() {
    const hasAudio = Boolean(state.audio);
    const duration = state.playbackDurationMs || state.audio?.durationMs || 0;
    const position = Math.max(0, Math.min(state.playbackPositionMs, duration));
    const playing = state.playbackState === "playing";
    elements.playPauseButton.disabled = !hasAudio;
    elements.stopButton.disabled = !hasAudio;
    elements.previewCutButton.disabled = !hasAudio;
    elements.playPauseButton.classList.toggle("is-playing", playing);
    elements.playPauseButton.setAttribute("aria-label", playing ? "暂停" : "播放");
    elements.playPauseButton.title = playing ? "暂停" : "从播放头开始播放";
    elements.playbackCurrent.textContent = formatDuration(position);
    elements.playbackTotal.textContent = hasAudio ? formatDuration(duration) : "--:--.---";
    elements.playbackHead.hidden = !hasAudio;
    elements.waveformStage.classList.toggle("is-playing", playing);
    if (hasAudio && duration > 0) {
      const width = elements.waveformStage.clientWidth;
      const plotWidth = Math.max(1, width - 56);
      const headX = 44 + plotWidth * (position / duration);
      elements.playbackHead.style.transform = `translateX(${headX}px)`;
      elements.waveformStage.setAttribute(
        "aria-label",
        `音频波形，播放位置 ${formatDuration(position)}，可拖动定位`,
      );
    }
  }

  function playbackPositionFromPointer(event) {
    if (!state.audio) return 0;
    const rect = elements.waveformStage.getBoundingClientRect();
    const x = Math.max(44, Math.min(rect.width - 12, event.clientX - rect.left));
    const ratio = (x - 44) / Math.max(1, rect.width - 56);
    return Math.round(ratio * state.audio.durationMs);
  }

  function setLocalPlaybackPosition(positionMs) {
    const duration = state.audio?.durationMs || state.playbackDurationMs || 0;
    state.playbackPositionMs = Math.max(0, Math.min(Number(positionMs) || 0, duration));
    updatePlaybackUi();
  }

  function finishPlaybackScrub(event) {
    if (!state.scrubbing) return;
    state.scrubbing = false;
    if (event?.pointerId !== undefined && elements.waveformStage.hasPointerCapture(event.pointerId)) {
      elements.waveformStage.releasePointerCapture(event.pointerId);
    }
    seekPlayback(state.playbackPositionMs);
  }

  async function seekPlayback(positionMs) {
    setLocalPlaybackPosition(positionMs);
    try {
      await callBackend("seekPlayback", Math.round(state.playbackPositionMs));
    } catch (error) {
      showToast("无法定位播放位置", error.message, true);
    }
  }

  async function togglePlayback() {
    if (!state.audio) return;
    try {
      if (state.playbackState === "playing") {
        await callBackend("pausePlayback");
      } else {
        const duration = state.audio.durationMs;
        const start = state.playbackPositionMs >= duration - 1 ? 0 : state.playbackPositionMs;
        setLocalPlaybackPosition(start);
        await callBackend("playFrom", Math.round(start));
      }
    } catch (error) {
      showToast("无法播放", error.message, true);
    }
  }

  async function previewFromCut() {
    if (!state.audio) return;
    const cutPosition = state.action === "trim"
      ? Math.min(state.audio.durationMs - 1, Math.round(currentOffsetSeconds() * 1000))
      : 0;
    setLocalPlaybackPosition(cutPosition);
    try {
      await callBackend("playFrom", cutPosition);
    } catch (error) {
      showToast("无法试听", error.message, true);
    }
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "--";
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
    if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  function channelLabel(channels) {
    return ({ 1: "单声道", 2: "立体声", 6: "5.1 声道", 8: "7.1 声道" })[channels] || `${channels} 声道`;
  }

  function setSelectOptions(select, values, formatter, selected) {
    select.replaceChildren();
    values.forEach((value) => {
      const option = document.createElement("option");
      const optionValue = typeof value === "object" && value !== null ? value.value : value;
      option.value = String(optionValue);
      option.textContent = formatter(value);
      select.append(option);
    });
    const availableValues = values.map((value) => String(
      typeof value === "object" && value !== null ? value.value : value,
    ));
    if (selected !== undefined && availableValues.includes(String(selected))) {
      select.value = String(selected);
    }
  }

  function initializeControls(config) {
    state.config = config;
    document.documentElement.dataset.platform = config.platform || "windows";
    document.documentElement.classList.toggle("is-maximized", Boolean(config.maximized));
    elements.maximizeButton.title = config.maximized ? "还原" : "最大化";
    elements.maximizeButton.setAttribute("aria-label", config.maximized ? "还原" : "最大化");
    setSelectOptions(elements.sampleRate, config.sampleRates, (value) => `${Number(value).toLocaleString()} Hz`, 44100);
    setSelectOptions(elements.channels, config.channels, channelLabel, 2);
    setSelectOptions(elements.bitDepth, config.bitDepths, (value) => `${value}-bit`, 16);
    setSelectOptions(elements.format, config.formats, (value) => value.label, undefined);
    elements.format.value = "wav";
    refreshFormatControls();
    setSelectOptions(elements.converterSampleRate, config.sampleRates, (value) => `${Number(value).toLocaleString()} Hz`, 44100);
    setSelectOptions(elements.converterChannels, config.channels, channelLabel, 2);
    setSelectOptions(elements.converterBitDepth, config.bitDepths, (value) => `${value}-bit`, 16);
    setSelectOptions(elements.converterFormat, config.formats, (value) => value.label, "mp3");
    elements.converterFormat.value = "mp3";
    refreshConverterFormatControls();
    elements.ffmpegStatus.textContent = config.ffmpegPath ? "FFmpeg 已就绪" : "FFmpeg 不可用";
  }

  function currentFormatProfile() {
    return state.config?.formats.find((profile) => profile.value === elements.format.value);
  }

  function refreshFormatControls(preserveBitrate = false) {
    const profile = currentFormatProfile();
    if (!profile) return;
    const previous = elements.bitrate.value;
    if (profile.lossless) {
      setSelectOptions(elements.bitrate, [0], () => "不适用", 0);
      elements.bitrate.disabled = true;
    } else {
      const selected = preserveBitrate && profile.bitrates.map(String).includes(previous)
        ? Number(previous)
        : profile.defaultBitrate;
      setSelectOptions(elements.bitrate, profile.bitrates, (value) => `${value} kbps`, selected);
      elements.bitrate.disabled = false;
    }
    elements.filenameExtension.textContent = `.${profile.value}`;
    updateDerivedState();
  }

  function currentConverterFormatProfile() {
    return state.config?.formats.find((profile) => profile.value === elements.converterFormat.value);
  }

  function refreshConverterFormatControls(preserveBitrate = false) {
    const profile = currentConverterFormatProfile();
    if (!profile) return;
    const previous = elements.converterBitrate.value;
    if (profile.lossless) {
      setSelectOptions(elements.converterBitrate, [0], () => "不适用", 0);
      elements.converterBitrate.disabled = true;
    } else {
      const selected = preserveBitrate && profile.bitrates.map(String).includes(previous)
        ? Number(previous)
        : profile.defaultBitrate;
      setSelectOptions(elements.converterBitrate, profile.bitrates, (value) => `${value} kbps`, selected);
      elements.converterBitrate.disabled = false;
    }
    elements.converterFilenameExtension.textContent = `.${profile.value}`;
    elements.converterTargetFormat.textContent = profile.label;
    updateConverterState();
  }

  function converterEstimatedBytes() {
    if (!state.audio) return 0;
    const seconds = state.audio.durationMs / 1000;
    const format = elements.converterFormat.value;
    const sampleRate = Number(elements.converterSampleRate.value);
    const channels = Number(elements.converterChannels.value);
    const bitDepth = Number(elements.converterBitDepth.value);
    if (format === "wav" || format === "aiff") {
      return seconds * sampleRate * channels * Math.max(1, bitDepth / 8);
    }
    if (format === "flac") {
      return seconds * sampleRate * channels * Math.max(1, bitDepth / 8) * 0.58;
    }
    return seconds * Math.max(1, Number(elements.converterBitrate.value)) * 1000 / 8;
  }

  function updateConverterState() {
    elements.converterEstimatedSize.textContent = state.audio ? formatBytes(converterEstimatedBytes()) : "--";
    elements.convertButton.disabled = !state.audio || state.converting;
  }

  function selectTool(tool) {
    state.activeTool = tool;
    const converterActive = tool === "convert";
    elements.offsetView.hidden = converterActive;
    elements.converterView.hidden = !converterActive;
    elements.offsetTaskTab.classList.toggle("is-active", !converterActive);
    elements.convertTaskTab.classList.toggle("is-active", converterActive);
    elements.offsetTaskTab.setAttribute("aria-selected", String(!converterActive));
    elements.convertTaskTab.setAttribute("aria-selected", String(converterActive));
    window.fluidBackground?.setMode(converterActive ? "convert" : state.action);
    if (converterActive) {
      requestAnimationFrame(renderConverterWaveform);
    } else {
      requestAnimationFrame(renderWaveform);
    }
  }

  function currentOffsetSeconds() {
    const value = Number.parseFloat(elements.offsetInput.value);
    return Number.isFinite(value) ? Math.max(0.001, Math.min(3600, value)) : 0.5;
  }

  function outputDurationMs() {
    if (!state.audio) return 0;
    const offset = Math.round(currentOffsetSeconds() * 1000);
    return state.action === "trim"
      ? Math.max(0, state.audio.durationMs - offset)
      : state.audio.durationMs + offset;
  }

  function estimatedBytes() {
    if (!state.audio) return 0;
    const durationSeconds = outputDurationMs() / 1000;
    const format = elements.format.value;
    const sampleRate = Number(elements.sampleRate.value);
    const channels = Number(elements.channels.value);
    const bitDepth = Number(elements.bitDepth.value);
    if (format === "wav" || format === "aiff") {
      return durationSeconds * sampleRate * channels * Math.max(1, bitDepth / 8);
    }
    if (format === "flac") {
      return durationSeconds * sampleRate * channels * Math.max(1, bitDepth / 8) * 0.58;
    }
    return durationSeconds * Math.max(1, Number(elements.bitrate.value)) * 1000 / 8;
  }

  function updateDerivedState(normalizeInput = true) {
    const offset = currentOffsetSeconds();
    if (normalizeInput) elements.offsetInput.value = offset.toFixed(3);
    elements.sourceDuration.textContent = state.audio ? formatDuration(state.audio.durationMs) : "--:--.---";
    elements.outputDuration.textContent = state.audio ? formatDuration(outputDurationMs()) : "--:--.---";
    elements.estimatedSize.textContent = state.audio ? formatBytes(estimatedBytes()) : "--";
    elements.exportButton.disabled = !state.audio || state.exporting || (state.action === "trim" && offset * 1000 >= state.audio.durationMs);
    elements.fade.disabled = !elements.antiClick.checked;
    elements.fadeField.classList.toggle("is-disabled", !elements.antiClick.checked);
  }

  function applyAudio(data) {
    state.audio = data;
    state.bpm = null;
    state.bpmMeasuring = false;
    state.playbackState = "stopped";
    state.playbackPositionMs = 0;
    state.playbackDurationMs = data.durationMs;
    const metadata = `${data.sourceFormat.toUpperCase()} · ${Number(data.sampleRate).toLocaleString()} Hz · ${channelLabel(data.channels)} · ${data.bitDepth}-bit · ${data.bitrateKbps} kbps · ${formatDuration(data.durationMs)}`;
    elements.fileName.textContent = data.name;
    elements.fileMeta.textContent = metadata;
    elements.converterFileName.textContent = data.name;
    elements.converterFileMeta.textContent = metadata;
    elements.sampleRate.value = String(data.sampleRate);
    if (!Array.from(elements.sampleRate.options).some((option) => option.value === String(data.sampleRate))) {
      const option = new Option(`${Number(data.sampleRate).toLocaleString()} Hz`, String(data.sampleRate));
      elements.sampleRate.add(option);
      elements.sampleRate.value = String(data.sampleRate);
    }
    elements.channels.value = String(data.channels);
    elements.bitDepth.value = String(data.bitDepth);
    elements.format.value = state.config.formats.some((profile) => profile.value === data.sourceFormat) ? data.sourceFormat : "wav";
    refreshFormatControls();
    if (!elements.bitrate.disabled && Array.from(elements.bitrate.options).some((option) => option.value === String(data.bitrateKbps))) {
      elements.bitrate.value = String(data.bitrateKbps);
    }
    elements.filename.value = `${data.stem}_edited`;
    [elements.converterSampleRate, elements.converterChannels, elements.converterBitDepth].forEach((select) => {
      const value = select === elements.converterSampleRate
        ? data.sampleRate
        : select === elements.converterChannels ? data.channels : data.bitDepth;
      if (!Array.from(select.options).some((option) => option.value === String(value))) {
        const label = select === elements.converterSampleRate
          ? `${Number(value).toLocaleString()} Hz`
          : select === elements.converterChannels ? channelLabel(value) : `${value}-bit`;
        select.add(new Option(label, String(value)));
      }
      select.value = String(value);
    });
    const converterTarget = data.sourceFormat === "mp3" ? "wav" : "mp3";
    elements.converterFormat.value = converterTarget;
    elements.converterFilename.value = `${data.stem}_converted`;
    elements.converterSourceFormat.textContent = data.sourceFormat.toUpperCase();
    refreshConverterFormatControls();
    elements.waveformStage.classList.remove("is-empty");
    elements.converterStage.classList.remove("is-empty");
    elements.emptyState.hidden = true;
    elements.loadingState.hidden = true;
    elements.converterEmptyState.hidden = true;
    elements.converterLoadingState.hidden = true;
    elements.bpmMeasureButton.disabled = false;
    elements.bpmMeasureButton.classList.remove("is-measuring");
    elements.bpmButtonValue.textContent = "--.-";
    elements.bpmButtonStatus.textContent = "可开始测量节拍与局部速度";
    renderWaveform();
    renderConverterWaveform();
    updateDerivedState();
    updateConverterState();
    updatePlaybackUi();
    setStatus(`已载入 ${data.name}`, "ready", 0);
  }

  function setLoading(name) {
    elements.fileName.textContent = name || "正在读取音频";
    elements.fileMeta.textContent = "分析格式、参数和波形";
    elements.converterFileName.textContent = name || "正在读取音频";
    elements.converterFileMeta.textContent = "分析格式、参数、波形与节拍";
    elements.emptyState.hidden = true;
    elements.loadingState.hidden = false;
    elements.converterEmptyState.hidden = true;
    elements.converterLoadingState.hidden = false;
    setStatus("正在分析音频", "busy", 8);
  }

  function renderWaveform() {
    const canvas = elements.waveformCanvas;
    const rect = canvas.getBoundingClientRect();
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.floor(rect.width * scale));
    const height = Math.max(1, Math.floor(rect.height * scale));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, width, height);
    if (!state.audio?.waveform) return;

    const leftPad = 44 * scale;
    const topPad = 26 * scale;
    const bottomPad = 16 * scale;
    const plotWidth = width - leftPad - 12 * scale;
    const plotHeight = height - topPad - bottomPad;
    const channelHeight = plotHeight / 2;

    context.strokeStyle = themeColor("--wave-grid");
    context.lineWidth = Math.max(1, scale * 0.6);
    for (let line = 0; line <= 8; line += 1) {
      const x = leftPad + plotWidth * (line / 8);
      context.beginPath();
      context.moveTo(x, topPad);
      context.lineTo(x, height - bottomPad);
      context.stroke();
    }
    context.beginPath();
    context.moveTo(leftPad, topPad + channelHeight);
    context.lineTo(width - 12 * scale, topPad + channelHeight);
    context.stroke();

    context.fillStyle = themeColor("--wave-label");
    context.font = `${10 * scale}px "Segoe UI", sans-serif`;
    context.textAlign = "center";
    for (let line = 0; line <= 4; line += 1) {
      const fraction = line / 4;
      const x = leftPad + plotWidth * fraction;
      context.fillText(formatDuration(state.audio.durationMs * fraction).slice(0, 5), x, 16 * scale);
    }
    context.textAlign = "center";
    context.fillText("L", 22 * scale, topPad + channelHeight * 0.52);
    context.fillText("R", 22 * scale, topPad + channelHeight * 1.52);

    state.audio.waveform.slice(0, 2).forEach((peaks, channel) => {
      const centerY = topPad + channelHeight * (channel + 0.5);
      const amplitude = channelHeight * 0.39;
      context.beginPath();
      context.moveTo(leftPad, centerY);
      peaks.forEach((peak, index) => {
        const x = leftPad + plotWidth * (index / Math.max(1, peaks.length - 1));
        context.lineTo(x, centerY - peak * amplitude);
      });
      for (let index = peaks.length - 1; index >= 0; index -= 1) {
        const x = leftPad + plotWidth * (index / Math.max(1, peaks.length - 1));
        context.lineTo(x, centerY + peaks[index] * amplitude);
      }
      context.closePath();
      context.fillStyle = themeColor(channel === 0 ? "--wave-primary" : "--wave-secondary");
      context.fill();
    });

    const offsetRatio = Math.min(1, currentOffsetSeconds() * 1000 / state.audio.durationMs);
    const markerX = state.action === "trim" ? leftPad + plotWidth * offsetRatio : leftPad;
    context.strokeStyle = themeColor("--timing-blue");
    context.lineWidth = 2 * scale;
    context.beginPath();
    context.moveTo(markerX, topPad);
    context.lineTo(markerX, height - bottomPad);
    context.stroke();
    if (state.action === "trim" && offsetRatio > 0) {
      context.fillStyle = themeColor("--timeline-fill");
      context.fillRect(leftPad, topPad, markerX - leftPad, plotHeight);
    }
  }

  function renderConverterWaveform() {
    const canvas = elements.converterWaveformCanvas;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.floor(rect.width * scale));
    const height = Math.max(1, Math.floor(rect.height * scale));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, width, height);
    if (!state.audio?.waveform) return;

    const left = 20 * scale;
    const right = 12 * scale;
    const top = 24 * scale;
    const bottom = 14 * scale;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const channelHeight = plotHeight / 2;
    context.strokeStyle = themeColor("--wave-grid");
    context.lineWidth = Math.max(1, scale * 0.6);
    for (let line = 0; line <= 8; line += 1) {
      const x = left + plotWidth * (line / 8);
      context.beginPath();
      context.moveTo(x, top);
      context.lineTo(x, height - bottom);
      context.stroke();
    }
    context.beginPath();
    context.moveTo(left, top + channelHeight);
    context.lineTo(width - right, top + channelHeight);
    context.stroke();

    context.fillStyle = themeColor("--wave-label");
    context.font = `${9 * scale}px "Segoe UI", sans-serif`;
    context.textAlign = "center";
    for (let line = 0; line <= 4; line += 1) {
      const fraction = line / 4;
      context.fillText(formatDuration(state.audio.durationMs * fraction).slice(0, 5), left + plotWidth * fraction, 15 * scale);
    }

    state.audio.waveform.slice(0, 2).forEach((peaks, channel) => {
      const centerY = top + channelHeight * (channel + 0.5);
      const amplitude = channelHeight * 0.36;
      context.beginPath();
      peaks.forEach((peak, index) => {
        const x = left + plotWidth * (index / Math.max(1, peaks.length - 1));
        const y = centerY - peak * amplitude;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      for (let index = peaks.length - 1; index >= 0; index -= 1) {
        const x = left + plotWidth * (index / Math.max(1, peaks.length - 1));
        context.lineTo(x, centerY + peaks[index] * amplitude);
      }
      context.closePath();
      context.fillStyle = themeColor(channel === 0 ? "--wave-primary" : "--wave-secondary");
      context.fill();
    });
  }

  function selectAction(action) {
    state.action = action;
    $$(".segment").forEach((button) => {
      const selected = button.dataset.action === action;
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    window.fluidBackground?.setMode(action);
    updateDerivedState();
    renderWaveform();
  }

  async function browseAudio() {
    try {
      const result = await callBackend("browseAudio");
      if (result.ok && result.pending) setLoading(result.name);
      else if (result.error) showToast("无法导入", result.error, true);
    } catch (error) {
      showToast("无法导入", error.message, true);
    }
  }

  async function startExport() {
    if (!state.audio || state.exporting) return;
    if (state.action === "trim" && currentOffsetSeconds() * 1000 >= state.audio.durationMs) {
      showToast("参数无效", "删除时间必须小于音频总时长。", true);
      return;
    }
    if (!elements.filename.value.trim()) {
      showToast("文件名无效", "请输入输出文件名。", true);
      elements.filename.focus();
      return;
    }

    const payload = {
      action: state.action,
      seconds: currentOffsetSeconds(),
      sampleRate: Number(elements.sampleRate.value),
      channels: Number(elements.channels.value),
      bitDepth: Number(elements.bitDepth.value),
      bitrateKbps: Number(elements.bitrate.value),
      format: elements.format.value,
      antiClick: elements.antiClick.checked,
      fadeMs: Number(elements.fade.value),
      normalize: elements.normalize.checked,
      filename: elements.filename.value.trim(),
    };

    try {
      const result = await callBackend("exportAudio", JSON.stringify(payload));
      if (!result.ok) {
        showToast("无法导出", result.error || "导出参数无效。", true);
        return;
      }
      state.exporting = true;
      elements.exportButton.disabled = true;
      elements.exportButton.querySelector("span").textContent = "正在导出";
      setStatus("正在准备导出", "busy", 2);
    } catch (error) {
      showToast("无法导出", error.message, true);
    }
  }

  async function startConversion() {
    if (!state.audio || state.converting) return;
    if (!elements.converterFilename.value.trim()) {
      showToast("文件名无效", "请输入输出文件名。", true);
      elements.converterFilename.focus();
      return;
    }
    const payload = {
      sampleRate: Number(elements.converterSampleRate.value),
      channels: Number(elements.converterChannels.value),
      bitDepth: Number(elements.converterBitDepth.value),
      bitrateKbps: Number(elements.converterBitrate.value),
      format: elements.converterFormat.value,
      normalize: elements.converterNormalize.checked,
      filename: elements.converterFilename.value.trim(),
    };
    try {
      const result = await callBackend("convertAudio", JSON.stringify(payload));
      if (!result.ok) {
        showToast("无法转换", result.error || "转换参数无效。", true);
        return;
      }
      state.converting = true;
      elements.convertButton.querySelector("span").textContent = "正在转换";
      updateConverterState();
      setStatus("正在准备格式转换", "busy", 2);
    } catch (error) {
      showToast("无法转换", error.message, true);
    }
  }

  function requestNcmConfirmation(path, name) {
    state.pendingNcmPath = path;
    elements.ncmDialogFile.textContent = name;
    selectTool("convert");
    if (!elements.ncmDialog.open) elements.ncmDialog.showModal();
  }

  async function confirmNcmConversion() {
    if (!state.pendingNcmPath || state.converting) return;
    const path = state.pendingNcmPath;
    state.pendingNcmPath = null;
    elements.ncmDialog.close("confirm");
    try {
      const result = await callBackend("convertNcm", path);
      if (!result.ok) {
        showToast("NCM 转换失败", result.error || "无法启动 NCM 转换。", true);
        return;
      }
      state.converting = true;
      elements.converterFileName.textContent = path.replaceAll("\\", "/").split("/").pop();
      elements.converterFileMeta.textContent = "正在解密 NCM 容器并生成 WAV";
      elements.converterEmptyState.hidden = true;
      elements.converterLoadingState.hidden = false;
      updateConverterState();
      setStatus("正在读取 NCM", "busy", 2);
    } catch (error) {
      showToast("NCM 转换失败", error.message, true);
    }
  }

  function connectSignals(backend) {
    backend.audioLoaded.connect((payload) => {
      try {
        applyAudio(JSON.parse(payload));
      } catch (error) {
        showToast("音频数据错误", error.message, true);
      }
    });
    backend.audioLoadFailed.connect((message) => {
      elements.loadingState.hidden = true;
      elements.converterLoadingState.hidden = true;
      elements.emptyState.hidden = !elements.waveformStage.classList.contains("is-empty");
      elements.converterEmptyState.hidden = !elements.converterStage.classList.contains("is-empty");
      setStatus("音频读取失败", "error", 0);
      showToast("读取失败", message, true);
    });
    backend.exportProgress.connect((progress, message) => {
      setStatus(`${message} · ${progress}%`, "busy", progress);
    });
    backend.exportFinished.connect((outputPath) => {
      state.exporting = false;
      elements.exportButton.querySelector("span").textContent = "开始导出";
      updateDerivedState();
      setStatus("导出完成", "ready", 100);
      showToast("导出完成", outputPath);
      setTimeout(() => setStatus("准备就绪", "ready", 0), 1800);
    });
    backend.exportFailed.connect((message) => {
      state.exporting = false;
      elements.exportButton.querySelector("span").textContent = "开始导出";
      updateDerivedState();
      setStatus("导出失败", "error", 0);
      showToast("导出失败", message, true);
    });
    backend.conversionProgress.connect((progress, message) => {
      setStatus(`${message} · ${progress}%`, "busy", progress);
    });
    backend.conversionFinished.connect((outputPath) => {
      state.converting = false;
      elements.convertButton.querySelector("span").textContent = "开始转换";
      updateConverterState();
      setStatus("格式转换完成", "ready", 100);
      showToast("转换完成", outputPath);
      setTimeout(() => setStatus("准备就绪", "ready", 0), 1800);
    });
    backend.conversionFailed.connect((message) => {
      state.converting = false;
      elements.convertButton.querySelector("span").textContent = "开始转换";
      updateConverterState();
      setStatus("格式转换失败", "error", 0);
      showToast("转换失败", message, true);
    });
    backend.bpmAnalysisStarted.connect((name) => {
      state.bpm = null;
      state.bpmMeasuring = true;
      elements.bpmMeasureButton.disabled = true;
      elements.bpmMeasureButton.classList.add("is-measuring");
      elements.bpmDialogFile.textContent = name || state.audio?.name || "当前音频";
      resetBpmDialog();
      setBpmProgress(2, "正在准备 BPM 分析");
      if (!elements.bpmDialog.open) elements.bpmDialog.showModal();
    });
    backend.bpmAnalysisProgress.connect((progress, message) => {
      setBpmProgress(progress, message);
    });
    backend.bpmDetected.connect((payload) => {
      try {
        const result = JSON.parse(payload);
        state.bpmMeasuring = false;
        elements.bpmMeasureButton.disabled = !state.audio;
        elements.bpmMeasureButton.classList.remove("is-measuring");
        renderBpmResult(result);
        setStatus("BPM 分析完成", "ready", 100);
      } catch (error) {
        showToast("BPM 数据错误", error.message, true);
      }
    });
    backend.bpmAnalysisFailed.connect((message) => {
      state.bpmMeasuring = false;
      elements.bpmMeasureButton.disabled = !state.audio;
      elements.bpmMeasureButton.classList.remove("is-measuring");
      elements.bpmButtonStatus.textContent = "未检测到稳定 BPM";
      elements.bpmDismissButton.disabled = false;
      setBpmProgress(100, "BPM 分析未完成");
      setStatus("BPM 分析未完成", "error", 0);
      showToast("BPM 分析未完成", message, true);
    });
    backend.ncmConfirmationRequested.connect(requestNcmConfirmation);
    backend.ncmProgress.connect((progress, message) => {
      setStatus(`${message} · ${progress}%`, "busy", progress);
    });
    backend.ncmConverted.connect((outputPath) => {
      state.converting = false;
      updateConverterState();
      const name = outputPath.replaceAll("\\", "/").split("/").pop();
      setLoading(name);
      selectTool("convert");
      showToast("NCM 已转换为 WAV", name);
    });
    backend.ncmConversionFailed.connect((message) => {
      state.converting = false;
      elements.converterLoadingState.hidden = true;
      elements.converterEmptyState.hidden = !elements.converterStage.classList.contains("is-empty");
      updateConverterState();
      setStatus("NCM 转换失败", "error", 0);
      showToast("NCM 转换失败", message, true);
    });
    backend.windowStateChanged.connect((maximized) => {
      elements.maximizeButton.title = maximized ? "还原" : "最大化";
      elements.maximizeButton.setAttribute("aria-label", maximized ? "还原" : "最大化");
      document.documentElement.classList.toggle("is-maximized", Boolean(maximized));
    });
    backend.playbackChanged.connect((playbackState) => {
      state.playbackState = playbackState;
      updatePlaybackUi();
    });
    backend.playbackPositionChanged.connect((positionMs, durationMs) => {
      if (state.scrubbing) return;
      state.playbackPositionMs = Number(positionMs) || 0;
      state.playbackDurationMs = Number(durationMs) || state.audio?.durationMs || 0;
      updatePlaybackUi();
    });
    backend.playbackFailed.connect((message) => {
      state.playbackState = "stopped";
      updatePlaybackUi();
      showToast("播放失败", message, true);
    });
    backend.notice.connect((title, message) => showToast(title, message, true));
  }

  async function initializeBackend(backend) {
    state.backend = backend;
    connectSignals(backend);
    try {
      const config = await callBackend("getInitialState");
      initializeControls(config);
      applyTheme(state.theme, false);
      setStatus("准备就绪", "ready", 0);
      if (new URLSearchParams(window.location.search).get("mock") === "loaded") {
        applyAudio(mockAudio());
      }
    } catch (error) {
      setStatus("环境初始化失败", "error", 0);
      showToast("初始化失败", error.message, true);
    }
  }

  function loadBackend() {
    if (window.qt?.webChannelTransport) {
      const script = document.createElement("script");
      script.src = "qrc:///qtwebchannel/qwebchannel.js";
      script.onload = () => new window.QWebChannel(window.qt.webChannelTransport, (channel) => initializeBackend(channel.objects.backend));
      script.onerror = () => initializeBackend(new MockBackend());
      document.head.append(script);
    } else {
      initializeBackend(new MockBackend());
    }
  }

  elements.importButton.addEventListener("click", browseAudio);
  elements.converterImportButton.addEventListener("click", browseAudio);
  elements.offsetTaskTab.addEventListener("click", () => selectTool("offset"));
  elements.convertTaskTab.addEventListener("click", () => selectTool("convert"));
  elements.waveformStage.addEventListener("click", (event) => {
    if (!state.audio) browseAudio();
    else if (!state.scrubbing) seekPlayback(playbackPositionFromPointer(event));
  });
  elements.waveformStage.addEventListener("keydown", (event) => {
    if (!state.audio && (event.key === "Enter" || event.key === " ")) {
      browseAudio();
      return;
    }
    if (!state.audio) return;
    if (event.key === " ") {
      event.preventDefault();
      togglePlayback();
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const direction = event.key === "ArrowLeft" ? -1 : 1;
      seekPlayback(state.playbackPositionMs + direction * (event.shiftKey ? 10000 : 1000));
    }
  });
  elements.waveformStage.addEventListener("pointerdown", (event) => {
    if (!state.audio || event.button !== 0) return;
    state.scrubbing = true;
    elements.waveformStage.setPointerCapture(event.pointerId);
    setLocalPlaybackPosition(playbackPositionFromPointer(event));
  });
  elements.waveformStage.addEventListener("pointermove", (event) => {
    if (!state.scrubbing) return;
    setLocalPlaybackPosition(playbackPositionFromPointer(event));
  });
  elements.waveformStage.addEventListener("pointerup", (event) => {
    finishPlaybackScrub(event);
  });
  elements.waveformStage.addEventListener("pointercancel", finishPlaybackScrub);
  elements.waveformStage.addEventListener("lostpointercapture", finishPlaybackScrub);
  elements.converterStage.addEventListener("click", () => {
    if (!state.audio) browseAudio();
  });
  elements.converterStage.addEventListener("keydown", (event) => {
    if (!state.audio && (event.key === "Enter" || event.key === " ")) browseAudio();
  });
  $$(".segment").forEach((button) => button.addEventListener("click", () => selectAction(button.dataset.action)));
  elements.decreaseOffset.addEventListener("click", () => {
    elements.offsetInput.value = Math.max(0.001, currentOffsetSeconds() - 0.01).toFixed(3);
    updateDerivedState();
    renderWaveform();
  });
  elements.increaseOffset.addEventListener("click", () => {
    elements.offsetInput.value = Math.min(3600, currentOffsetSeconds() + 0.01).toFixed(3);
    updateDerivedState();
    renderWaveform();
  });
  elements.offsetInput.addEventListener("input", () => {
    updateDerivedState(false);
    renderWaveform();
  });
  elements.offsetInput.addEventListener("change", updateDerivedState);
  elements.offsetInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      updateDerivedState();
      renderWaveform();
      elements.offsetInput.select();
    }
  });
  elements.resetButton.addEventListener("click", () => {
    elements.offsetInput.value = "0.500";
    selectAction("trim");
  });
  [elements.sampleRate, elements.channels, elements.bitDepth, elements.bitrate].forEach((element) => element.addEventListener("change", updateDerivedState));
  elements.format.addEventListener("change", () => refreshFormatControls());
  elements.antiClick.addEventListener("change", updateDerivedState);
  elements.playPauseButton.addEventListener("click", togglePlayback);
  elements.stopButton.addEventListener("click", () => callBackend("stopPlayback").catch((error) => showToast("无法停止", error.message, true)));
  elements.previewCutButton.addEventListener("click", previewFromCut);
  elements.exportButton.addEventListener("click", startExport);
  elements.convertButton.addEventListener("click", startConversion);
  elements.bpmMeasureButton.addEventListener("click", startBpmMeasurement);
  elements.bpmDismissButton.addEventListener("click", () => {
    if (!state.bpmMeasuring) elements.bpmDialog.close();
  });
  elements.bpmDialog.addEventListener("cancel", (event) => {
    if (state.bpmMeasuring) {
      event.preventDefault();
      showToast("BPM 正在分析", "分析完成后可关闭此窗口。", false);
    }
  });
  elements.converterFormat.addEventListener("change", () => refreshConverterFormatControls());
  [elements.converterSampleRate, elements.converterChannels, elements.converterBitDepth, elements.converterBitrate]
    .forEach((element) => element.addEventListener("change", updateConverterState));
  elements.confirmNcmButton.addEventListener("click", (event) => {
    event.preventDefault();
    confirmNcmConversion();
  });
  elements.cancelNcmButton.addEventListener("click", () => {
    state.pendingNcmPath = null;
  });
  elements.motionButton.addEventListener("click", () => {
    const next = !window.fluidBackground?.isEnabled();
    window.fluidBackground?.setEnabled(next);
    elements.motionButton.setAttribute("aria-pressed", String(next));
  });
  elements.themeButton.addEventListener("click", () => {
    applyTheme(state.theme === "dark" ? "light" : "dark");
  });
  elements.revealOutputButton.addEventListener("click", () => callBackend("revealOutput").catch((error) => showToast("无法打开", error.message, true)));
  elements.minimizeButton.addEventListener("click", () => state.backend?.minimizeWindow());
  elements.maximizeButton.addEventListener("click", () => state.backend?.toggleMaximize());
  elements.closeButton.addEventListener("click", () => state.backend?.closeWindow());

  ["dragenter", "dragover"].forEach((type) => document.addEventListener(type, (event) => {
    event.preventDefault();
    elements.waveformStage.classList.add("is-dragging");
    elements.converterStage.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach((type) => document.addEventListener(type, (event) => {
    event.preventDefault();
    elements.waveformStage.classList.remove("is-dragging");
    elements.converterStage.classList.remove("is-dragging");
  }));
  document.addEventListener("drop", (event) => {
    if (!window.qt && event.dataTransfer?.files?.length) {
      const file = event.dataTransfer.files[0];
      if (file.name.toLowerCase().endsWith(".ncm")) {
        requestNcmConfirmation(file.name, file.name);
      } else {
        setLoading(file.name);
        setTimeout(() => applyAudio({ ...mockAudio(), name: file.name }), 350);
      }
    }
  });

  const resizeObserver = new ResizeObserver(() => {
    renderWaveform();
    renderConverterWaveform();
    updatePlaybackUi();
  });
  resizeObserver.observe(elements.waveformStage);
  resizeObserver.observe(elements.converterStage);
  elements.motionButton.setAttribute("aria-pressed", String(window.fluidBackground?.isEnabled() ?? false));
  applyTheme(state.theme, false);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
    if (!localStorage.getItem("xmao-theme")) applyTheme(event.matches ? "dark" : "light", false);
  });
  selectTool("offset");
  selectAction("trim");
  loadBackend();
})();
