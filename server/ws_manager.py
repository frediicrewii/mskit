from typing import Dict, Set
from fastapi import WebSocket
import json
import asyncio


class ConnectionManager:
    def __init__(self):
        self.active: Dict[int, Set[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, user_id: int, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            if user_id not in self.active:
                self.active[user_id] = set()
            self.active[user_id].add(ws)

    async def disconnect(self, user_id: int, ws: WebSocket):
        async with self.lock:
            if user_id in self.active:
                self.active[user_id].discard(ws)
                if not self.active[user_id]:
                    del self.active[user_id]

    def is_online(self, user_id: int) -> bool:
        return user_id in self.active

    def online_user_ids(self) -> Set[int]:
        return set(self.active.keys())

    async def send_to_user(self, user_id: int, data: dict):
        if user_id not in self.active:
            return
        payload = json.dumps(data, default=str)
        dead = []
        for ws in list(self.active[user_id]):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active[user_id].discard(ws)

    async def broadcast_to_users(self, user_ids, data: dict):
        for uid in user_ids:
            await self.send_to_user(uid, data)


manager = ConnectionManager()
