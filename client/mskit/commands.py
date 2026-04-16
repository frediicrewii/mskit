"""Non-interactive commands: login, logout, users, chats, new-group, last."""
import getpass
import sys
from datetime import datetime
from pathlib import Path

from .api import Api, ApiError
from .config import Config


# ANSI colors for plain-terminal output (works without prompt_toolkit)
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


def _fmt_time(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(d.tzinfo) if d.tzinfo else datetime.now()
        if d.date() == now.date():
            return d.strftime("%H:%M")
        return d.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16]


def cmd_login(config: Config, api: Api, register: bool = False) -> int:
    print(f"{C.BOLD}tg login{C.RESET} — server: {config.server}")
    try:
        username = input("username: ").strip().lower()
        if not username:
            print(f"{C.RED}username required{C.RESET}")
            return 1
        if register:
            display_name = input("display name: ").strip() or username
        password = getpass.getpass("password: ")
        if register:
            res = api.register(username, display_name, password)
        else:
            res = api.login(username, password)
    except ApiError as e:
        print(f"{C.RED}error: {e}{C.RESET}")
        return 1
    except (EOFError, KeyboardInterrupt):
        print()
        return 1

    config.token = res["access_token"]
    config.username = res["user"]["username"]
    config.user_id = res["user"]["id"]
    config.display_name = res["user"]["display_name"]
    config.save()
    print(f"{C.GREEN}logged in as @{config.username}{C.RESET}")
    return 0


def cmd_logout(config: Config) -> int:
    config.clear_auth()
    print(f"{C.GREEN}logged out{C.RESET}")
    return 0


def cmd_whoami(config: Config) -> int:
    if not config.token:
        print(f"{C.YELLOW}not logged in — run `tg login`{C.RESET}")
        return 1
    print(f"@{config.username}  ({config.display_name})")
    print(f"server: {config.server}")
    return 0


def cmd_users(api: Api) -> int:
    try:
        users = api.list_users()
    except ApiError as e:
        print(f"{C.RED}error: {e}{C.RESET}")
        return 1
    if not users:
        print("no users")
        return 0
    print(f"{C.BOLD}{'username':<20} {'display name':<30} status{C.RESET}")
    print(f"{C.GRAY}{'-' * 60}{C.RESET}")
    for u in users:
        dot = f"{C.GREEN}●{C.RESET}" if u["is_online"] else f"{C.GRAY}○{C.RESET}"
        print(f"@{u['username']:<19} {u['display_name']:<30} {dot}")
    return 0


def cmd_chats(api: Api, me_id: int) -> int:
    try:
        chats = api.list_chats()
    except ApiError as e:
        print(f"{C.RED}error: {e}{C.RESET}")
        return 1
    if not chats:
        print(f"{C.DIM}no chats — try `tg <username>` to start one{C.RESET}")
        return 0
    print(f"{C.BOLD}your chats:{C.RESET}")
    for c in chats:
        if c["is_group"]:
            title = f"{C.CYAN}#{c['name']}{C.RESET}  {C.GRAY}({len(c['members'])} members){C.RESET}"
        else:
            other = next((m for m in c["members"] if m["id"] != me_id), None)
            if other:
                dot = f"{C.GREEN}●{C.RESET}" if other["is_online"] else f"{C.GRAY}○{C.RESET}"
                title = f"{dot} {C.BOLD}{other['display_name']}{C.RESET} @{other['username']}"
            else:
                title = "(empty chat)"
        lm = c.get("last_message")
        if lm:
            when = _fmt_time(lm["created_at"])
            preview = lm.get("content") or ("📎 " + (lm.get("file_name") or "file"))
            if len(preview) > 50:
                preview = preview[:47] + "..."
            print(f"  {title}")
            print(f"    {C.GRAY}{when}  {preview}{C.RESET}")
        else:
            print(f"  {title}")
    return 0


def cmd_new_group(api: Api, name: str, usernames: list) -> int:
    try:
        chat = api.create_group(name, usernames)
    except ApiError as e:
        print(f"{C.RED}error: {e}{C.RESET}")
        return 1
    print(f"{C.GREEN}group #{chat['name']} created ({len(chat['members'])} members){C.RESET}")
    for m in chat["members"]:
        print(f"  @{m['username']}  ({m['display_name']})")
    return 0


def print_messages(messages: list, me_id: int, is_group: bool, api: Api):
    """Pretty-print a list of messages to stdout (non-interactive mode)."""
    if not messages:
        print(f"{C.DIM}no messages yet{C.RESET}")
        return
    prev_sender = None
    for msg in messages:
        is_me = msg["sender_id"] == me_id
        time_str = _fmt_time(msg["created_at"])
        if is_me:
            sender_col = f"{C.YELLOW}you{C.RESET}"
        else:
            sender_col = f"{C.GREEN}{msg['sender_name']}{C.RESET}"
        body = ""
        if msg.get("content"):
            body = msg["content"]
        if msg.get("file_url"):
            icon = "📷" if msg.get("file_type") == "image" else "📎"
            fname = msg.get("file_name") or "file"
            url = api.resolve_file_url(msg["file_url"])
            link = f"{C.CYAN}{icon} {fname} → {url}{C.RESET}"
            body = body + "\n        " + link if body else link
        print(f"{C.GRAY}{time_str}{C.RESET}  {sender_col}: {body}")
        prev_sender = msg["sender_id"]


def cmd_last(api: Api, chat: dict, n: int, me_id: int) -> int:
    try:
        messages = api.get_messages(chat["id"], limit=n)
    except ApiError as e:
        print(f"{C.RED}error: {e}{C.RESET}")
        return 1
    if chat["is_group"]:
        print(f"{C.BOLD}{C.CYAN}#{chat['name']}{C.RESET} {C.GRAY}(last {len(messages)} messages){C.RESET}")
    else:
        other = next((m for m in chat["members"] if m["id"] != me_id), None)
        if other:
            dot = f"{C.GREEN}●{C.RESET}" if other["is_online"] else f"{C.GRAY}○{C.RESET}"
            print(f"{dot} {C.BOLD}{other['display_name']}{C.RESET} @{other['username']} {C.GRAY}(last {len(messages)}){C.RESET}")
    print(f"{C.GRAY}{'-' * 60}{C.RESET}")
    print_messages(messages, me_id, chat["is_group"], api)
    return 0
