from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timedelta
from app.database import get_db
from app.models import User, Campaign, Lead, CampaignLog
from app.auth import get_current_active_user_or_401

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/advanced-stats")
async def get_advanced_stats(
    range: str = Query("weekly", enum=["daily", "weekly", "monthly", "yearly", "custom"]),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    campaign_category: Optional[str] = None,
    lead_category: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user_or_401)
):
    # Determine date range
    now = datetime.now()
    if range == "daily":
        since = now - timedelta(days=1)
    elif range == "weekly":
        since = now - timedelta(weeks=1)
    elif range == "monthly":
        since = now - timedelta(days=30)
    elif range == "yearly":
        since = now - timedelta(days=365)
    elif range == "custom" and start_date:
        since = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            now = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        since = now - timedelta(weeks=1)

    # Base Campaign Query
    camp_query = db.query(Campaign).filter(Campaign.user_id == user.id, Campaign.created_at >= since, Campaign.created_at <= now)
    if campaign_category and campaign_category != "All":
        camp_query = camp_query.filter(Campaign.category == campaign_category)
    
    campaigns = camp_query.all()
    
    # 1. Category Success Rate (Success count per category)
    category_stats = db.query(
        Campaign.category,
        func.sum(Campaign.success_count).label("success"),
        func.sum(Campaign.failure_count).label("failure")
    ).filter(Campaign.user_id == user.id, Campaign.created_at >= since).group_by(Campaign.category).all()
    
    # 2. Lead Distribution by Category
    lead_dist = db.query(
        Lead.category,
        func.count(Lead.id).label("count")
    ).filter(Lead.user_id == user.id).group_by(Lead.category).all()
    
    # 3. Conversion Stats (Leads by status)
    lead_status = db.query(
        Lead.status,
        func.count(Lead.id).label("count")
    ).filter(Lead.user_id == user.id).group_by(Lead.status).all()

    # 4. Time-based trend (Campaign success over time)
    # Grouping depends on range
    if range in ["daily", "weekly"]:
        group_by = func.date(Campaign.created_at)
    else:
        group_by = func.strftime("%Y-%m", Campaign.created_at)
        
    trend = db.query(
        group_by.label("label"),
        func.sum(Campaign.success_count).label("success")
    ).filter(Campaign.user_id == user.id, Campaign.created_at >= since).group_by("label").order_by("label").all()

    return {
        "category_performance": [{"category": s.category, "success": s.success, "failure": s.failure} for s in category_stats],
        "lead_distribution": [{"category": l.category, "count": l.count} for l in lead_dist],
        "lead_conversion": [{"status": s.status, "count": s.count} for s in lead_status],
        "trend": [{"label": str(t.label), "count": t.success} for t in trend],
        "available_campaign_categories": [c[0] for c in db.query(Campaign.category).filter(Campaign.user_id == user.id).distinct().all()]
    }
