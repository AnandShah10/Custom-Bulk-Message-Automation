from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import pandas as pd
import io
import json
from app.database import get_db
from app.models import User, Lead
from app.auth import get_current_active_user_or_401

router = APIRouter(prefix="/leads", tags=["leads"])

@router.get("/")
async def get_leads(
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_active_user_or_401)
):
    query = db.query(Lead).filter(Lead.user_id == user.id)
    total = query.count()
    items = query.order_by(Lead.created_at.desc()).offset((page - 1) * size).limit(size).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size
    }

@router.post("/add")
async def add_lead(
    phone: str = Form(...),
    name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    category: str = Form("General"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user_or_401)
):
    # Basic check
    existing = db.query(Lead).filter(Lead.user_id == user.id, Lead.phone == phone).first()
    if existing:
        return {"status": "error", "message": "Lead with this phone already exists"}
    
    lead = Lead(user_id=user.id, phone=phone, name=name, email=email, category=category)
    db.add(lead)
    db.commit()
    return {"status": "success", "message": "Lead added successfully"}

@router.post("/import")
async def import_leads(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user_or_401)
):
    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content)) if file.filename.endswith('.xlsx') else pd.read_csv(io.BytesIO(content))
        
        if 'Phone' not in df.columns:
            raise HTTPException(status_code=400, detail="File must have a 'Phone' column")
        
        count = 0
        duplicate_count = 0
        for _, row in df.iterrows():
            phone = str(row['Phone']).split('.')[0].strip()
            if not phone or phone.lower() == 'nan': continue
            
            # Check for duplicate within user's leads
            existing = db.query(Lead).filter(Lead.user_id == user.id, Lead.phone == phone).first()
            if existing:
                duplicate_count += 1
                continue
            
            name = str(row.get('Name', '')) if 'Name' in row else None
            email = str(row.get('Email', '')) if 'Email' in row else None
            
            # Additional metadata
            meta = {k: str(v) for k, v in row.to_dict().items() if k not in ['Phone', 'Name', 'Email']}
            
            lead = Lead(
                user_id=user.id,
                phone=phone,
                name=name,
                email=email,
                metadata_json=json.dumps(meta) if meta else None
            )
            db.add(lead)
            count += 1
        
        db.commit()
        return {"status": "success", "imported": count, "duplicates_skipped": duplicate_count}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@router.delete("/{lead_id}")
async def delete_lead(lead_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user_or_401)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(lead)
    db.commit()
    return {"status": "success"}
@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: int, 
    status: str = Form(...),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_active_user_or_401)
):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    lead.status = status
    db.commit()
    return {"status": "success", "new_status": lead.status}
