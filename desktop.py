"""Windows desktop entry point. The UI and agent run in one native process."""

import ctypes
import logging
import sys
import tempfile
import uuid
from pathlib import Path

from desktop_runtime import prepare_desktop

APP_USER_MODEL_ID = 'edu.sjtu.serendipity.3820Agent'


def _set_app_user_model_id():
    """Give the taskbar the same identity as the installed shortcuts."""
    if sys.platform == 'win32':
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        if result != 0:
            raise OSError(f'无法设置 Windows 应用标识：{result}')


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
        _set_app_user_model_id()
        _enable_high_dpi()
        import tkinter as tk
        from desktop_gui import DesktopApp

        root = tk.Tk()
        _set_tk_scale(root)
        if smoke:
            root.withdraw()
        DesktopApp(root, home)
        if smoke:
            from desktop_runtime import read_model_config, write_model_config
            with tempfile.TemporaryDirectory(prefix='config-smoke-', dir=home) as directory:
                config = {'ARK_API_KEY': 'build-smoke-key',
                          'LLM_MODEL': 'build-smoke-chat', 'EMBED_MODEL': '',
                          'ARK_BASE_URL': 'https://ark.cn-beijing.volces.com/api/v3'}
                target = Path(directory)
                written = write_model_config(config, target)
                if written.parent != target or read_model_config(target) != config:
                    raise RuntimeError('Windows 配置加密、保存或读取失败')
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
