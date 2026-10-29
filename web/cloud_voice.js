(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.CloudVoice = api;
})(globalThis, function () {
  'use strict';

  function pcm16(input, rate) {
    const count = Math.floor(input.length * 16000 / rate);
    const output = new Int16Array(count);
    for (let i = 0; i < count; i += 1) {
      const from = Math.floor(i * rate / 16000);
      const to = Math.max(from + 1, Math.floor((i + 1) * rate / 16000));
      let sum = 0;
      for (let j = from; j < Math.min(to, input.length); j += 1) sum += input[j];
      const value = Math.max(-1, Math.min(1, sum / (to - from)));
      output[i] = value < 0 ? value * 32768 : value * 32767;
    }
    return output;
  }

  function createVoiceMode(options) {
    const supported = Boolean(options.secure && options.getUserMedia && options.AudioContext &&
      options.WebSocket && options.Audio && options.fetch);
    let enabled = false, epoch = 0, socket = null, stream = null, context = null;
    let source = null, processor = null, audio = null, audioUrl = null, aborter = null;
    let samples = [], elapsed = 0, silence = 0, heard = false, processing = false;
    const status = message => options.onStatus?.(message);

    function releaseCapture() {
      if (processor) { processor.onaudioprocess = null; processor.disconnect(); processor = null; }
      if (source) { source.disconnect(); source = null; }
      if (stream) { stream.getTracks().forEach(track => track.stop()); stream = null; }
      if (context) { context.close().catch(() => {}); context = null; }
      samples = [];
    }

    function releasePlayback() {
      if (aborter) { aborter.abort(); aborter = null; }
      if (audio) { audio.onended = null; audio.onerror = null; audio.pause(); audio = null; }
      if (audioUrl) { options.revokeObjectURL(audioUrl); audioUrl = null; }
    }

    function stop(message = '') {
      enabled = false; epoch += 1; processing = false;
      releaseCapture(); releasePlayback();
      if (socket) { socket.onclose = null; socket.onerror = null; socket.onmessage = null;
        socket.close(); socket = null; }
      options.onActiveChange?.(false);
      status(message);
    }

    async function speak(answer, run) {
      status('正在合成回答语音，文字已显示在页面上。');
      aborter = new AbortController();
      try {
        const response = await options.fetch('/voice/tts', {
          method: 'POST', headers: { 'Content-Type': 'application/json', ...options.getAuth() },
          body: JSON.stringify({ text: answer }), signal: aborter.signal,
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.error?.message || '语音合成失败');
        }
        const blob = await response.blob();
        if (!enabled || run !== epoch) return;
        audioUrl = options.createObjectURL(blob);
        audio = new options.Audio(audioUrl);
        audio.onended = () => {
          if (!enabled || run !== epoch) return;
          releasePlayback(); status('正在聆听，请继续提问。'); listen(run);
        };
        audio.onerror = () => stop('语音播放失败，文字回答仍可阅读。');
        status('正在播报回答，文字已显示在页面上。');
        await audio.play();
      } catch (error) {
        if (enabled && run === epoch)
          stop(`${error.message || '语音播报失败'}，文字回答仍可阅读。`);
      }
    }

    async function answerQuestion(text, run) {
      if (!enabled || run !== epoch) return;
      processing = true; releaseCapture(); socket = null;
      const question = String(text || '').trim();
      if (!question) { stop('没有听清，请重新开启语音对话。'); return; }
      status('已识别问题，正在查找资料。');
      try {
        const answer = await options.onRecognized(question);
        if (!enabled || run !== epoch) return;
        if (!answer) { stop('本轮未能生成回答，请重新提问。'); return; }
        await speak(answer, run);
      } catch (_) { if (enabled && run === epoch) stop('提问失败，请稍后重试。'); }
    }

    function finish() {
      if (processing || !socket || socket.readyState !== 1) return;
      processing = true; releaseCapture();
      socket.send(JSON.stringify({ type: 'finish' }));
      status('正在确认语音识别结果。');
    }

    function pushAudio(input) {
      if (!enabled || processing || !socket || socket.readyState !== 1) return;
      for (const sample of pcm16(input, context.sampleRate)) samples.push(sample);
      while (samples.length >= 3200) {
        const frame = samples.splice(0, 3200);
        if (socket.bufferedAmount > 1_000_000) { stop('语音连接过慢，请稍后重试。'); return; }
        socket.send(Int16Array.from(frame).buffer);
        const rms = Math.sqrt(frame.reduce((sum, value) => sum + value * value, 0) / 3200) / 32768;
        elapsed += 200;
        if (rms > 0.009) { heard = true; silence = 0; }
        else if (heard) silence += 200;
        if ((heard && silence >= 1400) || elapsed >= 35000) { finish(); return; }
        if (!heard && elapsed >= 15000) { stop('没有检测到说话，请重新开启语音对话。'); return; }
      }
    }

    async function listen(run) {
      if (!enabled || run !== epoch) return;
      processing = false; elapsed = 0; silence = 0; heard = false; samples = [];
      status('正在开启麦克风。');
      try {
        const opened = await options.getUserMedia({ audio: {
          echoCancellation: true, noiseSuppression: true, channelCount: 1,
        } });
        if (!enabled || run !== epoch) { opened.getTracks().forEach(track => track.stop()); return; }
        stream = opened;
        try { context = new options.AudioContext({ sampleRate: 16000 }); }
        catch (_) { context = new options.AudioContext(); }
        await context.resume();
        if (!enabled || run !== epoch) return;
        const scheme = options.location.protocol === 'https:' ? 'wss:' : 'ws:';
        socket = new options.WebSocket(`${scheme}//${options.location.host}/voice/asr`);
        socket.onopen = () => {
          if (!enabled || run !== epoch) return;
          socket.send(JSON.stringify({ type: 'auth', ...options.getAuthPayload() }));
          source = context.createMediaStreamSource(stream);
          processor = context.createScriptProcessor(4096, 1, 1);
          processor.onaudioprocess = event => {
            event.outputBuffer.getChannelData(0).fill(0);
            pushAudio(event.inputBuffer.getChannelData(0));
          };
          source.connect(processor); processor.connect(context.destination);
          status('正在聆听，请说出问题。');
        };
        socket.onmessage = event => {
          if (!enabled || run !== epoch) return;
          let data;
          try { data = JSON.parse(event.data); } catch (_) { return; }
          if (data.type === 'interim') options.onInterim?.(data.text);
          if (data.type === 'final') answerQuestion(data.text, run);
          if (data.type === 'error') stop(data.message || '语音识别失败。');
        };
        socket.onerror = () => stop('语音识别连接失败，请稍后重试。');
        socket.onclose = () => {
          if (enabled && run === epoch && !processing)
            stop('语音识别连接已断开，请稍后重试。');
        };
      } catch (error) {
        if (enabled && run === epoch)
          stop(error.name === 'NotAllowedError' ? '请允许浏览器使用麦克风。' :
            '无法启动麦克风，请检查浏览器权限。');
      }
    }

    function start() {
      if (!supported) {
        status(!options.secure ? '实时语音需要 HTTPS 或本机 localhost 地址。' :
          '当前浏览器不支持实时语音，请使用新版 Chrome 或 Edge。');
        return false;
      }
      if (enabled) return true;
      enabled = true; epoch += 1; options.onActiveChange?.(true);
      listen(epoch);
      return true;
    }

    return { start, stop, supported, get active() { return enabled; } };
  }

  return { createVoiceMode, pcm16 };
});
