const { test } = require('node:test');
const assert = require('node:assert/strict');
const history = require('../web/search_history.js');

test('keeps ten distinct recent search terms and restores them', () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key) };
  let items = [];
  for (let i = 0; i < 12; i += 1) items = history.save(storage, items, `资料${i}`);
  assert.equal(items.length, 10);
  assert.equal(items[0], '资料11');
  items = history.save(storage, items, '资料5');
  assert.equal(items[0], '资料5');
  assert.equal(new Set(items).size, 10);
  assert.deepEqual(history.load(storage), items);
  assert.deepEqual(history.clear(storage), []);
  assert.deepEqual(history.load(storage), []);
});
