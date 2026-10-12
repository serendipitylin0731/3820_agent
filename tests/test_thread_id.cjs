const test = require('node:test');
const assert = require('node:assert/strict');
const { createThreadId } = require('../web/app.js');

test('uses randomUUID when it is available', () => {
  assert.equal(createThreadId({ randomUUID: () => 'secure-context-id' }), 'secure-context-id');
});

test('creates distinct UUIDs on ordinary HTTP where randomUUID is unavailable', () => {
  let seed = 0;
  const cryptoSource = {
    getRandomValues(bytes) {
      for (let i = 0; i < bytes.length; i += 1) bytes[i] = seed++;
      return bytes;
    },
  };
  const first = createThreadId(cryptoSource);
  const second = createThreadId(cryptoSource);
  assert.match(first, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.notEqual(first, second);
});

test('still creates a thread ID if the browser exposes no crypto object', () => {
  assert.match(createThreadId(null), /^[0-9a-f-]{36}$/);
});
