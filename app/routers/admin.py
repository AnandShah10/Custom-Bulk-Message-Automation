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

@router.post("/admin/users/{user_id}/toggle-status")
async def toggle_user_status(user_id: int, current_admin: User = Depends(check_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")
        
    user.is_active = not user.is_active
    db.commit()
    
    action = "USER_ENABLED" if user.is_active else "USER_DISABLED"
    log = SystemLog(user_id=current_admin.id, action=action, details=f"Admin {current_admin.username} toggled status for {user.username}")
    db.add(log)
    db.commit()
    
    return {"status": "ok", "is_active": user.is_active}

@router.post("/admin/users/{user_id}/toggle-role")
async def toggle_user_role(user_id: int, current_admin: User = Depends(check_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")

    user.role = "admin" if user.role == "user" else "user"
    db.commit()
    
    action = "ROLE_CHANGED"
    log = SystemLog(user_id=current_admin.id, action=action, details=f"Admin {current_admin.username} changed role of {user.username} to {user.role}")
    db.add(log)
    db.commit()
    
    return {"status": "ok", "role": user.role}
