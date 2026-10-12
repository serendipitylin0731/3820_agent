(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root && typeof root.document !== 'undefined') root.LibrarySearchHistory = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const KEY = '3820-library-search-history-v1';
  function normalize(items) {
    if (!Array.isArray(items)) return [];
    const result = [];
    for (const value of items) {
      if (typeof value !== 'string') continue;
      const term = value.trim().slice(0, 120);
      if (term && !result.some(item => item.toLowerCase() === term.toLowerCase())) result.push(term);
      if (result.length === 10) break;
    }
    return result;
  }
  function load(storage) {
    try { return normalize(JSON.parse(storage?.getItem(KEY) || '[]')); } catch (_) { return []; }
  }
  function save(storage, items, query) {
    const result = normalize([query, ...items]);
    try { storage?.setItem(KEY, JSON.stringify(result)); } catch (_) { /* local storage can be disabled */ }
    return result;
  }
  function clear(storage) {
    try { storage?.removeItem(KEY); } catch (_) { /* local storage can be disabled */ }
    return [];
  }
  return { load, save, clear };
});
