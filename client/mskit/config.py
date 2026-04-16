"""Config: server URL + saved token in ~/.config/tg/config.json"""
import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(os.environ.get("MSKIT_CONFIG_DIR", Path.home() / ".config" / "mskit"))
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_SERVER = os.environ.get("MSKIT_SERVER", "http://localhost:8000")


class Config:
    def __init__(self):
        self.server: str = DEFAULT_SERVER
        self.token: Optional[str] = None
        self.username: Optional[str] = None
        self.user_id: Optional[int] = None
        self.display_name: Optional[str] = None
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text())
                self.server = data.get("server", DEFAULT_SERVER)
                self.token = data.get("token")
                self.username = data.get("username")
                self.user_id = data.get("user_id")
                self.display_name = data.get("display_name")
            except Exception:
                pass

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "server": self.server,
            "token": self.token,
            "username": self.username,
            "user_id": self.user_id,
            "display_name": self.display_name,
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2))
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except Exception:
            pass

    def clear_auth(self):
        self.token = None
        self.username = None
        self.user_id = None
        self.display_name = None
        self.save()

    @property
    def ws_url(self) -> str:
        base = self.server
        if base.startswith("https://"):
            return "wss://" + base[len("https://"):]
        if base.startswith("http://"):
            return "ws://" + base[len("http://"):]
        return base
