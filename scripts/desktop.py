import socket
import sys
import threading
import time
import webview
import uvicorn

from backend.main import app


def reserve_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    port = reserve_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    deadline = time.monotonic() + 15
    while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.1)
    if not server.started:
        server.should_exit = True
        from tkinter import messagebox
        messagebox.showerror("Universal Converter", "The local conversion service could not start.")
        return
    try:
        webview.create_window(
            "Universal Converter",
            f"http://127.0.0.1:{port}",
            width=1280,
            height=800,
            min_size=(960, 640),
            text_select=False,
        )
        webview.start(private_mode=False)
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
