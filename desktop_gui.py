"""Native Tk desktop interface. It calls the agent graph directly without HTTP or WebView."""

import logging
import queue
import random
import re
import shutil
import threading
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import Settings
from desktop_history import conversations, load_history, save_history
from desktop_runtime import apply_model_config, read_model_config, write_model_config


INK = '#18342c'
MUTED = '#62746b'
PAPER = '#f8faf6'
SIDEBAR = '#18342c'
GREEN = '#276349'
SOFT = '#eaf2e9'
LINE = '#dce6db'

EXAMPLES = [
    ('战略规划', '“3820”三个数字怎么理解？'),
    ('战略规划', '福州为什么在1992年制定二十年发展战略？'),
    ('战略规划', '3820工程分为哪三个阶段？各阶段的目标是什么？'),
    ('战略规划', '3820工程是怎样通过调查研究形成的？'),
    ('指标查询', '1995年福州地区生产总值是多少？'),
    ('指标查询', '2010年福州GDP的不同版本如何理解？'),
    ('指标查询', '1995年GDP目标和GNP目标有什么区别？'),
    ('指标查询', '1990年到1995年福州GDP增长率是多少？'),
    ('空间布局', '闽江口金三角经济圈如何布局？'),
    ('空间布局', '福州经济技术开发区和老市区分别承担什么作用？'),
    ('空间布局', '为什么强调沿江向海？'),
    ('实施路径', '长乐国际机场建设如何服务于3820工程的对外开放目标？'),
    ('实施路径', '“海上福州”与3820工程是什么关系？'),
    ('实施路径', '3820工程如何推动产业与开放？'),
    ('成效评估', '2000年定性目标是否有足够资料判断达成？'),
    ('成效评估', '评估3820工程目标时为什么要区分目标表与完成值？'),
    ('理论与方法', '怎样用马克思主义的方法分析3820工程的调查研究？'),
    ('理论与方法', '怎样区分1992年规划原文和后来的理论视角？'),
]


def collect_sources(result):
    seen = set()
    sources = []
    candidates = list(result.get('kb_sources', []))
    for item in result.get('results', {}).values():
        if isinstance(item, dict):
            candidates.extend(item.get('sources') or [])
    for source in candidates:
        if not isinstance(source, dict):
            continue
        marker = (str(source.get('source_file', '')), str(source.get('section', '')),
                  str(source.get('page_or_slide', '')))
        if marker[0] and marker not in seen:
            seen.add(marker)
            sources.append({key: source.get(key) for key in
                            ('source_file', 'section', 'page_or_slide', 'data_version')})
    return sources[:60]


class AutoHeightText(tk.Text):
    """Show the complete answer; the surrounding conversation canvas scrolls."""

    def __init__(self, master, **kwargs):
        super().__init__(master, height=2, **kwargs)
        self._fit_pending = False
        self.bind('<Configure>', self._schedule_fit, add='+')

    def _schedule_fit(self, _event=None):
        if not self._fit_pending:
            self._fit_pending = True
            self.after_idle(self._fit)

    def _fit(self):
        self._fit_pending = False
        if not self.winfo_exists() or self.winfo_width() <= 1:
            return
        result = self.count('1.0', 'end', 'update', 'displaylines')
        lines = result[0] if isinstance(result, tuple) else result
        needed = max(2, int(lines or 1) + 1)
        if int(self.cget('height')) != needed:
            self.configure(height=needed)


def _readonly_text(parent, content, *, bg, fg=INK, font_size=11, padx=12, pady=10):
    widget = AutoHeightText(parent, wrap='word', bg=bg, fg=fg,
                            relief='flat', borderwidth=0, padx=padx, pady=pady,
                            font=('Microsoft YaHei UI', font_size), cursor='arrow')
    widget.insert('1.0', content)
    widget.configure(state='disabled')
    widget._schedule_fit()
    return widget


class QuestionInput(tk.Text):
    def __init__(self, master, send, **kwargs):
        super().__init__(master, **kwargs)
        self._send = send

    def _on_return(self, event):
        if event.state & 0x1:  # Shift + Enter inserts a new line.
            return None
        self._send()
        return 'break'


