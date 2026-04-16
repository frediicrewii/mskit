from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from models import User, Chat, ChatMember, Message, get_db
from auth import get_current_user
from ws_manager import manager

router = APIRouter(prefix="/api/messages", tags=["messages"])


class SendMessageIn(BaseModel):
    chat_id: int
    content: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None


def serialize_message(msg: Message) -> dict:
    return {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "sender_id": msg.sender_id,
        "sender_username": msg.sender.username,
        "sender_name": msg.sender.display_name,
        "content": msg.content,
        "file_url": msg.file_url,
        "file_name": msg.file_name,
        "file_type": msg.file_type,
        "created_at": msg.created_at.isoformat(),
    }


@router.get("/{chat_id}")
def get_messages(chat_id: int, limit: int = 50,
                 db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    member = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == current.id).first()
    if not member:
        raise HTTPException(403, "Not a member of this chat")
    limit = min(max(limit, 1), 500)
    # fetch latest N, then reverse to chronological order
    msgs = db.query(Message).filter(Message.chat_id == chat_id)\
        .order_by(Message.created_at.desc()).limit(limit).all()
    msgs.reverse()
    return [serialize_message(m) for m in msgs]


@router.get("/{chat_id}/since/{after_id}")
def get_messages_since(chat_id: int, after_id: int,
                       db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    """Return all messages in chat with id > after_id, chronological order.
    Used by polling clients that can't use WebSocket.
    """
    member = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == current.id).first()
    if not member:
        raise HTTPException(403, "Not a member of this chat")
    msgs = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.id > after_id,
    ).order_by(Message.id.asc()).limit(200).all()
    return [serialize_message(m) for m in msgs]


@router.post("/")
async def send_message(data: SendMessageIn, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    member = db.query(ChatMember).filter(
        ChatMember.chat_id == data.chat_id, ChatMember.user_id == current.id).first()
    if not member:
        raise HTTPException(403, "Not a member of this chat")
    if not data.content and not data.file_url:
        raise HTTPException(400, "Message must have content or file")

    msg = Message(
        chat_id=data.chat_id,
        sender_id=current.id,
        content=data.content,
        file_url=data.file_url,
        file_name=data.file_name,
        file_type=data.file_type,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    payload = serialize_message(msg)

    member_ids = [m.user_id for m in db.query(ChatMember).filter(ChatMember.chat_id == data.chat_id).all()]
    await manager.broadcast_to_users(
        member_ids, {"type": "new_message", "message": payload})

    # If this chat has a bot as the other member and the sender isn't the bot,
    # hand off to the bot to generate a reply.
    from bot_runtime import maybe_bot_reply
    await maybe_bot_reply(db, data.chat_id, sender=current, text=data.content or "")

    return payload
