from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, SystemLog
from app.auth import get_current_active_user_or_401

router = APIRouter(tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")

def check_admin(user: User = Depends(get_current_active_user_or_401)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized mapping: Admin privileges required")
    return user

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: User = Depends(check_admin), db: Session = Depends(get_db)):
    """Serve the Admin HTML Interface."""
    # Get high-level stats
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    users_with_mfa = db.query(User).filter(User.mfa_enabled == True).count()
    
    # Get users list
    all_users = db.query(User).order_by(User.id.desc()).all()
    
    # Get latest logs
    recent_logs = db.query(SystemLog).order_by(SystemLog.created_at.desc()).limit(50).all()
    
    # Resolve usernames for logs
    user_dict = {u.id: u.username for u in all_users}
    for log in recent_logs:
        log.username = user_dict.get(log.user_id, "Unknown System")

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user,
        "total_users": total_users,
        "active_users": active_users,
        "users_with_mfa": users_with_mfa,
        "all_users": all_users,
        "recent_logs": recent_logs
    })
