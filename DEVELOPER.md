# Developer Setup & Technical Documentation

This guide is for developers who want to set up CBMS Pro locally for development or contributions.

## Quick Start (Local Development)

1. **Prerequisites**: Python 3.8+ installed.
2. **Clone the Repository**:
   ```cmd
   git clone https://github.com/AnandShah10/Custom-Bulk-Message-Automation.git
   cd Custom-Bulk-Message-Automation
   ```
3. **Set up Virtual Environment**:
   ```cmd
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
4. **Install Dependencies**:
   ```cmd
   pip install -r requirements.txt
   ```
5. **Configure Environment**: Place your `.env` file in the root directory with necessary API keys (WaSender, Gemini/OpenAI, JWT Secret).
6. **Run Application**:
   ```cmd
   uvicorn app.main:app --reload
   ```

## Project Structure
- `app/`: Core FastAPI application logic.
- `scripts/`: Utility scripts (e.g., indexing documentation).
- `chroma_db/`: Local vector database storage.
- `knowledge_graph.json`: Graph structure for RAG expansion.

## Support Bot Technicals
The support bot uses a GraphRAG approach combining ChromaDB (vector) and NetworkX (graph).
- **Indexing**: Handled by `scripts/index_docs.py`.
- **Engine**: Core logic in `app/rag_engine.py`.
- **Router**: FastAPI endpoints in `app/routers/support.py`.
