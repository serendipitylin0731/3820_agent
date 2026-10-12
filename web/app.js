(() => {
  'use strict';

  function createThreadId(cryptoSource = globalThis.crypto) {
    if (typeof cryptoSource?.randomUUID === 'function') return cryptoSource.randomUUID();
    const bytes = new Uint8Array(16);
    if (typeof cryptoSource?.getRandomValues === 'function') cryptoSource.getRandomValues(bytes);
    else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { createThreadId };
  if (typeof document === 'undefined') return;

  const form = document.querySelector('#chat-form');
  const questionInput = document.querySelector('#question');
  const sendButton = document.querySelector('#send');
  const messages = document.querySelector('#messages');
  const welcome = document.querySelector('#welcome');
  const suggestions = document.querySelector('#suggestions');
  const settingsDialog = document.querySelector('#settings-dialog');
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
  const libraryView = document.querySelector('#library-view');
  const libraryToggle = document.querySelector('#library-toggle');
  const libraryResults = document.querySelector('#library-results');
  const libraryStatus = document.querySelector('#library-status');
  const libraryReader = document.querySelector('#library-reader');
  const readerContent = document.querySelector('#library-reader-content');
  const readerPages = document.querySelector('#reader-pages');
  const readerPageSelect = document.querySelector('#reader-page-select');
  const searchHistoryStore = window.LibrarySearchHistory;
  let previewBlobUrl = null;
  let storage;
  try { storage = window.localStorage; } catch (_) { storage = null; }
  let savedTurns = historyStore.load(storage);
  let savedSearches = searchHistoryStore.load(storage);
  let activeReaderItem = null;
  let lastLibraryScroll = 0;
  let threadId = createThreadId();
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

  function modelNotice(payload) {
    return payload.notice || payload.results?.model?.data?.source_note || '';
  }

  function renderAnswer(container, payload, error, scroll = true) {
    container.body.replaceChildren();
    const answer = error || payload.answer || '没有收到可显示的答案。';
    container.body.append(make('p', 'answer', answer));
    if (payload.status === 'partial') container.body.append(make('p', 'message-warning', '回答部分内容暂不可用，请结合资料来源阅读或稍后重试。'));
    if (payload.status === 'error' && !error) container.body.append(make('p', 'message-warning', '回答生成未完成，请稍后重试。'));
    if (!error) addDetails(container.body, payload.results);
    const notice = !error && modelNotice(payload);
    if (notice) container.body.append(make('p', 'answer-note', notice));

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
    libraryView.hidden = true;
    libraryReader.hidden = true;
    libraryToggle.classList.remove('active');
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
    libraryView.hidden = true;
    libraryReader.hidden = true;
    libraryToggle.classList.remove('active');
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

  function showLibrary(preserveScroll = false) {
    document.body.dataset.view = 'library';
    libraryView.hidden = false;
    libraryReader.hidden = true;
    conversation.hidden = true;
    composer.hidden = true;
    backgroundDocument.hidden = true;
    backgroundTimeline.hidden = true;
    timelineSource.hidden = true;
    historyPanel.hidden = true;
    backgroundToggle.classList.remove('selected');
    backgroundToggle.removeAttribute('aria-current');
    document.querySelector('#mobile-background').removeAttribute('aria-current');
    libraryToggle.classList.add('active');
    if (!preserveScroll) {
      window.scrollTo({ top: 0, behavior: 'auto' });
      document.querySelector('#library-query').focus();
    }
  }

  function libraryHeaders() {
    const headers = {};
    if (serviceKey) headers['X-API-Key'] = serviceKey;
    if (clientId) headers['X-Client-ID'] = clientId;
    return headers;
  }

  async function checkedFetch(url) {
    const response = await fetch(url, { headers: libraryHeaders() });
    if (response.status === 401 || response.status === 403) settingsDialog.showModal();
    if (!response.ok) throw new Error(`请求失败（HTTP ${response.status}）`);
    return response;
  }

  function clearPreview() {
    if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    previewBlobUrl = null;
    readerContent.replaceChildren();
  }

  function showReader(item) {
    if (libraryReader.hidden) lastLibraryScroll = window.scrollY;
    activeReaderItem = item;
    document.body.dataset.view = 'library-reader';
    libraryView.hidden = true;
    libraryReader.hidden = false;
    document.querySelector('#library-reader-title').textContent = item.title;
    document.querySelector('#reader-collection').textContent = item.collection || '文献资料';
    document.querySelector('#reader-location').textContent = item.page_count
      ? `原件共 ${item.page_count} 页${item.indexed_page_count < item.page_count ? ` · 阅读稿含 ${item.indexed_page_count} 页文字` : ''}` : '';
    document.querySelector('#reader-download').textContent = item.format === 'md' ? '下载 Word' : '下载文件';
    document.querySelector('#reader-pdf').hidden = !item.pdf_id;
    document.querySelector('#reader-match').textContent = item.match_page ? `已定位至关键词所在第 ${item.match_page} 页` : '';
    window.scrollTo(0, 0);
  }

  function closeReader() {
    clearPreview();
    activeReaderItem = null;
    showLibrary(true);
    requestAnimationFrame(() => window.scrollTo(0, lastLibraryScroll));
  }

  function renderSearchHistory() {
    const panel = document.querySelector('#library-search-history');
    const list = document.querySelector('#library-history-list');
    panel.hidden = savedSearches.length === 0;
    list.replaceChildren();
    for (const term of savedSearches) {
      const button = make('button', '', term);
      button.type = 'button';
      button.addEventListener('click', () => {
        document.querySelector('#library-query').value = term;
        searchLibrary(term);
      });
      list.append(button);
    }
  }

  function renderMarkdown(content, item) {
    const output = make('div', 'library-markdown');
    let code = false;
    const highlights = item.highlight_terms || [];
    function appendHighlighted(element, value) {
      if (!highlights.length) { element.append(document.createTextNode(value)); return; }
      const pattern = new RegExp(highlights.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .sort((a, b) => b.length - a.length).join('|'), 'gi');
      let start = 0;
      for (const match of value.matchAll(pattern)) {
        if (match.index > start) element.append(document.createTextNode(value.slice(start, match.index)));
        element.append(make('mark', '', match[0]));
        start = match.index + match[0].length;
      }
      if (start < value.length) element.append(document.createTextNode(value.slice(start)));
    }
    function appendInline(element, value) {
      const pattern = /(!?\[[^\]]+\]\(https?:\/\/[^)]+\)|\*\*[^*]+\*\*|__[^_]+__|`[^`]+`)/g;
      let start = 0;
      for (const match of value.matchAll(pattern)) {
        if (match.index > start) appendHighlighted(element, value.slice(start, match.index));
        const token = match[0];
        const link = token.match(/^(!?)\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
        if (link) {
          const node = make(link[1] ? 'img' : 'a');
          if (link[1]) { node.src = link[3]; node.alt = link[2]; node.loading = 'lazy'; }
          else { node.href = link[3]; node.target = '_blank'; node.rel = 'noopener noreferrer'; appendHighlighted(node, link[2]); }
          element.append(node);
        } else {
          const node = make(token.startsWith('`') ? 'code' : 'strong');
          appendHighlighted(node, token.startsWith('`') ? token.slice(1, -1) : token.slice(2, -2));
          element.append(node);
        }
        start = match.index + token.length;
      }
      if (start < value.length) appendHighlighted(element, value.slice(start));
    }
    let firstMark = null;
    for (const line of content.split(/\r?\n/)) {
      if (line.trim().startsWith('```') || line.trim().startsWith('~~~')) {
        code = !code;
        continue;
      }
      if (!line.trim()) continue;
      let element;
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      const page = line.match(/^## 第\s*(\d+)\s*页/);
      if (line.trim() === '---') element = make('hr');
      else if (code) { element = make('pre'); appendHighlighted(element, line); }
      else if (heading) { element = make(`h${Math.min(heading[1].length, 4)}`); appendInline(element, heading[2]); }
      else if (/^\s*>\s?/.test(line)) { element = make('blockquote'); appendInline(element, line.replace(/^\s*>\s?/, '')); }
      else if (/^\s*[-*+]\s+/.test(line)) { element = make('p', 'library-list'); appendInline(element, `• ${line.replace(/^\s*[-*+]\s+/, '')}`); }
      else { element = make('p'); appendInline(element, line); }
      if (page) element.id = `reader-page-${page[1]}`;
      output.append(element);
      if (!firstMark) firstMark = element.querySelector('mark');
    }
    output.dataset.hasMatch = firstMark ? 'true' : 'false';
    return output;
  }

  function jumpToPage(page) {
    const element = document.querySelector(`#reader-page-${page}`);
    if (element) element.scrollIntoView({ block: 'start', behavior: 'auto' });
  }

  async function previewDocument(item) {
    clearPreview();
    showReader(item);
    readerContent.append(make('p', 'library-status', '正在加载预览…'));
    readerPages.hidden = true;
    try {
      const response = await checkedFetch(`/library/${encodeURIComponent(item.id)}/preview`);
      readerContent.replaceChildren();
      if (['md', 'txt', 'docx'].includes(item.format)) {
        const payload = await response.json();
        const pages = payload.pages || [];
        readerPageSelect.replaceChildren();
        readerPages.hidden = pages.length === 0;
        for (const page of pages) {
          const option = make('option', '', `第 ${page} 页`);
          option.value = String(page);
          readerPageSelect.append(option);
        }
        if (item.source_url) {
          const source = make('a', 'reader-source', '查看文献原文 ↗');
          source.href = item.source_url;
          source.target = '_blank';
          source.rel = 'noopener noreferrer';
          readerContent.append(source);
        }
        readerContent.append(renderMarkdown(payload.content, item));
        requestAnimationFrame(() => {
          if (item.match_page) { readerPageSelect.value = String(item.match_page); jumpToPage(item.match_page); }
          else readerContent.querySelector('mark')?.scrollIntoView({ block: 'center', behavior: 'auto' });
        });
      } else {
        previewBlobUrl = URL.createObjectURL(await response.blob());
        const element = item.format === 'pdf' ? make('iframe', 'library-frame')
          : item.format === 'mp4' ? make('video', 'library-video') : make('img', 'library-image');
        element.src = previewBlobUrl + (item.format === 'pdf' && item.match_page ? `#page=${item.match_page}` : '');
        if (item.format === 'mp4') element.controls = true;
        element.title = item.title;
        readerContent.append(element);
      }
    } catch (error) {
      readerContent.replaceChildren(make('p', 'library-status', error.message));
    }
  }

  async function downloadDocument(item) {
    try {
      const response = await checkedFetch(`/library/${encodeURIComponent(item.id)}/download`);
      const blobUrl = URL.createObjectURL(await response.blob());
      const link = make('a');
      link.href = blobUrl;
      const filename = item.format === 'md' ? `${item.title}.docx` : `${item.title}.${item.format}`;
      link.download = filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch (error) {
      if (libraryReader.hidden) libraryStatus.textContent = error.message;
      else readerContent.prepend(make('p', 'library-status', error.message));
    }
  }

  async function searchLibrary(query) {
    clearPreview();
    libraryResults.replaceChildren();
    libraryStatus.textContent = '正在检索资料…';
    try {
      const response = await checkedFetch(`/library/search?q=${encodeURIComponent(query)}`);
      const payload = await response.json();
      savedSearches = searchHistoryStore.save(storage, savedSearches, query);
      renderSearchHistory();
      libraryStatus.textContent = payload.results.length ? `找到 ${payload.results.length} 条匹配资料` : '没有找到匹配的资料，请更换关键词。';
      for (const item of payload.results) {
        const card = make('article', 'library-card');
        const label = { documents: '文字文档', papers: '本地论文', literature: '文献', pdf: 'PDF', media: '图片与视频' }[item.category];
        card.append(make('span', 'library-type', label || item.format), make('h2', '', item.title));
        if (item.collection) card.append(make('small', 'library-collection', item.collection));
        if (item.match_page) card.append(make('small', 'library-match-page', `匹配于第 ${item.match_page} 页`));
        if (item.snippet) card.append(make('p', '', item.snippet));
        const actions = make('div', 'library-card-actions');
        const preview = make('button', '', '预览');
        preview.type = 'button';
        preview.addEventListener('click', () => previewDocument(item));
        const download = make('button', '', item.format === 'md' ? '下载 Word' : '下载');
        download.type = 'button';
        download.addEventListener('click', () => downloadDocument(item));
        actions.append(preview, download);
        card.append(actions);
        libraryResults.append(card);
      }
    } catch (error) {
      libraryStatus.textContent = error.message;
    }
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
        payload.notice = modelNotice(payload);
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
    threadId = createThreadId();
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
  libraryToggle.addEventListener('click', () => showLibrary());
  document.querySelector('#mobile-library').addEventListener('click', () => showLibrary());
  document.querySelector('#library-search-form').addEventListener('submit', event => {
    event.preventDefault();
    searchLibrary(document.querySelector('#library-query').value.trim());
  });
  document.querySelector('#reader-back').addEventListener('click', closeReader);
  readerPageSelect.addEventListener('change', () => jumpToPage(readerPageSelect.value));
  document.querySelector('#reader-download').addEventListener('click', () => {
    if (activeReaderItem) downloadDocument(activeReaderItem);
  });
  document.querySelector('#reader-pdf').addEventListener('click', () => {
    if (activeReaderItem?.pdf_id) previewDocument({ ...activeReaderItem, id: activeReaderItem.pdf_id,
      format: 'pdf', pdf_id: null, category: 'pdf' });
  });
  document.querySelector('#clear-library-history').addEventListener('click', () => {
    savedSearches = searchHistoryStore.clear(storage);
    renderSearchHistory();
  });
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
  renderSuggestions();
  renderSearchHistory();
  showChat();
  renderHistory();
})();
