(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.VoiceMode = api;
})(globalThis, function () {
  'use strict';

  function speechChunks(value, limit = 110) {
    const plain = String(value || '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/[*#`>]/g, '')
      .replace(/\s+/g, ' ').trim();
    const chunks = [];
    let current = '';
    for (const sentence of plain.match(/[^。！？；;]+[。！？；;]?/g) || []) {
      const part = sentence.trim();
      if (!part) continue;
      if (current && current.length + part.length > limit) {
        chunks.push(current);
        current = '';
      }
      for (let start = 0; start < part.length; start += limit) {
        const slice = part.slice(start, start + limit);
        if (start + limit < part.length) chunks.push(slice);
        else current += slice;
      }
    }
    if (current) chunks.push(current);
    return chunks;
  }

  function createVoiceMode(options) {
    const Recognition = options.Recognition;
    const Utterance = options.Utterance;
    const synthesis = options.synthesis;
    const secure = options.secure !== false;
    const later = options.setTimeout || setTimeout;
    const clear = options.clearTimeout || clearTimeout;
    const supported = Boolean(Recognition && Utterance && synthesis && secure);
    let enabled = false;
    let generation = 0;
    let recognition = null;
    let timer = null;
    let processing = false;
    let speaking = false;

    const status = message => options.onStatus?.(message);
    const active = value => options.onActiveChange?.(value);

    function cancelTimer() {
      if (timer !== null) clear(timer);
      timer = null;
    }

    function stop(message = '') {
      enabled = false;
      generation += 1;
      processing = false;
      speaking = false;
      cancelTimer();
      const old = recognition;
      recognition = null;
      if (old) {
        old.onresult = null;
        old.onend = null;
        old.onerror = null;
        try { old.abort(); } catch (_) { /* Already stopped. */ }
      }
      try { synthesis?.cancel(); } catch (_) { /* No speech engine is active. */ }
      active(false);
      status(message);
    }

    function queueListen() {
      if (!enabled) return;
      cancelTimer();
      timer = later(() => { timer = null; listen(); }, 500);
    }

    function speak(answer) {
      const chunks = speechChunks(answer);
      if (!chunks.length) {
        status('正在聆听，请继续提问。');
        queueListen();
        return;
      }
      speaking = true;
      status('正在播报回答，文字已显示在页面上。');
      const epoch = generation;
      const voices = typeof synthesis.getVoices === 'function' ? synthesis.getVoices() : [];
      const chineseVoice = voices.find(voice => /^zh[-_]CN$/i.test(voice.lang)) ||
        voices.find(voice => /^zh/i.test(voice.lang));
      let index = 0;
      function next() {
        if (!enabled || epoch !== generation) return;
        if (index >= chunks.length) {
          speaking = false;
          status('正在聆听，请继续提问。');
          queueListen();
          return;
        }
        const utterance = new Utterance(chunks[index++]);
        utterance.lang = 'zh-CN';
        utterance.rate = 1;
        if (chineseVoice) utterance.voice = chineseVoice;
        utterance.onend = next;
        utterance.onerror = () => {
          if (!enabled || epoch !== generation) return;
          speaking = false;
          status('语音播报失败，文字回答仍可阅读。正在重新聆听。');
          queueListen();
        };
        try { synthesis.speak(utterance); }
        catch (_) { utterance.onerror(); }
      }
      next();
    }

    function listen() {
      if (!enabled || processing || speaking || recognition) return;
      const epoch = generation;
      const current = new Recognition();
      let finalText = '';
      recognition = current;
      current.lang = 'zh-CN';
      current.continuous = false;
      current.interimResults = true;
      current.maxAlternatives = 1;
      current.onresult = event => {
        if (!enabled || epoch !== generation) return;
        let interim = '';
        for (let i = event.resultIndex || 0; i < event.results.length; i += 1) {
          const result = event.results[i];
          const phrase = result?.[0]?.transcript || '';
          if (result.isFinal) finalText += phrase;
          else interim += phrase;
        }
        options.onInterim?.((finalText + interim).trim());
        if (finalText.trim()) {
          status('已识别问题，正在查找资料。');
          try { current.stop(); } catch (_) { /* End event may already be queued. */ }
        }
      };
      current.onerror = event => {
        if (!enabled || epoch !== generation || event.error === 'no-speech') return;
        if (event.error === 'aborted' && finalText) return;
        const denied = event.error === 'not-allowed' || event.error === 'service-not-allowed';
        stop(denied ? '麦克风权限未开启，请允许浏览器使用麦克风。' : '语音识别暂不可用，请改用文字输入。');
      };
      current.onend = () => {
        if (!enabled || epoch !== generation) return;
        recognition = null;
        const question = finalText.trim();
        if (!question) {
          status('没有听清，正在继续聆听。');
          queueListen();
          return;
        }
        processing = true;
        Promise.resolve().then(() => options.onRecognized(question)).then(answer => {
          processing = false;
          if (!enabled || epoch !== generation) return;
          if (answer) speak(answer);
          else {
            status('本轮未能生成语音回答，正在继续聆听。');
            queueListen();
          }
        }).catch(() => {
          processing = false;
          if (!enabled || epoch !== generation) return;
          status('提问失败，正在继续聆听。');
          queueListen();
        });
      };
      try {
        current.start();
        status('正在聆听，请说出问题。');
      } catch (_) {
        stop('无法启动麦克风，请检查浏览器权限。');
      }
    }

    function start() {
      if (!supported) {
        status(!secure ? '语音对话需要 HTTPS 或本机 localhost 地址。' :
          '当前浏览器不支持语音识别与合成，请改用文字输入。');
        return false;
      }
      if (enabled) return true;
      enabled = true;
      generation += 1;
      active(true);
      try { synthesis.cancel(); } catch (_) { /* Nothing to cancel. */ }
      listen();
      return enabled;
    }

    return { start, stop, supported, get active() { return enabled; } };
  }

  return { createVoiceMode, speechChunks };
});
