"""REST polling client — fallback for environments where WebSocket is blocked
(corporate Cloudflare/proxy combo returning 403 on WS upgrades, etc).

Interface mirrors WSClient so tui.py can use either interchangeably:
    - on_message(data) — called with {"type": "new_message", "message": {...}}
      for every new message since last poll
    - on_status(connected) — called True when poll succeeds, False on error
"""
import threading
import time
from typing import Callable, Optional

from .api import Api, ApiError


class Poller:
    """Polls /api/messages/{chat_id}/since/{after_id} every N seconds."""

    def __init__(self, api: Api, chat_id: int, initial_last_id: int,
                 on_message: Callable[[dict], None],
                 on_status: Optional[Callable[[bool], None]] = None,
                 interval: float = 2.0):
        self.api = api
        self.chat_id = chat_id
        self.last_id = initial_last_id
        self.on_message = on_message
        self.on_status = on_status or (lambda _c: None)
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._connected = False

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                new_msgs = self.api.get_messages_since(self.chat_id, self.last_id)
                if not self._connected:
                    self._connected = True
                    try:
                        self.on_status(True)
                    except Exception:
                        pass
                for msg in new_msgs:
                    if msg["id"] > self.last_id:
                        self.last_id = msg["id"]
                    try:
                        self.on_message({"type": "new_message", "message": msg})
                    except Exception:
                        pass
            except ApiError:
                if self._connected:
                    self._connected = False
                    try:
                        self.on_status(False)
                    except Exception:
                        pass
            except Exception:
                if self._connected:
                    self._connected = False
                    try:
                        self.on_status(False)
                    except Exception:
                        pass
            # sleep in 0.1s slices so stop is responsive
            slices = int(self.interval * 10)
            for _ in range(slices):
                if self._stop.is_set():
                    return
                time.sleep(0.1)