class DesktopApp:
    def __init__(self, root: tk.Tk, home: Path):
        self.root = root
        self.home = home
        self.turns = load_history(home)
        self.thread_id = str(uuid.uuid4())
        self.busy = False
        self.pending = queue.Queue()
        self._build()
        self._show_welcome()
        self._render_history()
        self.show_chat()
        self.root.after(250, self._first_run_settings)
        self.root.after(100, self._poll)

    def _build(self):
        self.root.title('3820 · 战略知识助手')
        scale = getattr(self.root, 'ui_scale', 1.0)
        width = min(round(1160 * scale), max(760, self.root.winfo_screenwidth() - 80))
        height = min(round(780 * scale), max(540, self.root.winfo_screenheight() - 80))
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(min(round(850 * scale), width), min(round(600 * scale), height))
        self.root.configure(bg=PAPER)
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('History.TScrollbar', background=SIDEBAR)

        shell = tk.Frame(self.root, bg=PAPER)
        shell.pack(fill='both', expand=True)
        self.sidebar = tk.Frame(shell, bg=SIDEBAR, width=round(270 * scale))
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        self.main = tk.Frame(shell, bg=PAPER)
        self.main.pack(side='left', fill='both', expand=True)

        brand = tk.Frame(self.sidebar, bg=SIDEBAR)
        brand.pack(fill='x', padx=21, pady=(27, 30))
        logo = tk.Canvas(brand, width=48, height=48, bg=SIDEBAR, highlightthickness=0)
        logo.pack(side='left', padx=(0, 12))
        logo.create_rectangle(3, 3, 45, 45, outline='#91ad9b', width=1)
        logo.create_line(10, 35, 20, 27, 29, 31, 39, 14,
                         fill='#a9d4ad', width=3, smooth=False)
        for x, y in ((10, 35), (20, 27), (39, 14)):
            logo.create_oval(x-3, y-3, x+3, y+3, fill='#d8a366', outline='')
        tk.Label(brand, text='3820 · 战略知识助手', bg=SIDEBAR, fg='#f0f6ed',
                 font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w', pady=(4, 2))
        tk.Label(brand, text='福州发展战略知识平台', bg=SIDEBAR, fg='#a9c1ac',
                 font=('Microsoft YaHei UI', 9)).pack(anchor='w')

        self._side_button('✦  新建对话', self.new_chat).pack(fill='x', padx=20, pady=(0, 8))
        self.background_button = tk.Frame(self.sidebar, bg='#284b3b',
                                          highlightbackground='#527463',
                                          highlightthickness=1, takefocus=1, cursor='hand2')
        self.background_button.pack(fill='x', padx=20, pady=(0, 17))
        self.background_label = tk.Label(self.background_button, text='3820 背景',
                                         bg='#284b3b', fg='#f0f6ed',
                                         font=('Microsoft YaHei UI', 10, 'bold'), cursor='hand2')
        self.background_label.pack(side='left', padx=12, pady=10)
        self.background_arrow = tk.Label(self.background_button, text='↗',
                                         bg='#284b3b', fg='#afd1b4',
                                         font=('Microsoft YaHei UI', 12), cursor='hand2')
        self.background_arrow.pack(side='right', padx=12)
        for widget in (self.background_button, self.background_label, self.background_arrow):
            widget.bind('<Button-1>', lambda _event: self.show_document())
        self.background_button.bind('<Return>', lambda _event: self.show_document())
        self.background_button.bind('<space>', lambda _event: self.show_document())
        self.sidebar_body = tk.Frame(self.sidebar, bg=SIDEBAR)
        self.sidebar_body.pack(fill='both', expand=True)
        self.timeline_panel = tk.Frame(self.sidebar_body, bg=SIDEBAR)
        tk.Label(self.timeline_panel, text='发展时间线', bg=SIDEBAR, fg='#9db5a4',
                 font=('Microsoft YaHei UI', 9, 'bold')).pack(anchor='w', padx=26, pady=(0, 15))
        timeline_scroll = tk.Frame(self.timeline_panel, bg=SIDEBAR)
        timeline_scroll.pack(fill='both', expand=True)
        self.timeline_canvas = tk.Canvas(timeline_scroll, bg=SIDEBAR, highlightthickness=0,
                                         borderwidth=0)
        timeline_bar = ttk.Scrollbar(timeline_scroll, orient='vertical',
                                     command=self.timeline_canvas.yview)
        self.timeline_canvas.configure(yscrollcommand=timeline_bar.set)
        self.timeline_canvas.pack(side='left', fill='both', expand=True)
        timeline_bar.pack(side='right', fill='y')
        timeline_content = tk.Frame(self.timeline_canvas, bg=SIDEBAR)
        timeline_window = self.timeline_canvas.create_window((0, 0), window=timeline_content,
                                                              anchor='nw')
        self.timeline_canvas.bind('<Configure>',
                                  lambda event: self.timeline_canvas.itemconfigure(timeline_window, width=event.width))
        timeline_content.bind('<Configure>',
                              lambda _event: self.timeline_canvas.configure(scrollregion=self.timeline_canvas.bbox('all')))
        self.timeline_canvas.bind('<MouseWheel>', self._scroll_timeline)
        self.timeline_canvas.bind('<Button-4>', self._scroll_timeline)
        self.timeline_canvas.bind('<Button-5>', self._scroll_timeline)
        timeline = [
            ('1990', '规划基期', '以这一年的主要指标作为三年目标的比较起点。'),
            ('1992', '战略形成', '广泛调研、论证后，二十年战略设想于 11 月审议通过。'),
            ('1995', '三年 · 起步', '推动主要指标在 1990 年基础上再翻一番。'),
            ('2000', '八年 · 追赶', '力争城乡主要人均指标达到国内先进城市水平。'),
            ('2010', '二十年 · 远景', '力争达到或接近亚洲中等发达国家或地区的平均水平。'),
        ]
        for index, (year, title, detail) in enumerate(timeline):
            row = tk.Frame(timeline_content, bg=SIDEBAR)
            row.pack(fill='x', padx=(27, 17))
            rail = tk.Canvas(row, width=21, height=1, bg=SIDEBAR, highlightthickness=0)
            rail.pack(side='left', fill='y', padx=(0, 10))
            def draw_rail(event, canvas=rail, last=index == len(timeline) - 1):
                canvas.delete('all')
                if not last:
                    canvas.create_line(10, 0, 10, event.height, fill='#547360', width=1)
                canvas.create_oval(6, 5, 14, 13, fill='#dbab72', outline='#254c3d', width=2)
            rail.bind('<Configure>', draw_rail)
            content = tk.Frame(row, bg=SIDEBAR)
            content.pack(side='left', fill='x', expand=True, pady=(0, 14))
            tk.Label(content, text=year, bg=SIDEBAR, fg='#e8b777', anchor='w',
                     font=('Georgia', 13, 'bold')).pack(anchor='w', pady=(0, 2))
            tk.Label(content, text=title, bg=SIDEBAR, fg='#f0f4e9', anchor='w',
                     font=('Microsoft YaHei UI', 9, 'bold')).pack(anchor='w')
            tk.Label(content, text=detail, bg=SIDEBAR, fg='#b0c5b5', anchor='w',
                     justify='left', wraplength=round(175 * scale),
                     font=('Microsoft YaHei UI', 8)).pack(anchor='w', pady=(3, 0))
            for widget in (row, rail, content, *content.winfo_children()):
                widget.bind('<MouseWheel>', self._scroll_timeline)
                widget.bind('<Button-4>', self._scroll_timeline)
                widget.bind('<Button-5>', self._scroll_timeline)
        tk.Button(timeline_content, text='查看福州市发改委资料 ↗',
                  command=lambda: webbrowser.open('https://fgw.fuzhou.gov.cn/fgwzwgk/fzgggz/jjyx/202403/t20240328_4799823.htm'),
                  bg=SIDEBAR, fg='#b9d0bc', activebackground=SIDEBAR,
                  activeforeground='white', relief='flat', bd=0, cursor='hand2',
                  font=('Microsoft YaHei UI', 8, 'underline')).pack(anchor='w', padx=34, pady=(1, 8))

        self.history_panel = tk.Frame(self.sidebar_body, bg=SIDEBAR)
        tk.Frame(self.history_panel, height=1, bg='#466253').pack(fill='x', padx=20, pady=(0, 15))
        header = tk.Frame(self.history_panel, bg=SIDEBAR)
        header.pack(fill='x', padx=24)
        tk.Label(header, text='历史对话', bg=SIDEBAR, fg='#bcd0bd',
                 font=('Microsoft YaHei UI', 9, 'bold')).pack(side='left')
        self.clear_button = tk.Button(header, text='清空', command=self.clear_history, bg=SIDEBAR,
                                      fg='#bcd0bd', activebackground=SIDEBAR, activeforeground='white',
                                      relief='flat', bd=0, cursor='hand2', font=('Microsoft YaHei UI', 8))
        history_frame = tk.Frame(self.history_panel, bg=SIDEBAR)
        history_frame.pack(fill='both', expand=True, padx=19, pady=(8, 5))
        self.history_canvas = tk.Canvas(history_frame, bg=SIDEBAR, highlightthickness=0,
                                        borderwidth=0)
        history_scroll = ttk.Scrollbar(history_frame, orient='vertical',
                                       command=self.history_canvas.yview)
        self.history_canvas.configure(yscrollcommand=history_scroll.set)
        self.history_canvas.pack(side='left', fill='both', expand=True)
        history_scroll.pack(side='right', fill='y')
        self.history_items = tk.Frame(self.history_canvas, bg=SIDEBAR)
        history_window = self.history_canvas.create_window((0, 0), window=self.history_items,
                                                            anchor='nw')
        self.history_canvas.bind('<Configure>',
                                 lambda event: self.history_canvas.itemconfigure(history_window, width=event.width))
        self.history_items.bind('<Configure>',
                                lambda _event: self.history_canvas.configure(scrollregion=self.history_canvas.bbox('all')))
        self.history_canvas.bind('<MouseWheel>', self._scroll_history)
        self.history_canvas.bind('<Button-4>', self._scroll_history)
        self.history_canvas.bind('<Button-5>', self._scroll_history)
        tk.Label(self.history_panel, text='本机最多保存 30 轮问答', bg=SIDEBAR, fg='#92aa99',
                 font=('Microsoft YaHei UI', 8)).pack(anchor='w', padx=25, pady=(2, 8))
        self._side_button('⚙  豆包 API 设置', self.show_settings).pack(fill='x', padx=20, pady=(0, 7))
        self._side_button('＋  导入资料', self.import_files).pack(fill='x', padx=20, pady=(0, 17))

        topbar = tk.Frame(self.main, bg=PAPER, height=round(68 * scale))
        topbar.pack(fill='x')
        topbar.pack_propagate(False)
        tk.Label(topbar, text='3820  /  知识工作台', bg=PAPER, fg='#567863',
                 font=('Microsoft YaHei UI', 10, 'bold')).pack(side='left', padx=32)
        tk.Label(topbar, text='本地应用', bg=PAPER, fg='#6f8576',
                 font=('Microsoft YaHei UI', 9)).pack(side='right', padx=30)
        tk.Frame(self.main, height=1, bg=LINE).pack(fill='x')
        self.page_host = tk.Frame(self.main, bg=PAPER)
        self.page_host.pack(fill='both', expand=True)

        self.chat_page = tk.Frame(self.page_host, bg=PAPER)
        self.chat_page.pack(fill='both', expand=True)
        chat_canvas_wrap = tk.Frame(self.chat_page, bg=PAPER)
        chat_canvas_wrap.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(chat_canvas_wrap, bg=PAPER, highlightthickness=0)
        scroll = ttk.Scrollbar(chat_canvas_wrap, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.messages = tk.Frame(self.canvas, bg=PAPER)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.messages, anchor='nw')
        self.messages.bind('<Configure>', lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        self.canvas.bind('<MouseWheel>', self._scroll_messages)
        self.canvas.bind('<Button-4>', self._scroll_messages)
        self.canvas.bind('<Button-5>', self._scroll_messages)

        composer = tk.Frame(self.chat_page, bg='white', highlightbackground=LINE, highlightthickness=1)
        composer.pack(fill='x', padx=38, pady=(8, 20))
        self.input = QuestionInput(composer, self.send_question, height=3, wrap='word',
                                   font=('Microsoft YaHei UI', 11), fg=INK, bg='white',
                                   relief='flat', bd=0, padx=13, pady=11)
        self.input.pack(fill='x')
        self.input.bind('<Return>', self.input._on_return)
        composer_bottom = tk.Frame(composer, bg='white')
        composer_bottom.pack(fill='x', padx=12, pady=(0, 10))
        tk.Label(composer_bottom, text='Enter 发送 · Shift + Enter 换行', bg='white', fg='#91a396',
                 font=('Microsoft YaHei UI', 8)).pack(side='left')
        self.send_button = tk.Button(composer_bottom, text='发送  ↗', command=self.send_question,
                                     bg=GREEN, fg='white', activebackground='#174e36',
                                     activeforeground='white', relief='flat', bd=0,
                                     cursor='hand2', font=('Microsoft YaHei UI', 10, 'bold'),
                                     padx=18, pady=7)
        self.send_button.pack(side='right')

        self.doc_page = tk.Frame(self.page_host, bg=PAPER)
        doc_top = tk.Frame(self.doc_page, bg=PAPER)
        doc_top.pack(fill='x', padx=35, pady=(24, 14))
        tk.Label(doc_top, text='“3820”战略工程 · 背景导读', bg=PAPER, fg=INK,
                 font=('Microsoft YaHei UI', 18, 'bold')).pack(side='left')
        tk.Button(doc_top, text='返回问答  ↗', command=self.show_chat, bg=GREEN,
                  fg='white', relief='flat', bd=0, padx=14, pady=7,
                  cursor='hand2').pack(side='right')
        self.doc_text = tk.Text(self.doc_page, wrap='word', bg='white', fg=INK,
                                font=('Microsoft YaHei UI', 11), spacing3=8,
                                padx=28, pady=22, relief='flat', bd=0)
        self.doc_text.pack(fill='both', expand=True, padx=35, pady=(0, 24))
        self._load_document()

    def _side_button(self, text, command):
        return tk.Button(self.sidebar, text=text, command=command, anchor='w',
                         bg='#294b3b', fg='#f0f6ed', activebackground='#37664e',
                         activeforeground='white', relief='flat', bd=0,
                         font=('Microsoft YaHei UI', 10), padx=13, pady=10, cursor='hand2')

    def _scroll_messages(self, event):
        if getattr(event, 'num', None) == 4:
            amount = -3
        elif getattr(event, 'num', None) == 5:
            amount = 3
        else:
            delta = getattr(event, 'delta', 0)
            amount = (-1 if delta > 0 else 1) * max(1, abs(delta) // 120)
        self.canvas.yview_scroll(amount, 'units')
        return 'break'

    def _scroll_history(self, event):
        if getattr(event, 'num', None) == 4:
            amount = -3
        elif getattr(event, 'num', None) == 5:
            amount = 3
        else:
            delta = getattr(event, 'delta', 0)
            amount = (-1 if delta > 0 else 1) * max(1, abs(delta) // 120)
        self.history_canvas.yview_scroll(amount, 'units')
        return 'break'

    def _scroll_timeline(self, event):
        if getattr(event, 'num', None) == 4:
            amount = -3
        elif getattr(event, 'num', None) == 5:
            amount = 3
        else:
            delta = getattr(event, 'delta', 0)
            amount = (-1 if delta > 0 else 1) * max(1, abs(delta) // 120)
        self.timeline_canvas.yview_scroll(amount, 'units')
        return 'break'

    def _paint_background_button(self, selected):
        color = '#37664e' if selected else '#284b3b'
        for widget in (self.background_button, self.background_label, self.background_arrow):
            widget.configure(bg=color)

    def _show_welcome(self):
        self.welcome = tk.Frame(self.messages, bg=PAPER)
        self.welcome.pack(fill='x', padx=45, pady=(50, 26))
        tk.Label(self.welcome, text='福州 · 1992—2010', bg=PAPER, fg='#67866b',
                 font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w', pady=(0, 12))
        tk.Label(self.welcome, text='从资料出发，读懂“3820”。', bg=PAPER, fg=INK,
                 font=('Microsoft YaHei UI', 24, 'bold')).pack(anchor='w')
        tk.Label(self.welcome, text='围绕战略规划、经济指标、空间布局与实施成效提问。\n回答会附上可追溯的资料来源。',
                 bg=PAPER, fg=MUTED, justify='left', font=('Microsoft YaHei UI', 10)).pack(anchor='w', pady=(13, 28))
        suggestions = tk.Frame(self.welcome, bg=PAPER)
        suggestions.pack(fill='x')
        tk.Label(suggestions, text='试试这样提问', bg=PAPER, fg='#67816f',
                 font=('Microsoft YaHei UI', 9, 'bold')).pack(side='left')
        tk.Button(suggestions, text='换一批 ↻', command=self._render_suggestions,
                  bg=PAPER, fg=GREEN, relief='flat', bd=0, cursor='hand2').pack(side='right')
        self.suggestion_grid = tk.Frame(self.welcome, bg=PAPER)
        self.suggestion_grid.pack(fill='x', pady=(11, 0))
        self._render_suggestions()

    def _render_suggestions(self):
        for child in self.suggestion_grid.winfo_children():
            child.destroy()
        categories = {}
        for category, question in EXAMPLES:
            categories.setdefault(category, []).append(question)
        chosen_categories = random.sample(list(categories), min(4, len(categories)))
        for index, category in enumerate(chosen_categories):
            question = random.choice(categories[category])
            button = tk.Button(self.suggestion_grid, text=f'{category}\n{question}',
                               command=lambda q=question: self.send_question(q),
                               bg='white', fg=INK, justify='left', anchor='w',
                               activebackground=SOFT, relief='flat', bd=0,
                               highlightbackground=LINE, highlightthickness=1,
                               wraplength=320, padx=14, pady=14,
                               cursor='hand2', font=('Microsoft YaHei UI', 9))
            button.grid(row=index // 2, column=index % 2, sticky='nsew', padx=5, pady=5)
        self.suggestion_grid.grid_columnconfigure(0, weight=1)
        self.suggestion_grid.grid_columnconfigure(1, weight=1)

    def _add_message(self, kind, content, sources=None):
        row = tk.Frame(self.messages, bg=PAPER)
        row.pack(fill='x', padx=40, pady=(9, 15))
        label = '我  ·  我的提问' if kind == 'user' else '✦  ·  知识助手'
        tk.Label(row, text=label, bg=PAPER, fg='#61816a',
                 font=('Microsoft YaHei UI', 9, 'bold')).pack(anchor='w', pady=(0, 8))
        card = tk.Frame(row, bg=SOFT if kind == 'user' else 'white',
                        highlightbackground=LINE, highlightthickness=1)
        card.pack(fill='x')
        answer = _readonly_text(card, content, bg=SOFT if kind == 'user' else 'white',
                                font_size=11, padx=18, pady=14)
        answer.pack(fill='x')
        answer.bind('<MouseWheel>', self._scroll_messages, add='+')
        answer.bind('<Button-4>', self._scroll_messages, add='+')
        answer.bind('<Button-5>', self._scroll_messages, add='+')
        if sources:
            panel = tk.Frame(card, bg='white')
            def toggle():
                if panel.winfo_manager():
                    panel.pack_forget()
                else:
                    panel.pack(fill='x', padx=16, pady=(0, 12))
            tk.Button(card, text=f'资料来源 · {len(sources)}  ▸', command=toggle,
                      bg='white', fg=GREEN, relief='flat', bd=0,
                      cursor='hand2', font=('Microsoft YaHei UI', 9, 'bold')).pack(anchor='w', padx=16, pady=(2, 10))
            for source in sources:
                file = str(source.get('source_file') or '')
                detail = ' · '.join(str(source.get(name)) for name in ('section', 'page_or_slide')
                                    if source.get(name))
                line = tk.Frame(panel, bg='white')
                line.pack(fill='x', pady=3)
                if file.startswith(('https://', 'http://')):
                    tk.Button(line, text=file, command=lambda url=file: webbrowser.open(url),
                              bg='white', fg=GREEN, relief='flat', bd=0,
                              wraplength=550, justify='left', anchor='w',
                              cursor='hand2', font=('Microsoft YaHei UI', 8)).pack(anchor='w')
                else:
                    tk.Label(line, text=file, bg='white', fg=INK,
                             font=('Microsoft YaHei UI', 8), wraplength=550, justify='left').pack(anchor='w')
                if detail:
                    tk.Label(line, text=detail, bg='white', fg='#839487',
                             font=('Microsoft YaHei UI', 8)).pack(anchor='w')
        if kind == 'assistant':
            tk.Button(row, text='复制回答', command=lambda text=content: self._copy(text),
                      bg=PAPER, fg=MUTED, relief='flat', bd=0,
                      cursor='hand2', font=('Microsoft YaHei UI', 8)).pack(anchor='w', pady=(6, 0))
        self.root.after_idle(lambda: self.canvas.yview_moveto(1.0))
        return row

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def send_question(self, preset=None):
        if self.busy:
            return
        question = (preset if isinstance(preset, str) else self.input.get('1.0', 'end-1c')).strip()
        if not question:
            return
        if len(question) > 4000:
            messagebox.showwarning('问题过长', '问题最多 4000 个字符。', parent=self.root)
            return
        self.show_chat()
        if self.welcome.winfo_manager():
            self.welcome.pack_forget()
        self._add_message('user', question)
        self.loading_row = self._add_message('assistant', '正在检索资料并组织回答…')
        self.input.delete('1.0', 'end')
        self.busy = True
        self.send_button.configure(state='disabled')
        threading.Thread(target=self._ask, args=(question, self.thread_id), daemon=True).start()

    def _ask(self, question, thread_id):
        try:
            from graph import ask
            result = ask(question, thread_id=thread_id, request_id=str(uuid.uuid4()))
            self.pending.put((question, result.get('answer') or '没有收到可显示的答案。',
                              collect_sources(result)))
        except Exception as exc:
            logging.warning('本地问答失败 error_type=%s', type(exc).__name__)
            self.pending.put((question, '问答暂时不可用，请检查模型配置或稍后重试。', []))

    def _poll(self):
        try:
            while True:
                question, answer, sources = self.pending.get_nowait()
                self.loading_row.destroy()
                self._add_message('assistant', answer, sources)
                turn = {'thread_id': self.thread_id, 'question': question,
                        'answer': answer, 'sources': sources}
                try:
                    self.turns = save_history(self.home, [*self.turns, turn])
                except OSError:
                    logging.exception('保存历史对话失败')
                    messagebox.showwarning('保存失败', '回答已显示，但未能保存到本机历史记录。', parent=self.root)
                self._render_history()
                self.busy = False
                self.send_button.configure(state='normal')
                self.input.focus_set()
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._poll)

    def _render_history(self):
        for child in self.history_items.winfo_children():
            child.destroy()
        items = conversations(self.turns)
        if not items:
            self.clear_button.pack_forget()
            tk.Label(self.history_items, text='暂无记录', bg=SIDEBAR, fg='#91ac99',
                     font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=8, pady=7)
            return
        if not self.clear_button.winfo_manager():
            self.clear_button.pack(side='right')
        for item in items:
            self._add_history_card(item)
        self.history_canvas.yview_moveto(0)

    def _add_history_card(self, item):
        thread_id = item['thread_id']
        active = thread_id == self.thread_id
        base = '#315b43' if active else SIDEBAR
        card = tk.Frame(self.history_items, bg=base, cursor='hand2',
                        highlightthickness=1 if active else 0,
                        highlightbackground='#628a6d', takefocus=1)
        card.pack(fill='x', padx=2, pady=2)
        title = item['title'].replace('\n', ' ').strip()[:26]
        title_label = tk.Label(card, text=title, bg=base, fg='#e9f1e6',
                               font=('Microsoft YaHei UI', 9, 'bold'), anchor='w', cursor='hand2')
        title_label.pack(fill='x', padx=9, pady=(8, 1))
        count_label = tk.Label(card, text=f'{item["count"]} 轮问答', bg=base, fg='#a9c4ae',
                               font=('Microsoft YaHei UI', 8), anchor='w', cursor='hand2')
        count_label.pack(fill='x', padx=9, pady=(0, 8))

        def paint(color):
            for widget in (card, title_label, count_label):
                widget.configure(bg=color)

        def select(_event=None):
            if not self.busy:
                self._restore(thread_id)

        for widget in (card, title_label, count_label):
            widget.bind('<Button-1>', select)
            widget.bind('<MouseWheel>', self._scroll_history)
            widget.bind('<Button-4>', self._scroll_history)
            widget.bind('<Button-5>', self._scroll_history)
            if not active:
                widget.bind('<Enter>', lambda _event: paint('#29493b'))
                widget.bind('<Leave>', lambda _event: paint(SIDEBAR))
        card.bind('<Return>', select)
        card.bind('<space>', select)

    def _restore(self, thread_id):
        self.thread_id = thread_id
        self.show_chat()
        for child in self.messages.winfo_children():
            child.destroy()
        self._show_welcome()
        matching = [turn for turn in self.turns if turn['thread_id'] == thread_id]
        if matching:
            self.welcome.pack_forget()
        for turn in matching:
            self._add_message('user', turn['question'])
            self._add_message('assistant', turn['answer'], turn.get('sources'))
        self._render_history()

    def new_chat(self):
        if self.busy:
            return
        self.thread_id = str(uuid.uuid4())
        for child in self.messages.winfo_children():
            child.destroy()
        self._show_welcome()
        self._render_history()
        self.show_chat()
        self.input.focus_set()

    def clear_history(self):
        if self.busy:
            return
        if not messagebox.askyesno('清空历史', '确定清空本机保存的 30 轮问答吗？', parent=self.root):
            return
        self.turns = save_history(self.home, [])
        self.new_chat()

    def show_chat(self):
        self.doc_page.pack_forget()
        if not self.chat_page.winfo_manager():
            self.chat_page.pack(fill='both', expand=True)
        self.timeline_panel.pack_forget()
        if not self.history_panel.winfo_manager():
            self.history_panel.pack(fill='both', expand=True)
        self._paint_background_button(False)

    def show_document(self):
        self.chat_page.pack_forget()
        if not self.doc_page.winfo_manager():
            self.doc_page.pack(fill='both', expand=True)
        self.history_panel.pack_forget()
        if not self.timeline_panel.winfo_manager():
            self.timeline_panel.pack(fill='both', expand=True)
        self._paint_background_button(True)

    def _load_document(self):
        path = Path(__file__).with_name('docs') / '3820背景.md'
        content = path.read_text(encoding='utf-8')
        widget = self.doc_text
        widget.tag_configure('h1', font=('Microsoft YaHei UI', 20, 'bold'), foreground=INK,
                             spacing1=16, spacing3=16)
        widget.tag_configure('h2', font=('Microsoft YaHei UI', 14, 'bold'), foreground=GREEN,
                             spacing1=18, spacing3=10)
        widget.tag_configure('link', foreground=GREEN, underline=True)
        for line in content.splitlines():
            tag = 'h1' if line.startswith('# ') else 'h2' if line.startswith('## ') else None
            line = line.lstrip('# ').replace('**', '') if tag else line
            cursor = 0
            for match in re.finditer(r'\[([^\]]+)\]\((https?://[^)]+)\)', line):
                widget.insert('end', line[cursor:match.start()], tag)
                label, url = match.groups()
                link_tag = f'link_{widget.index("end-1c").replace(".", "_")}'
                widget.insert('end', label, ('link', link_tag))
                widget.tag_bind(link_tag, '<Button-1>', lambda _event, address=url: webbrowser.open(address))
                widget.tag_bind(link_tag, '<Enter>', lambda _event: widget.configure(cursor='hand2'))
                widget.tag_bind(link_tag, '<Leave>', lambda _event: widget.configure(cursor='arrow'))
                cursor = match.end()
            widget.insert('end', line[cursor:] + '\n', tag)
        widget.configure(state='disabled')

    def _first_run_settings(self):
        try:
            config = read_model_config(self.home)
        except (OSError, ValueError, UnicodeError):
            config = {}
        if not (config.get('ARK_API_KEY') and config.get('LLM_MODEL')):
            self.show_settings()

    def show_settings(self):
        try:
            current = read_model_config(self.home)
        except (OSError, ValueError, UnicodeError):
            current = {}
        dialog = tk.Toplevel(self.root)
        dialog.title('豆包 API 设置')
        scale = getattr(self.root, 'ui_scale', 1.0)
        dialog.geometry(f'{round(500 * scale)}x{round(455 * scale)}')
        dialog.minsize(round(460 * scale), round(430 * scale))
        dialog.configure(bg=PAPER)
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text='配置豆包 API', bg=PAPER, fg=INK,
                 font=('Microsoft YaHei UI', 17, 'bold')).pack(anchor='w', padx=25, pady=(20, 6))
        tk.Label(dialog, text='请填写火山方舟控制台提供的密钥和已开通的模型 ID。密钥在本机加密保存。',
                 bg=PAPER, fg=MUTED, wraplength=450, justify='left',
                 font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=25, pady=(0, 12))
        form = tk.Frame(dialog, bg=PAPER)
        form.pack(fill='x', padx=25)
        fields = {}
        for key, title, secret in (
            ('ARK_API_KEY', 'API Key（留空表示不修改）', True),
            ('LLM_MODEL', '对话模型 ID', False),
            ('EMBED_MODEL', '向量模型 ID（可选）', False),
            ('ARK_BASE_URL', 'API 地址', False),
        ):
            tk.Label(form, text=title, bg=PAPER, fg=INK,
                     font=('Microsoft YaHei UI', 9, 'bold')).pack(anchor='w', pady=(9, 4))
            entry = tk.Entry(form, font=('Microsoft YaHei UI', 10), show='*' if secret else '',
                             bg='white', fg=INK, relief='solid', bd=1)
            entry.pack(fill='x', ipady=5)
            if not secret:
                entry.insert(0, current.get(key) or
                             ('https://ark.cn-beijing.volces.com/api/v3' if key == 'ARK_BASE_URL' else ''))
            fields[key] = entry

        def save():
            config = {name: widget.get().strip() for name, widget in fields.items()}
            config['ARK_API_KEY'] = config['ARK_API_KEY'] or current.get('ARK_API_KEY', '')
            if (not config['ARK_API_KEY'] or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',
                                                             config['LLM_MODEL'])):
                messagebox.showerror('配置无效', '请填写 API Key 和有效的对话模型 ID。', parent=dialog)
                return
            if config['EMBED_MODEL'] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',
                                                           config['EMBED_MODEL']):
                messagebox.showerror('配置无效', '向量模型 ID 格式无效。', parent=dialog)
                return
            if urlsplit(config['ARK_BASE_URL']).scheme != 'https':
                messagebox.showerror('配置无效', 'API 地址必须使用 HTTPS。', parent=dialog)
                return
            try:
                Settings(ark_api_key=config['ARK_API_KEY'], llm_model=config['LLM_MODEL'],
                         embed_model=config['EMBED_MODEL'] or None,
                         ark_base_url=config['ARK_BASE_URL'])
                write_model_config(config, self.home)
                apply_model_config(config)
            except (OSError, ValueError) as exc:
                logging.warning('保存模型配置失败 error_type=%s', type(exc).__name__)
                messagebox.showerror('保存失败', '无法保存模型配置，请检查当前用户目录。', parent=dialog)
                return
            dialog.destroy()
        buttons = tk.Frame(dialog, bg=PAPER)
        buttons.pack(fill='x', padx=25, pady=22)
        tk.Button(buttons, text='保存配置', command=save, bg=GREEN, fg='white',
                  relief='flat', bd=0, padx=19, pady=8,
                  font=('Microsoft YaHei UI', 10, 'bold'), cursor='hand2').pack(side='right')
        tk.Button(buttons, text='取消', command=dialog.destroy, bg=PAPER, fg=MUTED,
                  relief='flat', bd=0, padx=10, pady=8).pack(side='right', padx=8)

    def import_files(self):
        selected = filedialog.askopenfilenames(parent=self.root, title='导入知识资料',
                                               filetypes=[('支持的资料', '*.txt *.docx *.pptx')])
        if not selected:
            return
        destination = self.home / 'knowledge' / 'data'
        destination.mkdir(parents=True, exist_ok=True)
        copied = 0
        for name in selected:
            path = Path(name)
            if path.suffix.lower() not in {'.txt', '.docx', '.pptx'} or not path.is_file():
                continue
            target = destination / path.name
            if target.exists() and not messagebox.askyesno('覆盖资料', f'{path.name} 已存在，是否覆盖？', parent=self.root):
                continue
            shutil.copy2(path, target)
            copied += 1
        if copied:
            messagebox.showinfo('导入完成', f'已导入 {copied} 个文件，新问题会检索这些资料。', parent=self.root)
