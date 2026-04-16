import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from auth import get_current_user
from models import User

router = APIRouter(prefix="/api", tags=["files"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_SIZE = 50 * 1024 * 1024
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...),
                      current: User = Depends(get_current_user)):
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(413, "File too large (max 50 MB)")

    ext = Path(file.filename or "").suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / safe_name
    path.write_bytes(contents)

    file_type = "image" if ext in IMAGE_EXTS else "file"
    return {
        "file_url": f"/uploads/{safe_name}",
        "file_name": file.filename,
        "file_type": file_type,
        "size": len(contents),
    }
