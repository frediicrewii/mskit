"""WebSocket client running in background thread with auto-reconnect."""
import json
import os
import ssl
import threading
import time
from typing import Callable, Optional

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None


def _ws_sslopt():
    """SSL options for websocket-client, mirroring api.py."""
    if os.environ.get("MSKIT_INSECURE", "").lower() in ("1", "true", "yes"):
        return {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
    ca = os.environ.get("MSKIT_CA_BUNDLE")
    if ca:
        return {"ca_certs": ca}
    return None


class WSClient:
    """Background WebSocket connection with auto-reconnect every 3 seconds."""

    def __init__(self, ws_url: str, token: str, on_message: Callable[[dict], None],
                 on_status: Optional[Callable[[bool], None]] = None):
        if websocket is None:
            raise RuntimeError("websocket-client is not installed (pip install websocket-client)")
        self.url = f"{ws_url}/ws?token={token}"
        self.on_message = on_message
        self.on_status = on_status or (lambda _connected: None)
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._connected = False

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass

    def _run(self):
        while not self._stop.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_msg,
                    on_close=self._on_close,
                    on_error=self._on_error,
                )
                sslopt = _ws_sslopt()
                kwargs = {"ping_interval": 25, "ping_timeout": 10}
                if sslopt:
                    kwargs["sslopt"] = sslopt
                self._ws.run_forever(**kwargs)
            except Exception:
                pass
            if self._stop.is_set():
                break
            # mark disconnected and wait before reconnecting
            if self._connected:
                self._connected = False
                try:
                    self.on_status(False)
                except Exception:
                    pass
            for _ in range(30):  # 3 seconds in 0.1s slices
                if self._stop.is_set():
                    return
                time.sleep(0.1)

    def _on_open(self, _ws):
        self._connected = True
        try:
            self.on_status(True)
        except Exception:
            pass

    def _on_msg(self, _ws, message):
        try:
            data = json.loads(message)
        except Exception:
            return
        try:
            self.on_message(data)
        except Exception:
            pass

    def _on_close(self, _ws, _code, _reason):
        if self._connected:
            self._connected = False
            try:
                self.on_status(False)
            except Exception:
                pass

    def _on_error(self, _ws, _err):
        pass
