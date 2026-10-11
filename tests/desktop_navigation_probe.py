"""Exercise the native sidebar modes with saved history in an isolated process."""

import sys
import tempfile
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_gui import DesktopApp, _readonly_text
from desktop_history import save_history


try:
    root = tk.Tk()
except tk.TclError:
    raise SystemExit(77)

try:
    root.geometry('1000x700+20000+20000')
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        save_history(home, [{'thread_id': 'saved-session', 'question': '旧问题',
                             'answer': '旧回答', 'sources': []}])
        DesktopApp._first_run_settings = lambda self: None
        app = DesktopApp(root, home)
        root.update_idletasks()
        assert app.thread_id != 'saved-session'
        assert app.welcome.winfo_manager()
        assert len(app.turns) == 1
        assert app.history_panel.winfo_manager()
        assert not app.timeline_panel.winfo_manager()
        document = app.doc_text.get('1.0', 'end')
        assert '**1995' not in document
        assert '1995 年：三年起步。' in document
        assert app.doc_text.tag_ranges('strong')
        assert app.doc_text.tag_ranges('link')
        sample = _readonly_text(root, '**加粗**和[来源](https://example.org)', bg='white')
        assert sample.get('1.0', 'end').startswith('加粗和来源')
        assert sample.tag_ranges('strong') and sample.tag_ranges('link')
        sample.destroy()
        assert app._logo_images

        assert app.background_label.bind('<Button-1>')
        app.show_document()
        root.update_idletasks()
        assert app.timeline_panel.winfo_manager()
        assert not app.history_panel.winfo_manager()
        assert app.doc_page.winfo_manager()

        app.show_chat()
        root.update_idletasks()
        assert app.history_panel.winfo_manager()
        assert not app.timeline_panel.winfo_manager()
        assert app.welcome.winfo_manager()

        history_card = app.history_items.winfo_children()[0]
        assert history_card.winfo_children()[0].bind('<Button-1>')
        app._restore('saved-session')
        root.update_idletasks()
        assert app.thread_id == 'saved-session'
        assert not app.welcome.winfo_manager()
        assert app.history_panel.winfo_manager()
finally:
    root.destroy()
