from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Content, User, utcnow
from ..realtime import announce_changes, notify_devices
from ..schemas import ContentUpdate
from ..security import current_user, current_user_or_query, require_admin
from ..services.media import save_upload, stream_content
from ..storage import get_storage
from .deps import get_or_404

router = APIRouter(prefix="/content", tags=["content"])


def _out(c: Content) -> dict:
    return {"id": c.id, "name": c.name, "type": c.type, "mime": c.mime, "size": c.size,
            "duration": c.duration, "version": c.version, "created_at": c.created_at, "updated_at": c.updated_at}


@router.get("")
def list_content(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_out(c) for c in db.query(Content).order_by(Content.id.desc())]


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), name: str = Form(""), duration: int = Form(10),
                 db: Session = Depends(get_db), _: User = Depends(require_admin)):
    saved = await save_upload(file)
    c = Content(name=(name or file.filename or "Untitled")[:200], type=saved["type"], storage_key=saved["key"],
                mime=saved["mime"], size=saved["size"], duration=max(1, min(duration, 3600)))
    db.add(c)
    db.commit()
    return _out(c)


@router.put("/{content_id}")
def update_content(content_id: int, body: ContentUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = get_or_404(db, Content, content_id, "Content")
    if body.name is not None:
        c.name = body.name
    if body.duration is not None and body.duration != c.duration:
        c.duration = body.duration
        c.version += 1  # playlist timing changed -> devices must resync
    db.commit()
    notify_devices(None, "content")
    return _out(c)


@router.post("/{content_id}/replace")
async def replace_content(content_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                          _: User = Depends(require_admin)):
    """Swap the underlying file; bumps `version` so every device re-downloads it."""
    c = get_or_404(db, Content, content_id, "Content")
    saved = await save_upload(file)
    old_key = c.storage_key
    c.storage_key, c.type, c.mime, c.size = saved["key"], saved["type"], saved["mime"], saved["size"]
    c.version += 1
    c.updated_at = utcnow()
    db.commit()
    get_storage().delete(old_key)
    notify_devices(None, "content")
    return _out(c)


@router.delete("/{content_id}")
def delete_content(content_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = get_or_404(db, Content, content_id, "Content")
    db.query(Assignment).filter(Assignment.content_id == content_id).delete()
    key = c.storage_key
    db.delete(c)
    db.commit()
    get_storage().delete(key)
    announce_changes("content")
    return {"ok": True}


@router.get("/{content_id}/file")
def file(content_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(current_user_or_query)):
    c = get_or_404(db, Content, content_id, "Content")
    return stream_content(c, request)
