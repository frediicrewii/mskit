from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import User, Chat, ChatMember, Message, get_db
from auth import get_current_user
from routers.auth import UserOut
from ws_manager import manager

router = APIRouter(prefix="/api/chats", tags=["chats"])


class CreatePersonalIn(BaseModel):
    username: str


class CreateGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    usernames: list[str]


def serialize_chat(chat: Chat, db: Session) -> dict:
    online_ids = manager.online_user_ids()
    members = [
        {
            "id": m.user.id,
            "username": m.user.username,
            "display_name": m.user.display_name,
            "is_online": m.user.id in online_ids,
        }
        for m in chat.members
    ]
    last_msg = db.query(Message).filter(Message.chat_id == chat.id)\
        .order_by(Message.created_at.desc()).first()
    last_message = None
    if last_msg:
        last_message = {
            "id": last_msg.id,
            "content": last_msg.content,
            "file_type": last_msg.file_type,
            "file_name": last_msg.file_name,
            "sender_id": last_msg.sender_id,
            "sender_username": last_msg.sender.username,
            "created_at": last_msg.created_at.isoformat(),
        }
    return {
        "id": chat.id,
        "is_group": chat.is_group,
        "name": chat.name,
        "members": members,
        "last_message": last_message,
    }


@router.get("/")
def list_chats(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    chat_ids = [m.chat_id for m in db.query(ChatMember).filter(ChatMember.user_id == current.id).all()]
    chats = db.query(Chat).filter(Chat.id.in_(chat_ids)).all()
    result = [serialize_chat(c, db) for c in chats]
    result.sort(key=lambda c: (c["last_message"]["created_at"] if c["last_message"] else "", c["id"]),
                reverse=True)
    return result


@router.post("/personal")
async def create_or_get_personal(data: CreatePersonalIn, db: Session = Depends(get_db),
                                  current: User = Depends(get_current_user)):
    uname = data.username.strip().lower()
    other = db.query(User).filter(User.username == uname).first()
    if not other:
        raise HTTPException(404, f"User '{uname}' not found")
    if other.id == current.id:
        raise HTTPException(400, "Cannot chat with yourself")

    my_chat_ids = {m.chat_id for m in db.query(ChatMember).filter(ChatMember.user_id == current.id).all()}
    their_chat_ids = {m.chat_id for m in db.query(ChatMember).filter(ChatMember.user_id == other.id).all()}
    for cid in my_chat_ids & their_chat_ids:
        chat = db.query(Chat).filter(Chat.id == cid, Chat.is_group == False).first()
        if chat and len(chat.members) == 2:
            return serialize_chat(chat, db)

    chat = Chat(is_group=False, created_by=current.id)
    db.add(chat)
    db.flush()
    db.add(ChatMember(chat_id=chat.id, user_id=current.id))
    db.add(ChatMember(chat_id=chat.id, user_id=other.id))
    db.commit()
    db.refresh(chat)
    payload = serialize_chat(chat, db)
    await manager.send_to_user(other.id, {"type": "chat_created", "chat": payload})
    return payload


@router.post("/group")
async def create_group(data: CreateGroupIn, db: Session = Depends(get_db),
                        current: User = Depends(get_current_user)):
    usernames = [u.strip().lower() for u in data.usernames if u.strip()]
    users = db.query(User).filter(User.username.in_(usernames)).all()
    found = {u.username for u in users}
    missing = set(usernames) - found
    if missing:
        raise HTTPException(404, f"Users not found: {', '.join(sorted(missing))}")

    member_ids = {u.id for u in users} | {current.id}
    if len(member_ids) < 2:
        raise HTTPException(400, "Group needs at least one other member")

    chat = Chat(is_group=True, name=data.name.strip(), created_by=current.id)
    db.add(chat)
    db.flush()
    for uid in member_ids:
        db.add(ChatMember(chat_id=chat.id, user_id=uid))
    db.commit()
    db.refresh(chat)

    payload = serialize_chat(chat, db)
    for uid in member_ids:
        if uid != current.id:
            await manager.send_to_user(uid, {"type": "chat_created", "chat": payload})
    return payload


@router.get("/find-group")
def find_group_by_name(name: str, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    """Find a group chat by name that current user is a member of."""
    target = name.strip()
    my_chat_ids = [m.chat_id for m in db.query(ChatMember).filter(ChatMember.user_id == current.id).all()]
    groups = db.query(Chat).filter(Chat.id.in_(my_chat_ids), Chat.is_group == True).all()
    # case-insensitive exact match first
    for g in groups:
        if (g.name or "").lower() == target.lower():
            return serialize_chat(g, db)
    # fallback: substring
    for g in groups:
        if target.lower() in (g.name or "").lower():
            return serialize_chat(g, db)
    raise HTTPException(404, f"Group '{target}' not found in your chats")
