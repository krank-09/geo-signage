from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Content, User, utcnow
from ..realtime import announce_changes, notify_devices
from ..schemas import ContentUpdate
from ..scope import Scope, get_scope, get_scoped, resolve_scope, scoped, write_scope
from ..security import current_user_or_query
from ..services.media import save_upload, stream_content
from ..storage import get_storage

router = APIRouter(prefix="/content", tags=["content"])


def _out(c: Content) -> dict:
    return {"id": c.id, "client_id": c.client_id, "name": c.name, "type": c.type, "mime": c.mime, "size": c.size,
            "duration": c.duration, "version": c.version, "sha256": c.sha256, "created_at": c.created_at, "updated_at": c.updated_at}


@router.get("")
def list_content(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    return [_out(c) for c in scoped(db.query(Content), Content, scope).order_by(Content.id.desc())]


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), name: str = Form(""), duration: int = Form(10),
                 db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    saved = await save_upload(file)
    c = Content(client_id=scope.client_id, name=(name or file.filename or "Untitled")[:200], type=saved["type"], storage_key=saved["key"],
                mime=saved["mime"], size=saved["size"], sha256=saved["sha256"], duration=max(1, min(duration, 3600)))
    db.add(c)
    db.commit()
    return _out(c)


@router.put("/{content_id}")
def update_content(content_id: int, body: ContentUpdate, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    c = get_scoped(db, Content, content_id, scope, "Content")
    if body.name is not None:
        c.name = body.name
    if body.duration is not None and body.duration != c.duration:
        c.duration = body.duration
        c.version += 1  # playlist timing changed -> devices must resync
    db.commit()
    notify_devices(None, "content", c.client_id)
    return _out(c)


@router.post("/{content_id}/replace")
async def replace_content(content_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                          scope: Scope = Depends(write_scope)):
    """Swap the underlying file; bumps `version` so every device re-downloads it."""
    c = get_scoped(db, Content, content_id, scope, "Content")
    saved = await save_upload(file)
    old_key = c.storage_key
    c.storage_key, c.type, c.mime, c.size, c.sha256 = saved["key"], saved["type"], saved["mime"], saved["size"], saved["sha256"]
    c.version += 1
    c.updated_at = utcnow()
    db.commit()
    get_storage().delete(old_key)
    notify_devices(None, "content", c.client_id)
    return _out(c)


@router.delete("/{content_id}")
def delete_content(content_id: int, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    c = get_scoped(db, Content, content_id, scope, "Content")
    client_id, key = c.client_id, c.storage_key
    db.query(Assignment).filter(Assignment.content_id == content_id).delete()
    db.delete(c)
    db.commit()
    get_storage().delete(key)
    announce_changes("content", client_id)
    return {"ok": True}


@router.get("/{content_id}/file")
def file(content_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user_or_query)):
    # <img>/<video> tags cannot send headers, so the scope comes from the user alone: client users only ever get their own files
    c = get_scoped(db, Content, content_id, resolve_scope(user, None, db), "Content")
    return stream_content(c, request)
