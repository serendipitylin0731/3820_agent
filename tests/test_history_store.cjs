const test = require('node:test');
const assert = require('node:assert/strict');
const history = require('../web/history_store.js');

function memoryStorage() {
  const values = new Map();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
}

function turn(index, threadId = 'thread-a') {
  return {
    threadId,
    question: `问题 ${index}`,
    createdAt: `2026-10-11T00:00:${String(index % 60).padStart(2, '0')}Z`,
    payload: {
      answer: `回答 ${index}`,
      status: 'ok',
      results: { planning: { sources: [{ source_file: 'https://example.com/source', verified: false }] } },
    },
  };
}

test('restores only the latest 30 question-answer turns after reload', () => {
  const storage = memoryStorage();
  let turns = history.load(storage);
  for (let i = 0; i < 35; i += 1) turns = history.saveTurn(storage, turns, turn(i));
  const reloaded = history.load(storage);
  assert.equal(reloaded.length, 30);
  assert.equal(reloaded[0].question, '问题 5');
  assert.equal(reloaded.at(-1).payload.answer, '回答 34');
  assert.equal(reloaded[0].payload.results.planning.sources[0].verified, undefined);
});

test('groups saved turns by conversation and clears browser storage', () => {
  const storage = memoryStorage();
  let turns = history.saveTurn(storage, [], turn(1, 'first'));
  turns = history.saveTurn(storage, turns, turn(2, 'second'));
  turns = history.saveTurn(storage, turns, turn(3, 'first'));
  const conversations = history.conversations(history.load(storage));
  assert.deepEqual(conversations.map(item => [item.threadId, item.count]), [['first', 2], ['second', 1]]);
  history.clear(storage);
  assert.deepEqual(history.load(storage), []);
});

test('invalid or unavailable storage leaves chat history usable in memory', () => {
  const broken = { getItem: () => '{bad json', setItem: () => { throw Error('quota'); } };
  assert.deepEqual(history.load(broken), []);
  const turns = history.saveTurn(broken, [], turn(1));
  assert.equal(turns.length, 1);
  assert.deepEqual(history.load(null), []);
});
