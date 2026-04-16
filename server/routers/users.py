from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import User, get_db
from auth import get_current_user
from routers.auth import UserOut
from ws_manager import manager

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    users = db.query(User).order_by(User.username).all()
    online = manager.online_user_ids()
    for u in users:
        u.is_online = u.id in online
    return users


@router.get("/by-username/{username}", response_model=UserOut)
def get_by_username(username: str, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    if not user:
        raise HTTPException(404, f"User '{username}' not found")
    user.is_online = manager.is_online(user.id)
    return user
