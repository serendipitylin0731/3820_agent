const test = require('node:test');
const assert = require('node:assert/strict');
const { createVoiceMode } = require('../web/voice_mode.js');

function harness(onRecognized = async () => '回答包含背景。回答还说明实施过程。') {
  const recognitions = [];
  const spoken = [];
  const timers = [];
  const statuses = [];
  const states = [];
  class Recognition {
    constructor() { recognitions.push(this); }
    start() { this.started = true; }
    stop() { this.onend?.(); }
    abort() { this.aborted = true; }
  }
  class Utterance { constructor(text) { this.text = text; } }
  const synthesis = {
    speak: utterance => spoken.push(utterance),
    cancel: () => {},
    getVoices: () => [{ lang: 'zh-CN', name: 'Chinese voice' }],
  };
  const voice = createVoiceMode({ Recognition, Utterance, synthesis, secure: true,
    onRecognized, onStatus: status => statuses.push(status), onActiveChange: value => states.push(value),
    setTimeout: callback => { timers.push(callback); return timers.length; }, clearTimeout: () => {} });
  return { voice, recognitions, spoken, timers, statuses, states };
}

test('spoken question uses the answer callback, speaks its text, then listens again', async () => {
  const questions = [];
  const h = harness(async question => { questions.push(question); return '规划先明确阶段目标，再落实发展任务。'; });
  assert.equal(h.voice.start(), true);
  assert.equal(h.recognitions.length, 1);
  h.recognitions[0].onresult({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: '三个阶段是什么？' } }] });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(questions, ['三个阶段是什么？']);
  assert.equal(h.spoken[0].text, '规划先明确阶段目标，再落实发展任务。');
  assert.equal(h.spoken[0].lang, 'zh-CN');
  h.spoken[0].onend();
  h.timers.shift()();
  assert.equal(h.recognitions.length, 2);
  assert.equal(h.recognitions[1].started, true);
  h.voice.stop();
  assert.equal(h.states.at(-1), false);
});

test('stopping while an answer is pending prevents late speech and microphone restart', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const h = harness(() => pending);
  h.voice.start();
  h.recognitions[0].onresult({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: '问题' } }] });
  await new Promise(resolve => setImmediate(resolve));
  h.voice.stop();
  finish('这段回答不应被播报。');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.spoken.length, 0);
  assert.equal(h.timers.length, 0);
  assert.equal(h.recognitions.length, 1);
});

test('insecure public origin gives a clear message and does not request the microphone', () => {
  const messages = [];
  const voice = createVoiceMode({ secure: false, Recognition: class {}, Utterance: class {},
    synthesis: { cancel() {} }, onStatus: message => messages.push(message) });
  assert.equal(voice.start(), false);
  assert.match(messages.at(-1), /HTTPS/);
});
