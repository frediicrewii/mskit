"""Entry point for `mskit` command.

Usage examples:
  mskit                          open full-screen TUI with chat list
  mskit login                       interactive login
  mskit register                    interactive registration
  mskit logout
  mskit whoami
  mskit server https://my-server    set server URL
  mskit users                       list all users
  mskit chats                       list your chats
  mskit alice                       open personal chat with @alice (TUI)
  mskit -g "Team Chat"              open group chat (TUI)
  mskit -g Team --last 15           print last 15 messages and exit
  mskit alice --last 20
  mskit new-group Team alice bob carol
"""
import argparse
import sys

from .api import Api, ApiError
from .config import Config
from . import commands as cmd


def _require_auth(config: Config) -> bool:
    if not config.token:
        print("\033[93mnot logged in — run `mskit login` first\033[0m", file=sys.stderr)
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mskit",
        description="Terminal messenger client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  mskit login                 log in\n"
               "  mskit alice                 chat with @alice\n"
               "  mskit -g \"Team\"             open group\n"
               "  mskit -g Team --last 15     show last 15 messages\n"
               "  mskit new-group Team alice bob\n",
    )
    parser.add_argument("-g", "--group", action="store_true",
                        help="target is a group name, not a username")
    parser.add_argument("--last", type=int, metavar="N",
                        help="print last N messages and exit (non-interactive)")
    parser.add_argument("target", nargs="*",
                        help="command or username/group (see examples)")
    args = parser.parse_args(argv)

    config = Config()
    api = Api(config)

    # ----- dispatch sub-commands -----
    if not args.target:
        # Plain `mskit` — open TUI chat list
        if not _require_auth(config):
            return 1
        return launch_chat_list(api, config)

    first = args.target[0]

    # login / register
    if first == "login":
        return cmd.cmd_login(config, api, register=False)
    if first == "register":
        return cmd.cmd_login(config, api, register=True)
    if first == "logout":
        return cmd.cmd_logout(config)
    if first == "whoami":
        return cmd.cmd_whoami(config)

    if first == "server":
        if len(args.target) < 2:
            print(f"current server: {config.server}")
            return 0
        config.server = args.target[1].rstrip("/")
        config.save()
        print(f"\033[92mserver set to {config.server}\033[0m")
        return 0

    if first == "users":
        if not _require_auth(config):
            return 1
        return cmd.cmd_users(api)

    if first == "chats":
        if not _require_auth(config):
            return 1
        return cmd.cmd_chats(api, config.user_id)

    if first == "new-group":
        if not _require_auth(config):
            return 1
        if len(args.target) < 3:
            print("usage: mskit new-group <name> <user1> <user2> ...", file=sys.stderr)
            return 1
        name = args.target[1]
        usernames = args.target[2:]
        return cmd.cmd_new_group(api, name, usernames)

    # ----- open chat -----
    # everything else is interpreted as username (or group name with -g)
    if not _require_auth(config):
        return 1

    target = " ".join(args.target)

    try:
        if args.group:
            chat = api.find_group(target)
        else:
            chat = api.open_personal(target)
    except ApiError as e:
        print(f"\033[91merror: {e}\033[0m", file=sys.stderr)
        return 1

    if args.last is not None:
        return cmd.cmd_last(api, chat, args.last, config.user_id)

    # interactive TUI
    return launch_chat_tui(api, chat)


def launch_chat_tui(api, chat):
    try:
        from .tui import ChatTUI
    except ImportError as e:
        print(f"\033[91merror: prompt_toolkit not installed — {e}\033[0m", file=sys.stderr)
        print("install with: pip install prompt_toolkit", file=sys.stderr)
        return 1
    tui = ChatTUI(api, chat)
    tui.run()
    return 0


def launch_chat_list(api, config):
    """Plain `mskit` — show chat list as a simple selector, then open TUI for chosen one."""
    try:
        chats = api.list_chats()
    except ApiError as e:
        print(f"\033[91merror: {e}\033[0m", file=sys.stderr)
        return 1
    if not chats:
        print("\033[2mno chats yet — try `tg <username>` to start one\033[0m")
        return 0

    print("\033[1myour chats:\033[0m")
    for i, c in enumerate(chats, 1):
        if c["is_group"]:
            title = f"#{c['name']} ({len(c['members'])} members)"
        else:
            other = next((m for m in c["members"] if m["id"] != config.user_id), None)
            dot = "●" if other and other["is_online"] else "○"
            title = f"{dot} {other['display_name']} @{other['username']}" if other else "(empty)"
        lm = c.get("last_message")
        preview = ""
        if lm:
            txt = lm.get("content") or ("📎 " + (lm.get("file_name") or "file"))
            if len(txt) > 40:
                txt = txt[:37] + "..."
            preview = f"  \033[90m— {txt}\033[0m"
        print(f"  [{i}] {title}{preview}")
    print()
    try:
        pick = input("open chat # (empty to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if not pick:
        return 0
    try:
        idx = int(pick) - 1
        chat = chats[idx]
    except (ValueError, IndexError):
        print("\033[91minvalid choice\033[0m", file=sys.stderr)
        return 1
    return launch_chat_tui(api, chat)


if __name__ == "__main__":
    sys.exit(main())
