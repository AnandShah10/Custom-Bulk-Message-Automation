from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user") # 'admin' or 'user'
    is_active = Column(Boolean, default=True)
    custom_api_key = Column(String, nullable=True) # Optional per-user API key
    
    # MFA & OAuth Integrations
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    google_id = Column(String, unique=True, index=True, nullable=True)
    microsoft_id = Column(String, unique=True, index=True, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Password Reset
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expiry = Column(DateTime(timezone=True), nullable=True)

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, index=True)
    details = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
