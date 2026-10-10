"""Windows desktop entry point. The UI and agent run in one native process."""

import ctypes
import logging
import sys
import uuid

from desktop_runtime import prepare_desktop


def _message(title: str, message: str):
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    else:
        print(f'{title}: {message}', file=sys.stderr)


def _enable_high_dpi():
    """Ask Windows for sharp per-monitor rendering before Tk creates a window."""
    if sys.platform != 'win32':
        return
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _set_tk_scale(root):
    if sys.platform != 'win32':
        return
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id())
        if dpi > 0:
            root.tk.call('tk', 'scaling', dpi / 72)
            root.ui_scale = dpi / 96
    except (AttributeError, OSError):
        pass


def main():
    smoke = '--smoke-test' in sys.argv
    home = None
    root = None
    try:
        home = prepare_desktop()
        logging.basicConfig(filename=home / 'desktop.log', level=logging.INFO,
                            format='%(asctime)s %(levelname)s %(message)s',
                            encoding='utf-8')
        _enable_high_dpi()
        import tkinter as tk
        from desktop_gui import DesktopApp

        root = tk.Tk()
        _set_tk_scale(root)
        if smoke:
            root.withdraw()
        DesktopApp(root, home)
        if smoke:
            root.update_idletasks()
            root.update()
            from graph import ask
            result = ask('1995年福州GDP是多少？',
                         thread_id=f'desktop-smoke-{uuid.uuid4()}')
            if not result.get('answer'):
                raise RuntimeError('问答功能未正确打包')
            return 0
        root.mainloop()
        return 0
    except Exception:
        logging.exception('桌面版启动失败')
        if not smoke:
            location = str(home / 'desktop.log') if home else '当前用户的 AppData 目录'
            _message('3820 启动失败', f'无法启动应用。请查看日志：{location}')
        return 1
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == '__main__':
    raise SystemExit(main())
