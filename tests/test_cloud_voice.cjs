const test = require('node:test');
const assert = require('node:assert/strict');
const { createVoiceMode, pcm16 } = require('../web/cloud_voice.js');

const tick = () => new Promise(resolve => setImmediate(resolve));

function harness(onRecognized = async () => '检索后的回答保留在页面。') {
  const sockets = [], contexts = [], tracks = [], sounds = [], calls = [], statuses = [];
  class Socket {
    constructor(url) { this.url = url; this.readyState = 1; this.sent = []; sockets.push(this); }
    send(value) { this.sent.push(value); }
    close() { this.readyState = 3; }
  }
  class Context {
    constructor() { this.sampleRate = 16000; contexts.push(this); }
    async resume() {}
    async close() {}
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createScriptProcessor() {
      this.processor = { connect() {}, disconnect() {} };
      return this.processor;
    }
  }
  class Audio {
    constructor(url) { this.url = url; sounds.push(this); }
    async play() { this.played = true; }
    pause() { this.paused = true; }
  }
  const voice = createVoiceMode({
    secure: true, WebSocket: Socket, AudioContext: Context, Audio,
    location: { protocol: 'https:', host: 'example.org' },
    getUserMedia: async () => {
      const track = { stopped: false, stop() { this.stopped = true; } };
      tracks.push(track);
      return { getTracks: () => [track] };
    },
    fetch: async (path, request) => {
      calls.push({ path, request });
      return { ok: true, blob: async () => ({ mp3: true }) };
    },
    createObjectURL: () => 'blob:answer', revokeObjectURL: () => {},
    getAuth: () => ({ 'X-API-Key': 'site-password' }),
    getAuthPayload: () => ({ service_key: 'site-password', client_id: '' }),
    onRecognized, onStatus: message => statuses.push(message),
  });
  return { voice, sockets, contexts, tracks, sounds, calls, statuses };
}

test('PCM conversion keeps audio signed and downsamples to 16 kHz', () => {
  assert.deepEqual([...pcm16(Float32Array.from([1, 1, -1, -1]), 32000)], [32767, -32768]);
});

test('live audio is sent to server ASR, its transcript enters chat, and TTS plays answer', async () => {
  const questions = [];
  const h = harness(async question => { questions.push(question); return '资料显示三个阶段逐步推进。'; });
  assert.equal(h.voice.start(), true);
  await tick(); await tick();
  assert.equal(h.sockets.length, 1);
  assert.equal(h.sockets[0].url, 'wss://example.org/voice/asr');
  h.sockets[0].onopen();
  assert.equal(JSON.parse(h.sockets[0].sent[0]).service_key, 'site-password');
  const buffer = new Float32Array(4096).fill(0.12);
  h.contexts[0].processor.onaudioprocess({ inputBuffer: { getChannelData: () => buffer },
    outputBuffer: { getChannelData: () => new Float32Array(4096) } });
  assert.ok(h.sockets[0].sent[1] instanceof ArrayBuffer);
  h.sockets[0].onmessage({ data: JSON.stringify({ type: 'final', text: '三个阶段是什么？' }) });
  await tick(); await tick();
  assert.deepEqual(questions, ['三个阶段是什么？']);
  assert.equal(h.calls[0].path, '/voice/tts');
  assert.equal(JSON.parse(h.calls[0].request.body).text, '资料显示三个阶段逐步推进。');
  assert.equal(h.sounds[0].played, true);
  h.sounds[0].onended();
  await tick(); await tick();
  assert.equal(h.sockets.length, 2);
  h.voice.stop();
  assert.equal(h.tracks.every(track => track.stopped), true);
});

test('HTTP public page cannot start microphone and says why', () => {
  const statuses = [];
  const voice = createVoiceMode({ secure: false, onStatus: value => statuses.push(value) });
  assert.equal(voice.start(), false);
  assert.match(statuses.at(-1), /HTTPS/);
});
