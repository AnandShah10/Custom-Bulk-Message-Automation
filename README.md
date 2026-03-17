# CBMS Pro: Bulk WhatsApp Message Sender

CBMS Pro is a high-performance, fully customizable backend robust queuing system and web dashboard designed to send bulk WhatsApp messages using the [WaSender API](https://www.wasenderapi.com).

## Features
- **Send Multiple Message Types:** Native support for Text, Image, Video, Document, Location, and Contact vCards.
- **Simultaneous Multi-format Sending:** Check multiple message types simultaneously; the backend queues each type in succession to the same contact seamlessly.
- **Premium Glassmorphism UI:** Features a sleek dark-mode interface with interactive, dynamic forms that expand/collapse based on the selected criteria.
- **Fallback Environment Variables:** Input fields can be left blank, allowing the application to securely load APIs keys out of your private `.env` file automatically.
- **Robust Background Queuing:** Built-in `queue_manager` uses threading, exponential backoff for failed requests, and specific `HTTP 429` rate limiting checks.
- **Excel Ingestion:** Ingests dynamic, personalized templates (e.g. `{Name}`) directly from your Excel `.xlsx` files.

## Project Structure
```
├── app
│   ├── main.py              # FastAPI endpoint router and logic handler
│   ├── queue_manager.py     # Background worker thread & session configs
│   ├── templates
│   │   └── index.html       # Dynamic frontend layout built with Tailwind CSS
│   └── static
│       └── style.css        # Interactive animations & glassmorphism visuals
├── .env                     # Hidden environment file containing WASENDER_API_KEY
├── requirements.txt         # Project dependencies
└── README.md                # This file
```

## Quick Start
1. Ensure you have Python installed.
2. Clone this repository and navigate to the root directory `Bulk whatsapp message`.
3. Set up the virtual environment:
   ```cmd
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
4. Install dependencies:
   ```cmd
   pip install fastapi uvicorn pandas openpyxl python-dotenv requests jinja2
   ```
5. Place your `.env` file in the root directory:
   ```env
   WASENDER_API_KEY=your_secret_api_key_here
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
