from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String)
    role = Column(String, default="user") # 'admin' or 'user'
    is_active = Column(Boolean, default=True)
    custom_api_key = Column(String, nullable=True) # Optional per-user API key
    credits = Column(Integer, default=0) # Credit system balance
    
    # WhatsApp Dynamic Sessions
    whatsapp_session_id = Column(String, unique=True, index=True, nullable=True)
    whatsapp_session_status = Column(String, default="disconnected") # disconnected, connecting, connected
    
    # MFA & OAuth Integrations
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    mfa_type = Column(String, default="app") # 'app', 'email', 'passkey'
    google_id = Column(String, unique=True, index=True, nullable=True)
    microsoft_id = Column(String, unique=True, index=True, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Password Reset
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expiry = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    leads = relationship("Lead", back_populates="owner")
    campaigns = relationship("Campaign", back_populates="owner")
    credit_transactions = relationship("CreditTransaction", back_populates="owner")

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, index=True)
    details = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserPasskey(Base):
    __tablename__ = "user_passkeys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    credential_id = Column(String, unique=True, index=True)
    public_key = Column(Text) # Store as base64 or hex
    sign_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    phone = Column(String, index=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    category = Column(String, default="General")
    status = Column(String, default="New") # New, Contacted, Converted, Lost
    metadata_json = Column(Text, nullable=True) # JSON strings
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="leads")

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String)
    message_type = Column(String) # text, image, etc.
    status = Column(String, default="queued") # queued, sending, completed, failed
    total_contacts = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="campaigns")
    logs = relationship("CampaignLog", back_populates="campaign")

class CampaignLog(Base):
    __tablename__ = "campaign_logs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), index=True)
    phone = Column(String)
    status = Column(String) # success, failure
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())

    campaign = relationship("Campaign", back_populates="logs")

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    amount = Column(Integer) # + for purchase, - for usage
    type = Column(String) # purchase, usage, refund
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="credit_transactions")
