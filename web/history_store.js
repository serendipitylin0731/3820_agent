(() => {
  'use strict';

  const KEY = '3820-chat-history-v1';
  const LIMIT = 30;
  const LEGACY_PREFIX = '知识库资料中暂未查找到，以下是豆包模型提供的参考回答：';
  const MODEL_NOTE = '知识库没有找到直接匹配的资料；此回答由豆包模型补充，未附资料来源。';

  function normalizeTurn(value) {
    if (!value || typeof value !== 'object') return null;
    if (typeof value.threadId !== 'string' || !value.threadId ||
        typeof value.question !== 'string' || !value.question.trim() ||
        !value.payload || typeof value.payload.answer !== 'string') return null;
    const legacy = value.payload.answer.startsWith(LEGACY_PREFIX);
    const results = {};
    for (const [name, result] of Object.entries(value.payload.results || {})) {
      if (!result || typeof result !== 'object') continue;
      results[name] = {
        sources: Array.isArray(result.sources) ? result.sources.slice(0, 60).map(source => ({
          source_file: String(source?.source_file || ''),
          section: source?.section == null ? '' : String(source.section),
          page_or_slide: source?.page_or_slide == null ? '' : String(source.page_or_slide),
          data_version: source?.data_version == null ? '' : String(source.data_version),
        })) : [],
      };
    }
    return {
      threadId: value.threadId,
      question: value.question.trim().slice(0, 4000),
      createdAt: typeof value.createdAt === 'string' ? value.createdAt : new Date().toISOString(),
      payload: {
        answer: legacy ? value.payload.answer.slice(LEGACY_PREFIX.length) : value.payload.answer,
        status: typeof value.payload.status === 'string' ? value.payload.status : 'ok',
        request_id: typeof value.payload.request_id === 'string' ? value.payload.request_id : '',
        notice: legacy ? MODEL_NOTE :
          typeof value.payload.notice === 'string' ? value.payload.notice.slice(0, 300) : '',
        results,
      },
    };
  }

  function load(storage) {
    try {
      const data = JSON.parse(storage?.getItem(KEY) || 'null');
      if (!data || data.version !== 1 || !Array.isArray(data.turns)) return [];
      return data.turns.map(normalizeTurn).filter(Boolean).slice(-LIMIT);
    } catch (_) {
      return [];
    }
  }

  function saveTurn(storage, turns, value) {
    const turn = normalizeTurn(value);
    if (!turn) return turns.slice(-LIMIT);
    const updated = [...turns, turn].slice(-LIMIT);
    const candidate = [...updated];
    while (candidate.length) {
      try {
        storage?.setItem(KEY, JSON.stringify({ version: 1, turns: candidate }));
        return candidate;
      } catch (_) {
        candidate.shift();
      }
    }
    return updated;
  }

  function clear(storage) {
    try { storage?.removeItem(KEY); } catch (_) { /* browser storage may be unavailable */ }
    return [];
  }

  function conversations(turns) {
    const grouped = new Map();
    for (const turn of turns) {
      if (!grouped.has(turn.threadId)) grouped.set(turn.threadId, {
        threadId: turn.threadId, title: turn.question, count: 0, updatedAt: turn.createdAt,
      });
      const conversation = grouped.get(turn.threadId);
      conversation.count += 1;
      conversation.updatedAt = turn.createdAt;
      grouped.delete(turn.threadId);
      grouped.set(turn.threadId, conversation);
    }
    return [...grouped.values()].reverse();
  }

  const api = { KEY, LIMIT, load, saveTurn, clear, conversations };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.ChatHistory = api;
})();
