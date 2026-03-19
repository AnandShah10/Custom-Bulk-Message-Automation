from app.routers.auth import base_url
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from dotenv import load_dotenv

load_dotenv()

conf = ConnectionConfig(
    MAIL_USERNAME = os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD"),
    MAIL_FROM = os.getenv("MAIL_FROM"),
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER = os.getenv("MAIL_SERVER"),
    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "CBMS Pro"),
    MAIL_STARTTLS = os.getenv("MAIL_STARTTLS", "True").lower() == "true",
    MAIL_SSL_TLS = os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

async def send_password_reset_email(email_to: str, reset_link: str):
    message = MessageSchema(
        subject="Password Reset Request - CBMS Pro",
        recipients=[email_to],
        body=f"""
        <div style="background-color: #0f172a; padding: 40px 20px; font-family: 'Inter', Arial, sans-serif;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; border-radius: 24px; padding: 40px; border: 1px solid rgba(255, 255, 255, 0.1);">
                <div style="text-align: center; margin-bottom: 32px;">
                    <!-- Compatible Icon Container -->
                    <table border="0" cellpadding="0" cellspacing="0" style="margin: 0 auto 20px auto;">
                        <tr>
                            <td align="center" style="background-color: #3b82f6; width: 64px; height: 64px; border-radius: 20px;">
                                <span style="font-size: 32px; line-height: 64px;">🔑</span>
                            </td>
                        </tr>
                    </table>
                    <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0; letter-spacing: -0.025em;">Reset Your Password</h1>
                    <p style="color: #94a3b8; font-size: 16px; margin-top: 12px;">Secure access to your CBMS Pro account.</p>
                </div>
                
                <div style="color: #cbd5e1; font-size: 16px; line-height: 1.6; margin-bottom: 32px; text-align: center;">
                    <p>We received a request to reset the password for your account. If this was you, click the button below to create a new one.</p>
                </div>
                
                <div style="text-align: center; margin-bottom: 40px;">
                    <a href="{reset_link}" style="display: inline-block; background: linear-gradient(90deg, #2563eb 0%, #4f46e5 100%); color: white; padding: 16px 32px; font-weight: 600; font-size: 16px; text-decoration: none; border-radius: 12px; transition: all 0.2s; box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.3);">
                        Create New Password
                    </a>
                </div>
                
                <div style="border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 24px; text-align: center;">
                    <p style="color: #64748b; font-size: 14px; margin-bottom: 8px;">Didn't request this change? You can safely ignore this email.</p>
                    <p style="color: #64748b; font-size: 12px; margin: 0;">This secure link expires in 60 minutes.</p>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 32px;">
                <p style="color: #475569; font-size: 12px; margin: 0;">&copy; 2026 CBMS Pro Automation. All rights reserved.</p>
                <div style="margin-top: 12px;">
                    <a href="{base_url}/privacy" style="color: #3b82f6; text-decoration: none; font-size: 12px; margin: 0 8px;">Privacy Policy</a>
                    <a href="{base_url}/terms" style="color: #3b82f6; text-decoration: none; font-size: 12px; margin: 0 8px;">Terms of Service</a>
                </div>
            </div>
        </div>
        """,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)

async def send_mfa_code_email(email_to: str, code: str):
    message = MessageSchema(
        subject="Your MFA Verification Code - CBMS Pro",
        recipients=[email_to],
        body=f"""
        <div style="background-color: #0f172a; padding: 40px 20px; font-family: 'Inter', Arial, sans-serif;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; border-radius: 24px; padding: 40px; border: 1px solid rgba(255, 255, 255, 0.1);">
                <div style="text-align: center; margin-bottom: 32px;">
                    <table border="0" cellpadding="0" cellspacing="0" style="margin: 0 auto 20px auto;">
                        <tr>
                            <td align="center" style="background-color: #8b5cf6; width: 64px; height: 64px; border-radius: 20px;">
                                <span style="font-size: 32px; line-height: 64px;">🛡️</span>
                            </td>
                        </tr>
                    </table>
                    <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0; letter-spacing: -0.025em;">Verification Code</h1>
                    <p style="color: #94a3b8; font-size: 16px; margin-top: 12px;">Use the code below to sign in to CBMS Pro.</p>
                </div>
                
                <div style="background-color: #0f172a; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px; border: 1px solid rgba(139, 92, 246, 0.2);">
                    <span style="color: #ffffff; font-size: 40px; font-weight: 800; letter-spacing: 0.2em; font-family: 'Courier New', Courier, monospace;">{code}</span>
                </div>
                
                <div style="color: #cbd5e1; font-size: 14px; line-height: 1.6; margin-bottom: 32px; text-align: center;">
                    <p>This code is valid for 5 minutes. If you didn't request this code, please secure your account immediately.</p>
                </div>
                
                <div style="border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 24px; text-align: center;">
                    <p style="color: #64748b; font-size: 12px; margin: 0;">&copy; 2026 CBMS Pro Automation. All rights reserved.</p>
                </div>
            </div>
        </div>
        """,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)
