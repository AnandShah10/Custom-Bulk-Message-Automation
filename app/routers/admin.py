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

from sqlalchemy import or_

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request, 
    user_page: int = 1, 
    log_page: int = 1, 
    user_query: str = "", 
    log_query: str = "",
    user: User = Depends(check_admin), 
    db: Session = Depends(get_db)
):
    """Serve the Admin HTML Interface with Search & Pagination."""
    USER_LIMIT = 10
    LOG_LIMIT = 20

    # High-level stats (global)
    total_users_count = db.query(User).count()
    active_users_count = db.query(User).filter(User.is_active == True).count()
    users_with_mfa_count = db.query(User).filter(User.mfa_enabled == True).count()
    
    # 1. Users Query with Search & Pagination
    user_base = db.query(User)
    if user_query:
        user_base = user_base.filter(
            or_(
                User.username.ilike(f"%{user_query}%"),
                User.full_name.ilike(f"%{user_query}%"),
                User.public_id.ilike(f"%{user_query}%")
            )
        )
    
    total_filtered_users = user_base.count()
    user_total_pages = (total_filtered_users + USER_LIMIT - 1) // USER_LIMIT
    all_users = user_base.order_by(User.id.desc()).offset((user_page - 1) * USER_LIMIT).limit(USER_LIMIT).all()
    
    # 2. Logs Query with Search & Pagination
    log_base = db.query(SystemLog)
    if log_query:
        log_base = log_base.filter(
            or_(
                SystemLog.action.ilike(f"%{log_query}%"),
                SystemLog.details.ilike(f"%{log_query}%")
            )
        )
    
    total_filtered_logs = log_base.count()
    log_total_pages = (total_filtered_logs + LOG_LIMIT - 1) // LOG_LIMIT
    recent_logs = log_base.order_by(SystemLog.created_at.desc()).offset((log_page - 1) * LOG_LIMIT).limit(LOG_LIMIT).all()
    
    # Resolve usernames for logs
    log_user_ids = {log.user_id for log in recent_logs if log.user_id}
    involved_users = db.query(User.id, User.username).filter(User.id.in_(log_user_ids)).all()
    user_dict = {u.id: u.username for u in involved_users}
    
    for log in recent_logs:
        log.username = user_dict.get(log.user_id, "System")

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user,
        "total_users": total_users_count,
        "active_users": active_users_count,
        "users_with_mfa": users_with_mfa_count,
        "all_users": all_users,
        "recent_logs": recent_logs,
        "user_page": user_page,
        "user_total_pages": user_total_pages,
        "user_query": user_query,
        "log_page": log_page,
        "log_total_pages": log_total_pages,
        "log_query": log_query
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
