(() => {
  'use strict';

  const form = document.querySelector('#chat-form');
  const questionInput = document.querySelector('#question');
  const sendButton = document.querySelector('#send');
  const messages = document.querySelector('#messages');
  const welcome = document.querySelector('#welcome');
  const suggestions = document.querySelector('#suggestions');
  const settingsDialog = document.querySelector('#settings-dialog');
  const modelDialog = document.querySelector('#model-dialog');
  const modelButton = document.querySelector('#model-settings-button');
  const mobileModelButton = document.querySelector('#mobile-model-settings');
  let modelSettingsToken = '';
  const backgroundToggle = document.querySelector('#background-toggle');
  const backgroundTimeline = document.querySelector('#background-timeline');
  const timelineSource = document.querySelector('.timeline-source');
  const backgroundDocument = document.querySelector('#background-document');
  const conversation = document.querySelector('#conversation');
  const composer = document.querySelector('#composer-wrap');
  const historyList = document.querySelector('#history-list');
  const historyPanel = document.querySelector('#history-panel');
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

  const exampleQuestions = [
    { category: '战略规划', label: '三个阶段分别要做什么？', question: '3820工程分为哪三个阶段？各阶段的主要目标是什么？' },
    { category: '战略规划', label: '为什么要制定二十年规划？', question: '福州为什么在1992年制定二十年经济社会发展战略设想？' },
    { category: '战略规划', label: '“3820”三个数字怎么理解？', question: '“3820”中的3年、8年、20年分别从哪一年算起？' },
    { category: '战略规划', label: '1995 年的主要目标是什么？', question: '3820工程第一阶段到1995年的主要目标和发展重点是什么？' },
    { category: '指标查询', label: '1995 年福州 GDP 是多少？', question: '指南记录的1995年福州地区生产总值是多少？请说明来源。' },
    { category: '指标查询', label: '1990—1995 年 GDP 增长多少？', question: '按指南中的1990年和1995年GDP，增长率是多少？请列出计算依据。' },
    { category: '指标查询', label: 'GDP 与 GNP 目标有什么区别？', question: '1995年GDP翻番推算目标与原件目标表中的GNP目标有什么区别？' },
    { category: '指标查询', label: '2010 年 GDP 的来源差异', question: '2010年福州GDP是多少？为什么不同资料中的数值不同？' },
    { category: '空间布局', label: '闽江口经济圈如何布局？', question: '原件怎样描述闽江口金三角经济圈的战略布局？' },
    { category: '空间布局', label: '投资示意图包含哪些区域？', question: '福州市闽江口金三角经济圈投资示意图中有哪些主要区域？' },
    { category: '空间布局', label: '开发区与老市区各起什么作用？', question: '3820工程的战略布局中，福州经济技术开发区和老市区分别承担什么作用？' },
    { category: '空间布局', label: '为什么强调沿江向海？', question: '3820工程为什么重视闽江口和海洋方向的发展？' },
    { category: '实施路径', label: '“海上福州”如何落地？', question: '“海上福州”与3820工程是什么关系？规划了哪些海洋发展方向？' },
    { category: '实施路径', label: '机场建设与战略有何关系？', question: '长乐国际机场建设如何服务于3820工程的对外开放目标？' },
    { category: '实施路径', label: '规划提出哪些基础设施重点？', question: '3820工程在机场、港口、公路等基础设施方面提出了哪些重点？' },
    { category: '实施路径', label: '如何推动产业与开放？', question: '3820工程如何通过开发区、招商和侨资推动产业发展？' },
    { category: '成效评估', label: '1995 年 GDP 目标达成率', question: '按指南的翻番演示算法，1995年福州GDP目标达成率是多少？' },
    { category: '成效评估', label: '2000 年目标能否判断达成？', question: '2000年定性目标是否达成？现有资料足以评估吗？' },
    { category: '成效评估', label: '2010 年 GDP 增长率能直接算吗？', question: '2010年GDP有不同版本时，能直接计算与1990年的增长率吗？' },
    { category: '成效评估', label: '目标表与完成值如何比较？', question: '评估3820工程目标时，为什么要区分当年目标表和后来的完成值？' },
    { category: '理论与方法', label: '调查研究为何重要？', question: '3820工程的编制过程怎样体现调查研究和群众参与？' },
    { category: '理论与方法', label: '怎样理解长期规划的方法？', question: '如何从分阶段目标和战略布局理解3820工程的长期规划方法？' },
    { category: '理论与方法', label: '马克思主义如何帮助理解规划？', question: '怎样用马克思主义的方法分析3820工程的调查研究和分阶段发展？' },
    { category: '理论与方法', label: '如何区分当年规划和后来理论？', question: '用习近平新时代中国特色社会主义思想理解3820工程时，怎样区分后来的分析视角与1992年规划原文？' },
  ];
  let previousQuestions = [];

  function renderSuggestions() {
    const categories = new Map();
    for (const example of exampleQuestions) {
      if (!categories.has(example.category)) categories.set(example.category, []);
      categories.get(example.category).push(example);
    }
    const names = [...categories.keys()];
    for (let index = names.length - 1; index > 0; index -= 1) {
      const randomIndex = Math.floor(Math.random() * (index + 1));
      [names[index], names[randomIndex]] = [names[randomIndex], names[index]];
    }
    const chosen = names.slice(0, 4).map(name => {
      const group = categories.get(name);
      return group[Math.floor(Math.random() * group.length)];
    });
    if (previousQuestions.length && chosen.every(example => previousQuestions.includes(example.question))) {
      chosen[0] = categories.get(chosen[0].category).find(example => !previousQuestions.includes(example.question)) || chosen[0];
    }
    previousQuestions = chosen.map(example => example.question);
    suggestions.replaceChildren();
    for (const example of chosen) {
      const button = make('button');
      button.type = 'button';
      button.dataset.question = example.question;
      const arrow = make('span', 'suggestion-arrow', '↗');
      arrow.setAttribute('aria-hidden', 'true');
      button.append(make('span', 'suggestion-category', example.category), make('span', '', example.label), arrow);
      button.addEventListener('click', () => sendQuestion(example.question));
      suggestions.append(button);
    }
  }

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
    document.body.dataset.view = 'chat';
    backgroundDocument.hidden = true;
    conversation.hidden = false;
    composer.hidden = false;
    backgroundTimeline.hidden = true;
    timelineSource.hidden = true;
    historyPanel.hidden = false;
    backgroundToggle.classList.remove('selected');
    backgroundToggle.removeAttribute('aria-current');
    document.querySelector('#mobile-background').removeAttribute('aria-current');
  }

  function showBackground() {
    document.body.dataset.view = 'background';
    backgroundDocument.hidden = false;
    conversation.hidden = true;
    composer.hidden = true;
    backgroundTimeline.hidden = false;
    timelineSource.hidden = false;
    historyPanel.hidden = true;
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
  function resetChat() {
    if (busy) return;
    threadId = crypto.randomUUID();
    messages.replaceChildren();
    welcome.hidden = false;
    questionInput.value = '';
    renderSuggestions();
    showChat();
    renderHistory();
    questionInput.focus();
  }
  document.querySelector('#new-chat').addEventListener('click', resetChat);
  document.querySelector('#mobile-new-chat').addEventListener('click', resetChat);
  backgroundToggle.addEventListener('click', showBackground);
  document.querySelector('#mobile-background').addEventListener('click', showBackground);
  document.querySelector('#back-to-chat').addEventListener('click', showChat);
  document.querySelector('#refresh-suggestions').addEventListener('click', renderSuggestions);
  clearHistory.addEventListener('click', () => {
    savedTurns = historyStore.clear(storage);
    resetChat();
  });
  document.querySelector('#settings-form').addEventListener('submit', event => {
    if (event.submitter?.value !== 'save') return;
    clientId = document.querySelector('#client-id').value.trim();
    serviceKey = document.querySelector('#service-key').value;
  });
  function showModelSettings() {
    if (!modelDialog.open) modelDialog.showModal();
  }
  modelButton.addEventListener('click', showModelSettings);
  mobileModelButton.addEventListener('click', showModelSettings);
  document.querySelector('#model-close').addEventListener('click', () => modelDialog.close());
  document.querySelector('#model-form').addEventListener('submit', async event => {
    event.preventDefault();
    const status = document.querySelector('#model-status');
    const save = document.querySelector('#model-save');
    save.disabled = true;
    status.textContent = '正在保存…';
    try {
      const response = await fetch('/desktop/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Desktop-Settings': modelSettingsToken },
        body: JSON.stringify({
          api_key: document.querySelector('#ark-key').value,
          llm_model: document.querySelector('#llm-model').value,
          embed_model: document.querySelector('#embed-model').value,
          base_url: document.querySelector('#ark-base-url').value,
        }),
      });
      if (!response.ok) throw new Error('保存失败，请检查密钥、模型 ID 和 API 地址。');
      document.querySelector('#ark-key').value = '';
      status.textContent = '配置已保存，可以开始提问。';
      setTimeout(() => modelDialog.close(), 900);
    } catch (error) {
      status.textContent = error.message || '无法保存配置。';
    } finally {
      save.disabled = false;
    }
  });
  fetch('/desktop/config', { cache: 'no-store' }).then(async response => {
    if (!response.ok) return;
    const config = await response.json();
    modelSettingsToken = config.token;
    modelButton.hidden = false;
    mobileModelButton.hidden = false;
    document.querySelector('#llm-model').value = config.llm_model || '';
    document.querySelector('#embed-model').value = config.embed_model || '';
    document.querySelector('#ark-base-url').value = config.base_url;
    document.querySelector('#model-data-note').textContent = `个人资料目录：${config.data_dir}`;
    if (!config.configured) showModelSettings();
  }).catch(() => {});
  renderSuggestions();
  showChat();
  renderHistory();
})();
