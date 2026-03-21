from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db
from app.models import User, Campaign, CampaignLog, CreditTransaction
from app.auth import get_current_active_user_or_401
from datetime import datetime, timedelta

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

@router.get("/")
async def get_campaigns(db: Session = Depends(get_db), user: User = Depends(get_current_active_user_or_401)):
    return db.query(Campaign).filter(Campaign.user_id == user.id).order_by(Campaign.created_at.desc()).all()

@router.get("/stats")
async def get_stats(db: Session = Depends(get_db), user: User = Depends(get_current_active_user_or_401)):
    # Total sent, Success Rate, Credits
    total_sent = db.query(func.sum(Campaign.processed_count)).filter(Campaign.user_id == user.id).scalar() or 0
    total_success = db.query(func.sum(Campaign.success_count)).filter(Campaign.user_id == user.id).scalar() or 0
    
    # Recent trend (last 7 days)
    seven_days_ago = datetime.now() - timedelta(days=7)
    daily_stats = db.query(
        func.date(Campaign.created_at).label("date"),
        func.sum(Campaign.success_count).label("successes")
    ).filter(
        Campaign.user_id == user.id,
        Campaign.created_at >= seven_days_ago
    ).group_by(func.date(Campaign.created_at)).all()

    return {
        "total_sent": total_sent,
        "success_rate": round((total_success / total_sent * 100), 2) if total_sent > 0 else 0,
        "credits_remaining": user.credits,
        "recent_trend": [{"date": str(d.date), "count": d.successes} for d in daily_stats]
    }

@router.get("/{campaign_id}")
async def get_campaign_detail(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user_or_401)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    logs = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign.id).all()
    return {
        "campaign": campaign,
        "logs": logs
    }

@router.get("/credits/history")
async def get_credit_history(db: Session = Depends(get_db), user: User = Depends(get_current_active_user_or_401)):
    return db.query(CreditTransaction).filter(CreditTransaction.user_id == user.id).order_by(CreditTransaction.created_at.desc()).limit(50).all()
