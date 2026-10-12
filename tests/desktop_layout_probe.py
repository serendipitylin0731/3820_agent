"""Runs in a child process so Tcl objects cannot outlive the test thread."""

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_app.gui import DesktopApp, _readonly_text


try:
    root = tk.Tk()
except tk.TclError:
    raise SystemExit(77)

try:
    root.geometry('700x500+20000+20000')
    canvas = tk.Canvas(root, yscrollincrement=1)
    canvas.pack(fill='both', expand=True)
    body = tk.Frame(canvas)
    window = canvas.create_window((0, 0), window=body, anchor='nw')
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
    body.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')))
    label = tk.Label(body, text='资料来源')
    label.pack()
    answer = _readonly_text(body, ('这是一段需要完整显示的回答。' * 12 + '\n') * 50,
                            bg='white')
    answer.pack(fill='x')
    for _ in range(8):
        root.update()
    first = int(answer.cget('height'))
    assert first > 120
    assert answer.yview() == (0.0, 1.0)
    root.geometry('420x500+20000+20000')
    # Off-screen window managers may ignore the geometry change; resize the
    # canvas window too, as the real conversation canvas does on Configure.
    canvas.itemconfigure(window, width=420)
    for _ in range(8):
        root.update()
    assert int(answer.cget('height')) > first
    assert answer.yview() == (0.0, 1.0)

    app = DesktopApp.__new__(DesktopApp)
    app.canvas = canvas
    app._message_wheel_remainder = 0.0
    app._bind_chat_wheel(body)
    canvas.yview_moveto(0.3)
    root.update()
    before = canvas.canvasy(0)
    label.event_generate('<MouseWheel>', delta=-120)
    root.update()
    assert 62 <= canvas.canvasy(0) - before <= 66
    before = canvas.canvasy(0)
    answer.event_generate('<MouseWheel>', delta=-120)
    root.update()
    assert 62 <= canvas.canvasy(0) - before <= 66
    assert answer.yview() == (0.0, 1.0)

    before = canvas.canvasy(0)
    for _ in range(3):
        answer.event_generate('<MouseWheel>', delta=-1)
    root.update()
    assert 1 <= canvas.canvasy(0) - before <= 2
finally:
    root.destroy()
