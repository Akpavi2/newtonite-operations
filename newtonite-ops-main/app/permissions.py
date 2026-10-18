from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import User, Membership, WorkItem

ROLES = {"Viewer", "Member", "Lead", "Admin"}

def membership_for(db: Session, user: User, team_id: int) -> Membership | None:
    return db.query(Membership).filter_by(user_id=user.id, team_id=team_id).first()

def require_team_role(db: Session, user: User, team_id: int, allowed: set[str]) -> Membership:
    membership = membership_for(db, user, team_id)
    if not membership or membership.role not in allowed:
        raise HTTPException(status_code=403, detail="You do not have permission for this team action")
    return membership

def get_visible_item(db: Session, user: User, item_id: int) -> WorkItem:
    item = db.query(WorkItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    if not membership_for(db, user, item.team_id):
        # Return 404 rather than disclosing another team's item exists.
        raise HTTPException(status_code=404, detail="Work item not found")
    return item
