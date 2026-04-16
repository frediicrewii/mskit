"""Full-screen interactive chat TUI using prompt_toolkit.

Self-contained version: built-in REST poller (no WebSocket), SSL verification
forced off in Api client. Works through corporate proxies that block WebSocket.
"""
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame

from .api import Api, ApiError


# ---------- force SSL verification OFF on the Api's httpx client ----------
# This is necessary for corporate networks with MITM proxies that intercept
# HTTPS traffic with a custom certificate.
import httpx as _httpx
_orig_api_client = Api.client.fget  # type: ignore


def _patched_client(self):
    if self._client is None:
        self._client = _httpx.Client(
            base_url=self.config.server,
            timeout=15,
            verify=False,
        )
    return self._client


Api.client = property(_patched_client)  # type: ignore

# Silence the InsecureRequestWarning httpx prints about verify=False
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


STYLE = Style.from_dict({
    "status": "bg:#2b5278 #ffffff bold",
    "status.offline": "bg:#882222 #ffffff bold",
    "title": "bold #3390ec",
    "time": "#6c7883",
    "sender": "bold #7bc862",
    "sender.me": "bold #eda86c",
    "file": "#3390ec underline",
    "system": "italic #8b98a5",
    "error": "bold #e17076",
})


def _fmt_time(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return d.strftime("%H:%M")
    except Exception:
        return "??:??"


# ---------- Built-in REST poller (no WebSocket) ----------
class _Poller:
    """Polls the server every `interval` seconds for new messages."""

    def __init__(self, api: Api, chat_id: int, initial_last_id: int,
                 on_new_messages, on_status, interval: float = 2.0):
        self.api = api
        self.chat_id = chat_id
        self.last_id = initial_last_id
        self.on_new_messages = on_new_messages
        self.on_status = on_status
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

    def _try_get_new(self):
        """Try the new /since/{id} endpoint first, fall back to full reload."""
        try:
            return self.api.get_messages_since(self.chat_id, self.last_id)
        except (ApiError, AttributeError):
            # Server doesn't have /since endpoint or client lib too old —
            # fall back to fetching last 50 and filtering by id locally.
            try:
                all_msgs = self.api.get_messages(self.chat_id, limit=50)
                return [m for m in all_msgs if m["id"] > self.last_id]
            except ApiError:
                raise

    def _run(self):
        while not self._stop.is_set():
            try:
                new_msgs = self._try_get_new()
                if not self._connected:
                    self._connected = True
                    self._safe_status(True)
                if new_msgs:
                    for m in new_msgs:
                        if m["id"] > self.last_id:
                            self.last_id = m["id"]
                    self._safe_new_messages(new_msgs)
            except Exception:
                if self._connected:
                    self._connected = False
                    self._safe_status(False)
            for _ in range(int(self.interval * 10)):
                if self._stop.is_set():
                    return
                time.sleep(0.1)

    def _safe_status(self, c):
        try:
            self.on_status(c)
        except Exception:
            pass

    def _safe_new_messages(self, msgs):
        try:
            self.on_new_messages(msgs)
        except Exception:
            pass


class ChatTUI:
    def __init__(self, api: Api, chat: dict):
        self.api = api
        self.chat = chat
        self.me_id = api.config.user_id
        self.messages: list = []
        self.connected = False
        self.status_text = ""

        self.input_buffer = Buffer(multiline=False, accept_handler=self._on_accept)
        self.messages_control = FormattedTextControl(text=self._render_messages, focusable=False)
        self.status_control = FormattedTextControl(text=self._render_status)

        title = self._chat_title()
        messages_window = Window(
            content=self.messages_control,
            wrap_lines=True,
            always_hide_cursor=True,
        )
        input_window = Window(
            content=BufferControl(buffer=self.input_buffer),
            height=1,
        )
        status_window = Window(
            content=self.status_control,
            height=1,
            style="class:status",
            align=WindowAlign.LEFT,
        )

        body = HSplit([
            Frame(messages_window, title=title),
            Frame(input_window, title="Message (Enter to send, Ctrl-Q to quit, Ctrl-F to attach file)"),
            status_window,
        ])

        kb = KeyBindings()

        @kb.add("c-q")
        @kb.add("c-c")
        def _(event):
            event.app.exit()

        @kb.add("c-f")
        def _(event):
            self._attach_file()

        @kb.add("c-r")
        def _(event):
            self._reload_messages()

        self.app = Application(
            layout=Layout(body, focused_element=input_window),
            key_bindings=kb,
            style=STYLE,
            full_screen=True,
            mouse_support=False,
        )

        # initial load
        self._reload_messages()
        initial_last = max((m["id"] for m in self.messages), default=0)

        # poller (no WebSocket — works through corporate firewalls)
        self.poller = _Poller(
            api=api,
            chat_id=chat["id"],
            initial_last_id=initial_last,
            on_new_messages=self._on_new_messages,
            on_status=self._on_poller_status,
            interval=2.0,
        )

    # ---------- rendering ----------
    def _chat_title(self) -> str:
        if self.chat["is_group"]:
            return f"# {self.chat['name']} ({len(self.chat['members'])} members)"
        other = next((m for m in self.chat["members"] if m["id"] != self.me_id), None)
        if other:
            dot = "●" if other.get("is_online") else "○"
            return f"{dot} {other['display_name']} (@{other['username']})"
        return "chat"

    def _render_messages(self):
        if not self.messages:
            return [("class:system", "No messages yet. Say hi!\n")]
        lines = []
        prev_sender = None
        is_group = self.chat["is_group"]
        for msg in self.messages:
            is_me = msg["sender_id"] == self.me_id
            sender_style = "class:sender.me" if is_me else "class:sender"
            time_str = _fmt_time(msg["created_at"])

            if is_group and msg["sender_id"] != prev_sender:
                prefix = msg["sender_name"]
            else:
                prefix = "you" if is_me else msg["sender_name"]

            lines.append(("class:time", f"{time_str} "))
            lines.append((sender_style, f"{prefix}: "))

            if msg.get("content"):
                lines.append(("", msg["content"]))
            if msg.get("file_url"):
                if msg.get("content"):
                    lines.append(("", "\n        "))
                icon = "📷" if msg.get("file_type") == "image" else "📎"
                fname = msg.get("file_name") or "file"
                url = self.api.resolve_file_url(msg["file_url"])
                lines.append(("class:file", f"{icon} {fname} — {url}"))

            lines.append(("", "\n"))
            prev_sender = msg["sender_id"]
        return lines

    def _render_status(self):
        left = "● Connected (polling)" if self.connected else "○ Connecting..."
        msg = self.status_text
        return [("", f" {left}"), ("", f"   {msg}" if msg else "")]

    def _set_status(self, text: str):
        self.status_text = text
        self._invalidate()

    def _invalidate(self):
        try:
            self.app.invalidate()
        except Exception:
            pass

    # ---------- actions ----------
    def _reload_messages(self):
        try:
            self.messages = self.api.get_messages(self.chat["id"], limit=50)
        except ApiError as e:
            self._set_status(f"load error: {e}")
        self._invalidate()

    def _on_accept(self, buffer: Buffer) -> bool:
        text = buffer.text.strip()
        if not text:
            return False
        try:
            sent = self.api.send_message(self.chat["id"], content=text)
            # immediately add it locally so the user sees it without waiting
            # for the next poll cycle
            if sent and not any(m["id"] == sent["id"] for m in self.messages):
                self.messages.append(sent)
                if sent["id"] > self.poller.last_id:
                    self.poller.last_id = sent["id"]
                self._invalidate()
        except ApiError as e:
            self._set_status(f"send error: {e}")
        buffer.reset()
        return False

    def _attach_file(self):
        import sys
        from prompt_toolkit.application import run_in_terminal

        def prompt_and_send():
            try:
                sys.stdout.write("\nFile path to upload (empty to cancel): ")
                sys.stdout.flush()
                path_str = sys.stdin.readline().strip()
                if not path_str:
                    return
                path = Path(path_str).expanduser()
                if not path.exists():
                    print(f"not found: {path}")
                    return
                print(f"uploading {path.name}...")
                up = self.api.upload_file(path)
                self.api.send_message(
                    self.chat["id"],
                    file_url=up["file_url"],
                    file_name=up["file_name"],
                    file_type=up["file_type"],
                )
                print("sent.")
            except ApiError as e:
                print(f"error: {e}")
            except Exception as e:
                print(f"error: {e}")

        run_in_terminal(prompt_and_send)

    # ---------- poller callbacks ----------
    def _on_new_messages(self, msgs):
        added = False
        for msg in msgs:
            if msg["chat_id"] != self.chat["id"]:
                continue
            if not any(m["id"] == msg["id"] for m in self.messages):
                self.messages.append(msg)
                added = True
        if added:
            self._invalidate()

    def _on_poller_status(self, connected: bool):
        self.connected = connected
        self._invalidate()

    # ---------- run ----------
    def run(self):
        self.poller.start()
        try:
            self.app.run()
        finally:
            self.poller.stop()
