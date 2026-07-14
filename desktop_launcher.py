import atexit
import os
import socket
import subprocess
import sys
import time
import urllib.request

import webview

APP_FILE = "caption_app.py"
WINDOW_TITLE = "🎬 動画字幕自動生成アプリ"


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", os.path.join(base_dir, APP_FILE),
            "--server.port", str(port),
            "--server.address", "127.0.0.1",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=base_dir,
    )
    atexit.register(proc.terminate)

    if not wait_for_server(url):
        proc.terminate()
        raise RuntimeError("アプリの起動に失敗しました（ffmpegやPythonの設定を確認してください）")

    webview.create_window(WINDOW_TITLE, url, width=1200, height=860, min_size=(900, 600))
    webview.start()

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


if __name__ == "__main__":
    main()
