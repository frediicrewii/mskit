import os
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from models import init_db, SessionLocal, User, ChatMember
from auth import decode_token
from ws_manager import manager
from routers import auth as auth_router
from routers import users as users_router
from routers import chats as chats_router
from routers import messages as messages_router
from routers import files as files_router

init_db()

app = FastAPI(title="mskit messenger server", version="1.0")

# ensure bot user exists + start scheduler
import asyncio
from bot_runtime import ensure_bot_user, scheduler_loop
_scheduler_task = None


@app.on_event("startup")
async def _startup():
    global _scheduler_task
    db = SessionLocal()
    try:
        ensure_bot_user(db)
    finally:
        db.close()
    _scheduler_task = asyncio.create_task(scheduler_loop())


@app.on_event("shutdown")
async def _shutdown():
    if _scheduler_task:
        _scheduler_task.cancel()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(chats_router.router)
app.include_router(messages_router.router)
app.include_router(files_router.router)

# serve uploaded files
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
def root():
    return {"name": "mskit messenger server", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


async def broadcast_presence(user_id: int, is_online: bool, db: Session):
    chat_ids = [m.chat_id for m in db.query(ChatMember).filter(ChatMember.user_id == user_id).all()]
    if not chat_ids:
        return
    others = db.query(ChatMember.user_id).filter(
        ChatMember.chat_id.in_(chat_ids),
        ChatMember.user_id != user_id
    ).distinct().all()
    user_ids = {row[0] for row in others}
    await manager.broadcast_to_users(user_ids, {
        "type": "presence", "user_id": user_id, "is_online": is_online
    })


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str = Query(...)):
    user_id = decode_token(token)
    if user_id is None:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        await websocket.close(code=4404)
        return

    was_offline = not manager.is_online(user_id)
    await manager.connect(user_id, websocket)

    if was_offline:
        user.is_online = True
        user.last_seen = datetime.utcnow()
        db.commit()
        await broadcast_presence(user_id, True, db)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(user_id, websocket)
        if not manager.is_online(user_id):
            try:
                user.is_online = False
                user.last_seen = datetime.utcnow()
                db.commit()
                await broadcast_presence(user_id, False, db)
            except Exception:
                pass
        db.close()
