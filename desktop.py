"""Windows desktop entry point: loopback FastAPI plus a persistent native window."""

import ctypes
import json
import logging
import socket
import sys
import threading
import time
from urllib.request import Request, urlopen

from desktop_runtime import prepare_desktop


HOST = '127.0.0.1'
PORT = 3820
URL = f'http://{HOST}:{PORT}/'


def _message(title: str, message: str):
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    else:
        print(f'{title}: {message}', file=sys.stderr)


def _listen():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind((HOST, PORT))
        sock.listen(128)
        return sock
    except OSError:
        sock.close()
        raise


def start_server():
    import uvicorn
    from app import app

    listener = _listen()
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT,
                                          log_level='warning', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    for _ in range(100):
        if not thread.is_alive():
            break
        try:
            with urlopen(URL + 'health', timeout=0.3) as response:
                if response.status == 200:
                    return server, thread, listener
        except (OSError, TimeoutError):
            time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=3)
    listener.close()
    raise RuntimeError('本地服务启动失败')


def main():
    smoke = '--smoke-test' in sys.argv
    try:
        home = prepare_desktop()
        server, thread, listener = start_server()
        try:
            if smoke:
                with urlopen(URL, timeout=3) as response:
                    if response.status != 200 or b'3820' not in response.read():
                        raise RuntimeError('界面资源未正确打包')
                with urlopen(URL + 'desktop/config', timeout=3) as response:
                    if response.status != 200:
                        raise RuntimeError('桌面设置接口不可用')
                question = json.dumps({'question': '1995年福州GDP是多少？',
                                       'thread_id': 'desktop-smoke-test'}, ensure_ascii=False).encode('utf-8')
                request = Request(URL + 'chat', data=question,
                                  headers={'Content-Type': 'application/json'}, method='POST')
                with urlopen(request, timeout=15) as response:
                    result = json.load(response)
                    if response.status != 200 or not result.get('answer'):
                        raise RuntimeError('问答功能未正确打包')
                return 0
            import webview
            webview.create_window('3820 · 战略知识助手', URL, width=1180, height=790,
                                  min_size=(760, 560), background_color='#f8faf6')
            webview.start(private_mode=False, storage_path=str(home / 'webview'))
            return 0
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            listener.close()
    except OSError as exc:
        logging.exception('桌面版启动失败')
        message = ('本机 3820 端口已被占用。请关闭已经打开的 3820 应用后重试。'
                   if getattr(exc, 'winerror', None) == 10048 else '无法启动应用，请检查本机服务和安装文件。')
        if not smoke:
            _message('3820 启动失败', message)
        return 1
    except Exception:
        logging.exception('桌面版启动失败')
        if not smoke:
            _message('3820 启动失败', '无法启动应用。请确认已安装 Microsoft Edge WebView2 Runtime，并重新安装应用。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
