(() => {
  'use strict';

  const form = document.querySelector('#chat-form');
  const questionInput = document.querySelector('#question');
  const sendButton = document.querySelector('#send');
  const messages = document.querySelector('#messages');
  const welcome = document.querySelector('#welcome');
  const settingsDialog = document.querySelector('#settings-dialog');
  const backgroundToggle = document.querySelector('#background-toggle');
  const backgroundDocument = document.querySelector('#background-document');
  const conversation = document.querySelector('#conversation');
  const composer = document.querySelector('#composer-wrap');
  const historyList = document.querySelector('#history-list');
  const historyEmpty = document.querySelector('#history-empty');
  const clearHistory = document.querySelector('#clear-history');
  const historyStore = window.ChatHistory;
  let storage;
  try { storage = window.localStorage; } catch (_) { storage = null; }
  let savedTurns = historyStore.load(storage);
  let threadId = crypto.randomUUID();
  let busy = false;
  let serviceKey = '';
  let clientId = '';

  function make(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function scrollToLatest() {
    requestAnimationFrame(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' }));
  }

  function newMessage(kind, label) {
    const article = make('article', `message ${kind}`);
    const meta = make('div', 'message-meta');
    meta.append(make('span', 'avatar', kind === 'user' ? '我' : '✦'), document.createTextNode(label));
    const body = make('div', 'message-body');
    article.append(meta, body);
    messages.append(article);
    return { article, body };
  }

  function collectSources(results) {
    const unique = new Map();
    for (const result of Object.values(results || {})) {
      for (const source of result.sources || []) {
        const id = [source.source_file, source.page_or_slide, source.section, source.data_version].join('|');
        unique.set(id, source);
      }
    }
    return [...unique.values()];
  }

  function sourceLink(file) {
    if (!/^https?:\/\//i.test(file)) return document.createTextNode(file);
    try {
      const url = new URL(file);
      if (!['http:', 'https:'].includes(url.protocol)) return document.createTextNode(file);
      const a = make('a', '', file);
      a.href = url.href;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      return a;
    } catch (_) {
      return document.createTextNode(file);
    }
  }

  function addDetails(body, results) {
    const sources = collectSources(results);
    if (sources.length) {
      const section = make('details', 'sources');
      section.append(make('summary', '', `资料来源 · ${sources.length}`));
      const list = make('ul', 'source-list');
      for (const source of sources) {
        const item = make('li');
        const main = make('div', 'source-title');
        main.append(sourceLink(source.source_file));
        const position = [source.section, source.page_or_slide, source.data_version].filter(value => value !== null && value !== undefined && value !== '').join(' · ');
        if (position) main.append(make('div', 'source-meta', position));
        item.append(main);
        list.append(item);
      }
      section.append(list);
      body.append(section);
    }

  }

  function renderAnswer(container, payload, error, scroll = true) {
    container.body.replaceChildren();
    const answer = error || payload.answer || '没有收到可显示的答案。';
    container.body.append(make('p', 'answer', answer));
    if (payload.status === 'partial') container.body.append(make('p', 'message-warning', '回答部分内容暂不可用，请结合资料来源阅读或稍后重试。'));
    if (payload.status === 'error' && !error) container.body.append(make('p', 'message-warning', '回答生成未完成，请稍后重试。'));
    if (!error) addDetails(container.body, payload.results);

    const actions = make('div', 'message-actions');
    const copy = make('button', '', '复制回答');
    copy.type = 'button';
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(answer);
        copy.textContent = '已复制';
      } catch (_) {
        copy.textContent = '复制失败';
      }
    });
    actions.append(copy);
    if (payload.request_id) actions.append(make('span', 'request-id', `请求 ID：${payload.request_id}`));
    container.body.append(actions);
    if (scroll) scrollToLatest();
  }

  function showChat() {
    backgroundDocument.hidden = true;
    conversation.hidden = false;
    composer.hidden = false;
    backgroundToggle.classList.remove('selected');
    backgroundToggle.removeAttribute('aria-current');
    document.querySelector('#mobile-background').removeAttribute('aria-current');
  }

  function showBackground() {
    backgroundDocument.hidden = false;
    conversation.hidden = true;
    composer.hidden = true;
    backgroundToggle.classList.add('selected');
    backgroundToggle.setAttribute('aria-current', 'page');
    document.querySelector('#mobile-background').setAttribute('aria-current', 'page');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function renderHistory() {
    historyList.replaceChildren();
    const items = historyStore.conversations(savedTurns);
    historyEmpty.hidden = items.length > 0;
    clearHistory.hidden = items.length === 0;
    for (const item of items) {
      const button = make('button', 'history-item');
      button.type = 'button';
      button.title = item.title;
      button.setAttribute('aria-label', `打开对话：${item.title}`);
      button.append(make('span', 'history-item-title', item.title), make('small', '', `${item.count} 轮问答`));
      if (item.threadId === threadId && backgroundDocument.hidden) button.classList.add('current');
      button.addEventListener('click', () => restoreConversation(item.threadId));
      historyList.append(button);
    }
  }

  function restoreConversation(id) {
    if (busy) return;
    const turns = savedTurns.filter(turn => turn.threadId === id);
    if (!turns.length) return;
    threadId = id;
    messages.replaceChildren();
    welcome.hidden = true;
    for (const turn of turns) {
      newMessage('user', '我的提问').body.append(make('div', '', turn.question));
      renderAnswer(newMessage('assistant', '知识助手'), turn.payload, undefined, false);
    }
    showChat();
    renderHistory();
    scrollToLatest();
  }

  async function sendQuestion(raw) {
    const question = raw.trim();
    if (busy || !question) return;
    busy = true;
    sendButton.disabled = true;
    welcome.hidden = true;
    newMessage('user', '我的提问').body.append(make('div', '', question));
    const answer = newMessage('assistant loading', '知识助手');
    answer.body.append(make('span', 'loading-dots', '正在检索资料并组织回答'));
    questionInput.value = '';
    questionInput.style.height = '';
    scrollToLatest();
    let needsAuth = false;

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (serviceKey) headers['X-API-Key'] = serviceKey;
      if (clientId) headers['X-Client-ID'] = clientId;
      const response = await fetch('/chat', {
        method: 'POST', headers,
        body: JSON.stringify({ question, thread_id: threadId }),
      });
      const payload = await response.json();
      answer.article.classList.remove('loading');
      if (!response.ok) {
        let message = payload.error?.message || `请求失败（HTTP ${response.status}）`;
        if (response.status === 401 || response.status === 403) {
          message = '服务要求访问密码，请填写管理员提供的网站密码后重发问题。';
          questionInput.value = question;
          needsAuth = true;
        }
        renderAnswer(answer, payload, message);
      } else {
        renderAnswer(answer, payload);
        savedTurns = historyStore.saveTurn(storage, savedTurns, {
          threadId, question, payload, createdAt: new Date().toISOString(),
        });
        renderHistory();
      }
    } catch (_) {
      answer.article.classList.remove('loading');
      renderAnswer(answer, {}, '无法连接本地服务，请确认服务仍在运行后重试。');
    } finally {
      busy = false;
      sendButton.disabled = false;
      if (needsAuth) settingsDialog.showModal();
      else questionInput.focus();
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    sendQuestion(questionInput.value);
  });
  questionInput.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  questionInput.addEventListener('input', () => {
    questionInput.style.height = 'auto';
    questionInput.style.height = `${Math.min(questionInput.scrollHeight, 180)}px`;
  });
  document.querySelectorAll('[data-question]').forEach(button => {
    button.addEventListener('click', () => sendQuestion(button.dataset.question));
  });
  function resetChat() {
    if (busy) return;
    threadId = crypto.randomUUID();
    messages.replaceChildren();
    welcome.hidden = false;
    questionInput.value = '';
    showChat();
    renderHistory();
    questionInput.focus();
  }
  document.querySelector('#new-chat').addEventListener('click', resetChat);
  document.querySelector('#mobile-new-chat').addEventListener('click', resetChat);
  backgroundToggle.addEventListener('click', showBackground);
  document.querySelector('#mobile-background').addEventListener('click', showBackground);
  document.querySelector('#back-to-chat').addEventListener('click', showChat);
  clearHistory.addEventListener('click', () => {
    savedTurns = historyStore.clear(storage);
    resetChat();
  });
  document.querySelector('#settings-form').addEventListener('submit', event => {
    if (event.submitter?.value !== 'save') return;
    clientId = document.querySelector('#client-id').value.trim();
    serviceKey = document.querySelector('#service-key').value;
  });
  if (savedTurns.length) restoreConversation(savedTurns[savedTurns.length - 1].threadId);
  else renderHistory();
})();
