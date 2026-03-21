from fpdf import FPDF
import io
from datetime import datetime

class CampaignReport(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 20)
        self.set_text_color(37, 99, 235) # Blue 600
        self.cell(0, 10, 'CBMS Pro | Campaign Report', ln=True, align='C')
        self.ln(5)
        self.set_draw_color(226, 232, 240)
        self.line(10, 25, 200, 25)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(100)
        self.cell(0, 10, f'Page {self.page_no()} | Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")}', align='C')

def generate_campaign_pdf(campaign, logs):
    pdf = CampaignReport()
    pdf.add_page()
    
    # Campaign Overview
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, f'Campaign: {campaign.name}', ln=True)
    pdf.set_font('helvetica', '', 10)
    pdf.cell(100, 8, f'Status: {campaign.status.upper()}', ln=False)
    pdf.cell(0, 8, f'Date: {campaign.created_at.strftime("%Y-%m-%d %H:%M")}', ln=True)
    pdf.ln(5)

    # Stats Grid
    pdf.set_fill_color(248, 250, 252)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(63, 15, f'Total Contacts: {campaign.total_contacts}', border=1, fill=True, align='C')
    pdf.cell(63, 15, f'Success: {campaign.success_count}', border=1, fill=True, align='C')
    pdf.cell(64, 15, f'Failure: {campaign.failure_count}', border=1, fill=True, align='C')
    pdf.ln(20)

    # Logs Table
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 10, 'Message Logs', ln=True)
    pdf.ln(2)
    
    # Table Header
    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(45, 10, ' Phone', border=1, fill=True)
    pdf.cell(30, 10, ' Status', border=1, fill=True)
    pdf.cell(115, 10, ' Details/Errors', border=1, fill=True)
    pdf.ln()

    # Table Content
    pdf.set_text_color(30, 41, 59)
    pdf.set_font('helvetica', '', 9)
    for log in logs[:100]: # Cap at 100 for readability in summary, or adjust as needed
        status_color = (34, 197, 94) if log.status == 'success' else (239, 68, 68)
        
        pdf.cell(45, 8, f' {log.phone}', border=1)
        
        # Status with color is tricky in fpdf2 for cell text, so we'll just check
        pdf.cell(30, 8, f' {log.status.upper()}', border=1)
        
        # Details (multi-line handle)
        details = (log.error_message or 'Delivered successfully')[:60]
        pdf.cell(115, 8, f' {details}', border=1)
        pdf.ln()

    if len(logs) > 100:
        pdf.ln(5)
        pdf.set_font('helvetica', 'I', 8)
        pdf.cell(0, 10, f'* Only showing first 100 of {len(logs)} logs in this summary PDF.', ln=True, align='C')

    # S returns as string for fpdf, and bytes/bytearray for fpdf2
    try:
        return pdf.output(dest='S')
    except TypeError:
        # Some fpdf2 versions don't like dest='S'
        return pdf.output()
