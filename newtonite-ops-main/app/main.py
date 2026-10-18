import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import jwt

from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import update, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, SessionLocal
from .models import User, Team, Membership, WorkItem, ActivityEvent, Comment, IdempotencyRecord
from .schemas import LoginInput, ItemCreate, ItemUpdate, TransitionInput, CommentInput
from .security import hash_password, verify_password, create_access_token, decode_access_token
from .permissions import membership_for, require_team_role, get_visible_item

BASE_DIR = Path(__file__).resolve().parent
bearer = HTTPBearer(auto_error=False)
TRANSITIONS = {
    "Open": {"In Progress"},
    "In Progress": {"Open", "Awaiting Approval"},
    "Awaiting Approval": {"In Progress", "Resolved"},
    "Resolved": {"Closed", "In Progress"},
    "Closed": set(),
}


def seed_data(db: Session) -> None:
    if db.query(User).count():
        return
    teams = [Team(name="Operations"), Team(name="Engineering"), Team(name="Finance")]
    db.add_all(teams)
    db.flush()
    users = [
        User(email="admin@newtonite.local", name="Avery Admin", password_hash=hash_password("AdminDemo!2026")),
        User(email="lead@newtonite.local", name="Lee Lead", password_hash=hash_password("LeadDemo!2026")),
        User(email="member@newtonite.local", name="Morgan Member", password_hash=hash_password("MemberDemo!2026")),
        User(email="viewer@newtonite.local", name="Val Viewer", password_hash=hash_password("ViewerDemo!2026")),
        User(email="finance@newtonite.local", name="Finley Finance", password_hash=hash_password("FinanceDemo!2026")),
    ]
    db.add_all(users)
    db.flush()
    memberships = [
        Membership(user_id=users[0].id, team_id=t.id, role="Admin") for t in teams
    ] + [
        Membership(user_id=users[1].id, team_id=teams[0].id, role="Lead"),
        Membership(user_id=users[2].id, team_id=teams[0].id, role="Member"),
        Membership(user_id=users[3].id, team_id=teams[0].id, role="Viewer"),
        Membership(user_id=users[4].id, team_id=teams[2].id, role="Member"),
    ]
    db.add_all(memberships)
    db.flush()
    examples = [
        WorkItem(title="Investigate delayed customer refund", description="Review the payment timeline and determine why the refund is delayed.", item_type="payment", priority="Urgent", status="Open", team_id=teams[0].id, assignee_id=None, creator_id=users[1].id),
        WorkItem(title="Review production error spike", description="Check logs and identify the root cause of the recent error increase.", item_type="incident", priority="High", status="In Progress", team_id=teams[1].id, assignee_id=None, creator_id=users[0].id),
        WorkItem(title="Update vendor compliance record", description="Confirm the required documents and update the record.", item_type="compliance", priority="Medium", status="Awaiting Approval", team_id=teams[2].id, assignee_id=users[4].id, creator_id=users[0].id),
    ]
    db.add_all(examples)
    db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
    yield

app = FastAPI(title="Newtonite Operations", version="1.0.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Please log in")
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter_by(id=user_id, active=True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User account is unavailable")
    return user

CurrentUser = Annotated[User, Depends(current_user)]
DB = Annotated[Session, Depends(get_db)]

def event(db: Session, item_id: int, actor_id: int, action: str, detail: str = "") -> None:
    db.add(ActivityEvent(item_id=item_id, actor_id=actor_id, action=action, detail=detail))

def item_dict(item: WorkItem) -> dict:
    return {"id": item.id, "title": item.title, "description": item.description, "item_type": item.item_type,
            "priority": item.priority, "status": item.status, "team_id": item.team_id, "assignee_id": item.assignee_id,
            "creator_id": item.creator_id, "due_date": item.due_date, "version": item.version,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None}

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/auth/login")
def login(payload: LoginInput, db: DB):
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    memberships = [{"team_id": m.team_id, "team": m.team.name, "role": m.role} for m in user.memberships]
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email, "memberships": memberships}}

@app.get("/api/me")
def me(user: CurrentUser, db: DB):
    return {"id": user.id, "name": user.name, "email": user.email,
            "memberships": [{"team_id": m.team_id, "team": m.team.name, "role": m.role} for m in user.memberships]}

@app.get("/api/teams")
def list_teams(user: CurrentUser, db: DB):
    return [{"id": m.team_id, "name": m.team.name, "role": m.role} for m in user.memberships]

