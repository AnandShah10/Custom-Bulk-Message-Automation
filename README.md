# CBMS Pro: Bulk WhatsApp Message Sender

CBMS Pro is a high-performance, fully customizable backend robust queuing system and web dashboard designed to send bulk WhatsApp messages using the [WaSender API](https://www.wasenderapi.com).

## Features
- **Send Multiple Message Types:** Native support for Text, Image, Video, Document, Location, Audio, Sticker, Poll and Contact vCards.
- **Simultaneous Multi-format Sending:** Check multiple message types simultaneously; the backend queues each type in succession to the same contact seamlessly.
- **Premium Glassmorphism UI:** Features a sleek dark-mode interface with interactive, dynamic forms that expand/collapse based on the selected criteria.
- **Dynamic WhatsApp Session Management:** Connect your own WhatsApp number via QR code scanning directly from the dashboard.
- **User Profile & Security:** Support for Full Names, MFA (Aon), and OAuth 2.0 (Google/Microsoft).
- **UUID-based Identifiers:** Enhanced security with UUID4 public identifiers for all users.
- **Robust Background Queuing:** Built-in `queue_manager` uses threading, exponential backoff for failed requests, and specific `HTTP 429` rate limiting checks.
- **Excel Ingestion:** Ingests dynamic, personalized templates (e.g. `{Name}`) directly from your Excel `.xlsx` files.

## Project Structure
```
├── app
│   ├── main.py              # FastAPI endpoint router and logic handler
│   ├── queue_manager.py     # Background worker thread & session configs
│   ├── wasender_utils.py    # WASender API abstraction layer
│   ├── routers
│   │   ├── sessions.py      # WhatsApp session management endpoints
│   │   ├── auth.py          # Email/Password authentication
│   │   └── oauth.py         # Google/Microsoft login logic
│   ├── templates
│   │   ├── index.html       # Main Dashboard
│   │   └── sessions.html    # WhatsApp QR Connection page
│   └── static
│       └── style.css        # Interactive animations & glassmorphism visuals
├── .env                     # Configuration (API Keys, Tokens, JWT Secret)
├── requirements.txt         # Project dependencies
└── README.md                # This file
```

## Quick Start
1. Ensure you have Python installed.
2. Clone this repository and navigate to the root directory `Custom-Bulk-Message-Automation`.
3. Set up the virtual environment:
   ```cmd
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
4. Install dependencies:
   ```cmd
   pip install -r requirements.txt
   ```
5. Place your `.env` file in the root directory:
   ```env
    WASENDER_PERSONAL_TOKEN=your_personal_access_token_here
    WASENDER_API_KEY=your_default_api_key_here
    JWT_SECRET_KEY=your_random_secret_string
    BASE_URL=http://localhost:8000
   ```
6. Run the application locally:
   ```cmd
   uvicorn app.main:app --reload
   ```
7. Open `http://127.0.0.1:8000` in your web browser to access the dashboard.

## System Requirements
- Python 3.8+
- Active WaSender API subscription/key

---
For usage instructions, please refer to the `USER_MANUAL.md`.
