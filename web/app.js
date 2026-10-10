(() => {
  'use strict';

  const form = document.querySelector('#chat-form');
  const questionInput = document.querySelector('#question');
  const sendButton = document.querySelector('#send');
  const messages = document.querySelector('#messages');
  const welcome = document.querySelector('#welcome');
  const settingsDialog = document.querySelector('#settings-dialog');
  const backgroundToggle = document.querySelector('#background-toggle');
  const backgroundTimeline = document.querySelector('#background-timeline');
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
        item.append(main, make('span', `badge${source.verified ? '' : ' unverified'}`, source.verified ? '已核验' : '待独立核验'));
        list.append(item);
      }
      section.append(list);
      body.append(section);
    }

    const entries = Object.entries(results || {});
    if (entries.length) {
      const section = make('details', 'agents');
      section.append(make('summary', '', `分析过程 · ${entries.length}`));
      const list = make('ul', 'agent-list');
      const roles = { planning: '规划', indicator: '指标', spatial: '空间', evaluation: '评估', theory: '理论资料' };
      const states = { ok: '完成', insufficient_evidence: '依据不足', error: '执行异常' };
      for (const [name, result] of entries) {
        const item = make('li');
        const role = result.role || name.split('_')[0];
        item.append(make('span', '', role === 'theory' ? '理论参照' : `${roles[role] || role}智能体`), make('span', `badge${result.status === 'ok' ? '' : result.status === 'error' ? ' error' : ' partial'}`, states[result.status] || result.status));
        list.append(item);
      }
      section.append(list);
      body.append(section);
    }
  }

  function renderAnswer(container, payload, error) {
    container.body.replaceChildren();
    const answer = error || payload.answer || '没有收到可显示的答案。';
    container.body.append(make('p', 'answer', answer));
    if (payload.status === 'partial') container.body.append(make('p', 'message-warning', '部分智能体未完成，请结合下方执行状态和来源查看。'));
    if (payload.status === 'error' && !error) container.body.append(make('p', 'message-warning', '智能体执行未完成，请稍后重试。'));
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
    questionInput.focus();
  }
  document.querySelector('#new-chat').addEventListener('click', resetChat);
  document.querySelector('#mobile-new-chat').addEventListener('click', resetChat);
  backgroundToggle.addEventListener('click', () => {
    const expanded = backgroundToggle.getAttribute('aria-expanded') === 'true';
    backgroundToggle.setAttribute('aria-expanded', String(!expanded));
    backgroundTimeline.hidden = expanded;
  });
  document.querySelector('#mobile-background').addEventListener('click', () => {
    document.body.classList.toggle('timeline-open');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  document.querySelector('#settings-form').addEventListener('submit', event => {
    if (event.submitter?.value !== 'save') return;
    clientId = document.querySelector('#client-id').value.trim();
    serviceKey = document.querySelector('#service-key').value;
  });
})();