@app.get("/api/dashboard")
def dashboard(user: CurrentUser, db: DB):
    team_ids = [m.team_id for m in user.memberships]
    base = db.query(WorkItem).filter(WorkItem.team_id.in_(team_ids))
    return {"total": base.count(), "open": base.filter(WorkItem.status == "Open").count(),
            "in_progress": base.filter(WorkItem.status == "In Progress").count(),
            "urgent": base.filter(WorkItem.priority == "Urgent").filter(WorkItem.status != "Closed").count(),
            "assigned_to_me": base.filter(WorkItem.assignee_id == user.id).count(),
            "unassigned_urgent": base.filter(WorkItem.assignee_id.is_(None), WorkItem.priority == "Urgent", WorkItem.status != "Closed").count(),
            "awaiting_approval": base.filter(WorkItem.status == "Awaiting Approval").count()}

@app.get("/api/items")
def list_items(user: CurrentUser, db: DB, q: str | None = None, status: str | None = None,
               priority: str | None = None, team_id: int | None = None, assigned_to_me: bool = False,
               unassigned_urgent: bool = False, awaiting_approval: bool = False,
               page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    team_ids = [m.team_id for m in user.memberships]
    query = db.query(WorkItem).filter(WorkItem.team_id.in_(team_ids))
    if team_id is not None:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="You are not a member of this team")
        query = query.filter(WorkItem.team_id == team_id)
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(or_(WorkItem.title.ilike(needle), WorkItem.description.ilike(needle)))
    if status: query = query.filter(WorkItem.status == status)
    if priority: query = query.filter(WorkItem.priority == priority)
    if assigned_to_me: query = query.filter(WorkItem.assignee_id == user.id)
    if unassigned_urgent: query = query.filter(WorkItem.assignee_id.is_(None), WorkItem.priority == "Urgent", WorkItem.status != "Closed")
    if awaiting_approval: query = query.filter(WorkItem.status == "Awaiting Approval")
    total = query.count()
    items = query.order_by(WorkItem.updated_at.desc(), WorkItem.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [item_dict(i) for i in items], "total": total, "page": page, "page_size": page_size, "pages": (total + page_size - 1) // page_size}

@app.post("/api/items", status_code=201)
def create_item(payload: ItemCreate, user: CurrentUser, db: DB, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_team_role(db, user, payload.team_id, {"Member", "Lead", "Admin"})
    if payload.assignee_id is not None:
        assignee_membership = membership_for(db, db.query(User).filter_by(id=payload.assignee_id).first(), payload.team_id) if db.query(User).filter_by(id=payload.assignee_id).first() else None
        if not assignee_membership:
            raise HTTPException(status_code=422, detail="Assignee must belong to the selected team")
    if idempotency_key:
        if len(idempotency_key) > 200:
            raise HTTPException(status_code=400, detail="Idempotency-Key must be 200 characters or fewer")
        previous = db.query(IdempotencyRecord).filter_by(key=idempotency_key).first()
        if previous:
            if previous.user_id != user.id:
                raise HTTPException(status_code=409, detail="Idempotency key already used")
            existing = db.query(WorkItem).filter_by(id=previous.item_id).first()
            if existing:
                return JSONResponse(status_code=200, content=item_dict(existing))
    item = WorkItem(**payload.model_dump(), creator_id=user.id)
    db.add(item)
    try:
        db.flush()
        event(db, item.id, user.id, "created", f"Created work item '{item.title}'")
        if payload.assignee_id is not None:
            event(db, item.id, user.id, "assignee_changed", f"Assigned to user #{payload.assignee_id}")
        if idempotency_key:
            db.add(IdempotencyRecord(key=idempotency_key, user_id=user.id, item_id=item.id))
        db.commit()
        db.refresh(item)
        return item_dict(item)
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            previous = db.query(IdempotencyRecord).filter_by(key=idempotency_key).first()
            if previous and previous.user_id == user.id:
                existing = db.query(WorkItem).filter_by(id=previous.item_id).first()
                if existing: return JSONResponse(status_code=200, content=item_dict(existing))
        raise HTTPException(status_code=409, detail="Conflicting request; retry with a new idempotency key")

@app.get("/api/items/{item_id}")
def get_item(item_id: int, user: CurrentUser, db: DB):
    return item_dict(get_visible_item(db, user, item_id))

@app.patch("/api/items/{item_id}")
def update_item(item_id: int, payload: ItemUpdate, user: CurrentUser, db: DB):
    item = get_visible_item(db, user, item_id)
    membership = require_team_role(db, user, item.team_id, {"Member", "Lead", "Admin"})
    if payload.version != item.version:
        raise HTTPException(status_code=409, detail={"message": "This item changed. Reload and try again.", "current": item_dict(item)})
    updates = payload.model_dump(exclude={"version"}, exclude_unset=True)
    if "assignee_id" in updates and updates["assignee_id"] is not None:
        assignee = db.query(User).filter_by(id=updates["assignee_id"]).first()
        if not assignee or not membership_for(db, assignee, item.team_id):
            raise HTTPException(status_code=422, detail="Assignee must belong to this team")
        if membership.role == "Member" and updates["assignee_id"] != user.id:
            raise HTTPException(status_code=403, detail="Only Leads or Admins can assign work to other users")
    old_values = {key: getattr(item, key) for key in updates}
    result = db.execute(update(WorkItem).where(WorkItem.id == item_id, WorkItem.version == payload.version).values(**updates, version=WorkItem.version + 1, updated_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        db.rollback()
        db.refresh(item)
        raise HTTPException(status_code=409, detail={"message": "This item changed. Reload and try again.", "current": item_dict(item)})
    for key, value in updates.items():
        old_value = old_values[key]
        if old_value != value:
            event(db, item.id, user.id, f"{key}_changed", f"{old_value!s} → {value!s}")
    db.commit()
    db.expire_all()
    return item_dict(db.query(WorkItem).filter_by(id=item_id).one())

@app.post("/api/items/{item_id}/claim")
def claim_item(item_id: int, user: CurrentUser, db: DB):
    item = get_visible_item(db, user, item_id)
    require_team_role(db, user, item.team_id, {"Member", "Lead", "Admin"})
    # Atomic conditional update: only one concurrent caller can change NULL assignee to this user.
    result = db.execute(update(WorkItem).where(WorkItem.id == item_id, WorkItem.assignee_id.is_(None), WorkItem.status != "Closed").values(assignee_id=user.id, version=WorkItem.version + 1, updated_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This item is already assigned or closed")
    event(db, item.id, user.id, "claimed", f"Claimed by {user.name}")
    db.commit()
    db.expire_all()
    return item_dict(db.query(WorkItem).filter_by(id=item_id).one())

@app.post("/api/items/{item_id}/transition")
def transition_item(item_id: int, payload: TransitionInput, user: CurrentUser, db: DB):
    item = get_visible_item(db, user, item_id)
    membership = require_team_role(db, user, item.team_id, {"Member", "Lead", "Admin"})
    if payload.version != item.version:
        raise HTTPException(status_code=409, detail={"message": "This item changed. Reload and try again.", "current": item_dict(item)})
    if payload.status not in TRANSITIONS[item.status]:
        raise HTTPException(status_code=422, detail=f"Transition from {item.status} to {payload.status} is not allowed")
    if item.status == "Awaiting Approval" and payload.status == "Resolved" and membership.role not in {"Lead", "Admin"}:
        raise HTTPException(status_code=403, detail="Only a Lead or Admin can approve this item")
    old_status = item.status
    result = db.execute(update(WorkItem).where(WorkItem.id == item_id, WorkItem.version == payload.version).values(status=payload.status, version=WorkItem.version + 1, updated_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This item changed. Reload and try again.")
    event(db, item.id, user.id, "status_changed", f"{old_status} → {payload.status}")
    db.commit()
    db.expire_all()
    return item_dict(db.query(WorkItem).filter_by(id=item_id).one())

@app.get("/api/items/{item_id}/activity")
def item_activity(item_id: int, user: CurrentUser, db: DB):
    get_visible_item(db, user, item_id)
    rows = db.query(ActivityEvent, User.name).join(User, User.id == ActivityEvent.actor_id).filter(ActivityEvent.item_id == item_id).order_by(ActivityEvent.created_at.asc(), ActivityEvent.id.asc()).all()
    return [{"id": e.id, "actor": name, "action": e.action, "detail": e.detail, "created_at": e.created_at.isoformat()} for e, name in rows]

@app.get("/api/items/{item_id}/comments")
def item_comments(item_id: int, user: CurrentUser, db: DB):
    get_visible_item(db, user, item_id)
    rows = db.query(Comment, User.name).join(User, User.id == Comment.author_id).filter(Comment.item_id == item_id).order_by(Comment.created_at.asc()).all()
    return [{"id": c.id, "author": name, "body": c.body, "created_at": c.created_at.isoformat()} for c, name in rows]

@app.post("/api/items/{item_id}/comments", status_code=201)
def add_comment(item_id: int, payload: CommentInput, user: CurrentUser, db: DB):
    get_visible_item(db, user, item_id)
    comment = Comment(item_id=item_id, author_id=user.id, body=payload.body.strip())
    db.add(comment)
    event(db, item_id, user.id, "comment_added", payload.body.strip()[:160])
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "author": user.name, "body": comment.body, "created_at": comment.created_at.isoformat()}
