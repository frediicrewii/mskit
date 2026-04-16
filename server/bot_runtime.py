"""Runtime glue between weather_bot logic and messaging layer.

Responsibilities:
  - ensure the @weather_bot user exists at startup
  - intercept user messages to the bot and generate replies
  - periodically send weather updates to subscribed users
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from models import SessionLocal, User, Chat, ChatMember, Message, WeatherSubscription
from auth import hash_password
from ws_manager import manager
from weather_bot import (
    BOT_USERNAME, BOT_DISPLAY_NAME,
    handle_user_message, fetch_weather, format_weather_message,
)

# ---------- startup ----------
def ensure_bot_user(db: Session) -> User:
    bot = db.query(User).filter(User.username == BOT_USERNAME).first()
    if bot:
        if not bot.is_bot:
            bot.is_bot = True
            db.commit()
        return bot
    bot = User(
        username=BOT_USERNAME,
        display_name=BOT_DISPLAY_NAME,
        password_hash=hash_password("DISABLED_" + "x" * 16),  # unusable
        is_bot=True,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


# ---------- helpers ----------
async def _send_bot_message(db: Session, chat_id: int, bot: User, text: str):
    """Write a message from the bot and broadcast it to members via WS."""
    msg = Message(
        chat_id=chat_id,
        sender_id=bot.id,
        content=text,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    # build the same payload shape as routers/messages.serialize_message
    payload = {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "sender_id": msg.sender_id,
        "sender_username": bot.username,
        "sender_name": bot.display_name,
        "content": msg.content,
        "file_url": None,
        "file_name": None,
        "file_type": None,
        "created_at": msg.created_at.isoformat() + "Z",
    }
    member_ids = [m.user_id for m in db.query(ChatMember).filter(ChatMember.chat_id == chat_id).all()]
    await manager.broadcast_to_users(
        member_ids, {"type": "new_message", "message": payload})


def _get_bot_chat_for_user(db: Session, user_id: int, bot_id: int) -> Chat | None:
    """Find the 1-on-1 chat between user and bot, if any."""
    my_chats = {m.chat_id for m in db.query(ChatMember).filter(ChatMember.user_id == user_id).all()}
    bot_chats = {m.chat_id for m in db.query(ChatMember).filter(ChatMember.user_id == bot_id).all()}
    common = my_chats & bot_chats
    for cid in common:
        chat = db.query(Chat).filter(Chat.id == cid, Chat.is_group == False).first()
        if chat and len(chat.members) == 2:
            return chat
    return None


# ---------- inbound: user -> bot ----------
async def maybe_bot_reply(db: Session, chat_id: int, sender: User, text: str):
    """If the target chat is a 1-on-1 between sender and the bot, have the bot reply."""
    if sender.is_bot:
        return  # avoid loops
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat or chat.is_group:
        return

    bot = db.query(User).filter(User.username == BOT_USERNAME).first()
    if not bot:
        return
    members = [m.user for m in chat.members]
    member_ids = {u.id for u in members}
    if bot.id not in member_ids:
        return
    if sender.id == bot.id:
        return

    # Load current subscription (if any)
    sub = db.query(WeatherSubscription).filter(WeatherSubscription.user_id == sender.id).first()

    reply, action = await handle_user_message(text, sub)

    at = action.get("type") if action else "nothing"

    if at == "show_regions":
        # Set state to await_region if no active sub
        if sub:
            sub.state = "await_region"
            sub.chat_id = chat_id
        else:
            sub = WeatherSubscription(
                user_id=sender.id,
                chat_id=chat_id,
                location_name="",
                location_query="",
                state="await_region",
            )
            db.add(sub)
        db.commit()

    elif at == "subscribe":
        name = action["location_name"]
        query = action["location_query"]
        if sub:
            sub.location_name = name
            sub.location_query = query
            sub.state = "active"
            sub.chat_id = chat_id
            sub.last_sent_at = None
        else:
            sub = WeatherSubscription(
                user_id=sender.id,
                chat_id=chat_id,
                location_name=name,
                location_query=query,
                state="active",
                last_sent_at=None,
            )
            db.add(sub)
        db.commit()

    elif at == "unsubscribe":
        if sub:
            db.delete(sub)
            db.commit()

    elif at == "send_now":
        # Send the reply (if any) first, then weather immediately.
        if reply:
            await _send_bot_message(db, chat_id, bot, reply)
        await _deliver_forecast(db, bot, sub, chat_id)
        return

    # Send the text reply
    if reply:
        await _send_bot_message(db, chat_id, bot, reply)

    # If we just subscribed, send first forecast immediately
    if at == "subscribe":
        sub = db.query(WeatherSubscription).filter(WeatherSubscription.user_id == sender.id).first()
        await _deliver_forecast(db, bot, sub, chat_id)


# ---------- outbound: scheduled weather broadcast ----------
async def _deliver_forecast(db: Session, bot: User, sub: WeatherSubscription | None, chat_id: int):
    if not sub or sub.state != "active" or not sub.location_query:
        return
    data = await fetch_weather(sub.location_query)
    if not data:
        await _send_bot_message(db, chat_id, bot,
            "Не удалось получить данные о погоде. Попробую через 10 минут.")
        return
    text = format_weather_message(data, sub.location_name)
    await _send_bot_message(db, chat_id, bot, text)
    sub.last_sent_at = datetime.utcnow()
    db.commit()


async def scheduler_loop():
    """Forever: every minute, check subscriptions and send forecast if >=10 minutes passed."""
    from models import SessionLocal as _SL
    while True:
        try:
            await asyncio.sleep(60)
            db = _SL()
            try:
                bot = db.query(User).filter(User.username == BOT_USERNAME).first()
                if not bot:
                    continue
                now = datetime.utcnow()
                cutoff = now - timedelta(minutes=10)
                subs = db.query(WeatherSubscription).filter(
                    WeatherSubscription.state == "active"
                ).all()
                for sub in subs:
                    if sub.last_sent_at is None or sub.last_sent_at <= cutoff:
                        try:
                            await _deliver_forecast(db, bot, sub, sub.chat_id)
                        except Exception as e:
                            print(f"[scheduler] forecast delivery failed for user={sub.user_id}: {e}")
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler] loop error: {e}")
